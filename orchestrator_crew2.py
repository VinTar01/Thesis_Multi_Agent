import os
import json
import shutil
import time
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from neo4j import GraphDatabase

from Crew2.crew2_db import crew_neo4j_writer

# ==========================================
# CONNESSIONE AL DATABASE 
# ==========================================
# L'orchestratore utilizza una connessione diretta per eseguire controlli 
# veloci a basso costo computazionale prima di invocare l'LLM.
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "myThesis" 
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# ==========================================
# 1. DEFINIZIONE DELLO STATO GLOBALE (MEMORIA CONDIVISA)
# ==========================================
# La classe DBState rappresenta la "Coda di Messaggi" del sistema.
# Definisce tre liste: i task pendenti, quelli andati a buon fine
# e quelli falliti. 
# LangGraph aggiorna questo dizionario
# al termine di ogni transizione di stato.

class DBState(TypedDict):
    file_da_processare: List[str]
    file_completati: List[str]
    file_errore: List[str]

# ==========================================
# FUNZIONE DI SUPPORTO NON USATA ATTUALMENTE
# ==========================================
def file_gia_inserito(dati_json: dict) -> bool:
    """
    Prima di allocare token e tempo computazionale all'agente IA, questa funzione
    interroga deterministicamente Neo4j tramite Cypher statico per verificare 
    se le entità 'Case' contenute nel JSON siano già presenti.
    In ottica di efficienza, agisce anche da filtro preventivo contro le duplicazioni.
    """
    entities = dati_json.get("entities", [])
    if not entities:
        return False
    
    # Ricerca di nodi root di tipo 'Case'
    case_entities = [e for e in entities if e.get("label") == "Case"]
    
    if case_entities:
        ids_casi = [c.get("id") for c in case_entities if c.get("id")]
        if not ids_casi:
            return False
            
        # Verifica transazionale tramite il driver
        query = "MATCH (n:Case) WHERE n.id IN $ids RETURN count(n) as cnt"
        try:
            with driver.session() as session:
                result = session.run(query, ids=ids_casi)
                record = result.single()
                cnt = record["cnt"] if record else 0
                return cnt == len(ids_casi)
        except Exception as e:
            print(f"[ERROR] Impossibile verificare l'esistenza dei casi: {e}")
            return False
            
    else:
        # Fallback: verifica sulla prima entità disponibile se 'Case' non è presente
        prima_entita_id = entities[0].get("id")
        if not prima_entita_id:
            return False
            
        query = "MATCH (n {id: $id}) RETURN n LIMIT 1"
        try:
            with driver.session() as session:
                result = session.run(query, id=prima_entita_id)
                return result.peek() is not None
        except Exception as e:
            print(f"[PRE-FLIGHT ERROR] Impossibile verificare l'entità {prima_entita_id}: {e}")
            return False
        
# ==========================================
# NODO 1: INIZIALIZZAZIONE DELLA CODA DI LAVORO
# ==========================================
def scoperta_file(state: DBState):
    """
    Fase di Ingestion Locale: analizza la directory di output della Fase 1,
    identifica tutti i JSON validati e li inietta nello Stato iniziale
    per l'elaborazione.
    """
    print("\n[LANGGRAPH NODE: Ingestion] Scansione directory locale 'casi_estratti_json'...")
    cartella = "casi_estratti_json"
    
    if not os.path.exists(cartella):
        print("-> [INFO] Nessuna directory sorgente trovata. Coda vuota.")
        return {"file_da_processare": [], "file_completati": [], "file_errore": []}
        
    files = [os.path.join(cartella, f) for f in os.listdir(cartella) if f.endswith(".json")]
    print(f"-> [INFO] Identificati {len(files)} payload pronti per l'ingestione.")
    
    return {"file_da_processare": files, "file_completati": [], "file_errore": []}

# ==========================================
# NODO 2: DELEGA AGENTICA E GESTIONE FILE SYSTEM
# ==========================================
def inserimento_db(state: DBState):
    """
    Preleva un singolo JSON, lo carica in memoria, esegue eventuali check,
    delega il task all'agente CrewAI e, in caso di successo, archivia il file fisico
    per prevenire doppie elaborazioni in esecuzioni future.
    """
    da_processare = state["file_da_processare"].copy()
    completati = state["file_completati"].copy()
    errori = state["file_errore"].copy()

    if not da_processare:
        return state

    file_corrente = da_processare.pop(0)
    print(f"\n[LANGGRAPH NODE: Exec] Elaborazione: {file_corrente} (Queue: {len(da_processare)})")

    try:
        # Caricamento payload
        with open(file_corrente, 'r', encoding='utf-8') as f:
            dati_json = json.load(f)

        cartella_archivio = "casi_inseriti_db"
        os.makedirs(cartella_archivio, exist_ok=True)

        # ==========================================
        # OPZIONALE: mi serviva per fare alcune prove 
        # Se attivato, sfrutta file_gia_inserito() per saltare file già presenti
        # nel grafo, risparmiando latenza e token API.
        # ==========================================
        # if file_gia_inserito(dati_json):
        #    print(f" -> [SKIP] Topologia già presente in Neo4j. Archiviazione diretta.")
        #    percorso_archivio = os.path.join(cartella_archivio, os.path.basename(file_corrente))
        #    shutil.move(file_corrente, percorso_archivio)
        #    completati.append(file_corrente)
        #    return {"file_da_processare": da_processare, "file_completati": completati, "file_errore": errori}

        # Serializzazione e delega al framework multi-agente
        json_string = json.dumps(dati_json, ensure_ascii=False, indent=2)
        risultato = crew_neo4j_writer.kickoff(inputs={'json_da_inserire': json_string}) #chiamata della crew

        print(f" -> [SUCCESS] Transazione completata per '{file_corrente}'.")
        
        # Archiviazione fisica del file (Spostamento)
        percorso_archivio = os.path.join(cartella_archivio, os.path.basename(file_corrente))
        shutil.move(file_corrente, percorso_archivio)
        completati.append(file_corrente)

    except Exception as e:
        print(f" -> [EXCEPTION] Impossibile completare l'ingestione per {file_corrente}: {e}")
        errori.append(file_corrente)


    print(" -> [RATE LIMIT] Applicazione backoff di 15 secondi...")
    time.sleep(15)

    return {"file_da_processare": da_processare, "file_completati": completati, "file_errore": errori}


# ==========================================
# 3. ROUTER CONDIZIONALE
# ==========================================
def continua_o_termina(state: DBState):
    """Semaforo di stato: valuta l'esaurimento della coda di elaborazione."""
    if len(state["file_da_processare"]) == 0:
        return "fine"
    return "continua"

# ==========================================
# 4. ASSEMBLAGGIO MACCHINA A STATI
# ==========================================
workflow = StateGraph(DBState)

workflow.add_node("scoperta", scoperta_file)
workflow.add_node("inserimento", inserimento_db)

workflow.set_entry_point("scoperta")
workflow.add_edge("scoperta", "inserimento")

workflow.add_conditional_edges(
    "inserimento",
    continua_o_termina,
    {
        "continua": "inserimento",
        "fine": END                 
    }
)

app_db = workflow.compile()

# ==========================================
# RUNTIME PRINCIPALE
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print(" AVVIO SISTEMA ORCHESTRATO - FASE 2 (DB INGESTION)")
    print("="*50)
    
    # Inizializzazione stato pulito
    stato_iniziale = {"file_da_processare": [], "file_completati": [], "file_errore": []}
    risultato_finale = app_db.invoke(stato_iniziale)
    
    print("\n" + "="*50)
    print(" TELEMETRIA FINALE (CREW 2) ")
    print("="*50)
    print(f"Payload archiviati con successo in Neo4j : {len(risultato_finale['file_completati'])}")
    print(f"Payload falliti o respinti dal database  : {len(risultato_finale['file_errore'])}")