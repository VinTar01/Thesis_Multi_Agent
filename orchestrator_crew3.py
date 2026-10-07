import os
import re
import json
import time
import requests 
from typing import TypedDict, List, Dict, Any
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langgraph.graph import StateGraph, END

from Crew3.crew3_enrichment import crew_wikidata

load_dotenv()

# ==========================================
# CONNESSIONE AL KNOWLEDGE GRAPH (LIVELLO LOCALE)
# ==========================================
# Inizializzazione della connessione al database Neo4j.
# in questo contesto il database funge sia da sorgente dati (i nodi da arricchire) 
# sia da destinazione (il ritorno dei metadati da Wikidata).
URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USERNAME") 
PASSWORD = os.getenv("NEO4J_PASSWORD")

if not all([URI, USER, PASSWORD]):
    raise ValueError("[FATAL] Credenziali Neo4j mancanti. Controllare l'ambiente (.env).")

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# ==========================================
# FUNZIONE DI SUPPORTO Q-ID
# ==========================================
# Anziché forzare l'Intelligenza Artificiale a generare query SPARQL complesse 
# basate sul nome testuale del nodo (spesso ambiguo), il sistema interroga 
# deterministicamente le API native di Wikidata per recuperare l'ID univoco (Q-ID).
# L'agente verrà invocato solo se il Q-ID esiste, risparmiando token per i nodi irrilevanti.

def cerca_qid_wikidata(nome_entita: str) -> str | None:
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities", 
        "format": "json",
        "language": "it",
        "search": nome_entita 
    }
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "GraceMultiAgent/1.0"})
        data = resp.json() 
        if data.get("search"):
            # L'API wbsearchentities ordina fisiologicamente i risultati per pertinenza
            return data["search"][0]["id"]
    except Exception as e:
        print(f"[API ERROR] Fallimento durante la risoluzione dell'entità '{nome_entita}': {e}")
    return None


# ==========================================
# 1. DEFINIZIONE DELLO STATO GLOBALE
# ==========================================
class EnrichmentState(TypedDict):
    nodi_da_arricchire: List[Dict[str, Any]]
    nodi_completati: List[str]
    nodi_non_trovati: List[str]
    nodi_errore: List[str]


# ==========================================
# NODO 1: SCOPERTA DEI NODI LOCALI 
# ============================================
def scoperta_nodi(state: EnrichmentState):
    """
    Interroga il grafo locale per isolare i nodi che richiedono espansione semantica.
    """
    print("\n[LANGGRAPH NODE: Target Acquisition] Scansione del database Neo4j...")
    
    # Per mitigare il rumore e i falsi positivi semantici, l'ambito di ricerca
    # è strettamente circoscritto alle entità oggettive (Location, Weapon, Case).
    # Le entità 'Person' vengono deliberatamente escluse poiché l'ecosistema 
    # di Wikidata tende a rimandare alla pagina del caso giudiziario piuttosto 
    # che a schede biografiche pertinenti, invalidando l'Entity Resolution.
    # Il flag 'wikidata_checked IS NULL' impedisce elaborazioni ridondanti.
    query = """
    MATCH (n)
    WHERE (n:Location OR n:Weapon OR n:Case)
      AND n.wikidata_checked IS NULL 
      AND n.name IS NOT NULL
    RETURN n.id AS id, n.name AS name, labels(n)[0] AS label
    """
    
    nodi = []
    try:
        with driver.session() as session:
            result = session.run(query)
            for record in result:
                nodi.append({
                    "id": record["id"],
                    "name": record["name"],
                    "label": record["label"]
                })
        print(f"-> [INFO] Nodi candidati all'arricchimento semantico: {len(nodi)}")
    except Exception as e:
        print(f"[FATAL] Interruzione del driver Neo4j: {e}")

    return {
        "nodi_da_arricchire": nodi,
        "nodi_completati": [],
        "nodi_non_trovati": [],
        "nodi_errore": []
    }


# ==========================================
# NODO 2: DELEGA ALL'AGENTE E PERSISTENZA DELLE PROPRIETÀ
# ==========================================
def arricchimento_nodo(state: EnrichmentState):
    """
    Gestisce l'integrazione tra il mondo chiuso (Local DB) e il mondo aperto (Wikidata).
    Esegue il check deterministico e delega all'LLM la formulazione della query SPARQL.
    """
    da_processare = state["nodi_da_arricchire"].copy()
    completati = state["nodi_completati"].copy()
    non_trovati = state["nodi_non_trovati"].copy()
    errori = state["nodi_errore"].copy()

    if not da_processare:
        return state

    nodo_corrente = da_processare.pop(0)
    nodo_id = nodo_corrente["id"]
    nodo_nome = nodo_corrente["name"]
    nodo_label = nodo_corrente["label"]

    print(f"\n[LANGGRAPH NODE: Enrichment] Analisi Entità: '{nodo_nome}' ({nodo_label}) [Queue: {len(da_processare)}]")

    try:
        # FASE 1: Risoluzione Identità 
        q_id = cerca_qid_wikidata(nodo_nome)
        
        # Gestione del Null-Routing: Se l'entità è assente dal web semantico,
        # l'agente non viene invocato. Il nodo viene marcato localmente per 
        # impedire future valutazioni a vuoto.
        if not q_id:
            print(f" -> [MISSING] Q-ID non risolto. Marcatura del nodo per bypass futuro.")
            query_skip = "MATCH (n {id: $id}) SET n.wikidata_checked = true" 
            with driver.session() as session:
                session.run(query_skip, id=nodo_id)
            non_trovati.append(nodo_id)
            time.sleep(2)
            return {
                "nodi_da_arricchire": da_processare,
                "nodi_completati": completati,
                "nodi_non_trovati": non_trovati,
                "nodi_errore": errori
            }

        print(f" -> [Q-ID RESOLVED] Trovato identificativo: {q_id}. Delega all'Agente SPARQL...")

        # FASE 2: Esecuzione Dinamica (Text-to-SPARQL)
        # L'agente sfrutta il Q-ID per navigare la struttura gerarchica ed estrarre i metadati.
        risultato_crew = crew_wikidata.kickoff(inputs={
            "nome_entita": nodo_nome,
            "label_entita": nodo_label,
            "q_id": q_id 
        })

        output_str = str(risultato_crew).strip()

        # FASE 3: Parsing ed Estrazione
        # Regex per isolare il payload JSON ignorando eventuali allucinazioni discorsive
        match_json = re.search(r"\{.*\}", output_str, re.DOTALL)
        if match_json:
            dati_arricchiti = json.loads(match_json.group(0))
        else:
            dati_arricchiti = {"trovato": False}

        # Valutazione semantica del risultato SPARQL
        if dati_arricchiti.get("trovato") is False:
            print(f" -> [SPARQL EMPTY] Nessun binding rilevato per i vincoli imposti. Marcatura del nodo.")
            query_skip = "MATCH (n {id: $id}) SET n.wikidata_checked = true"
            with driver.session() as session:
                session.run(query_skip, id=nodo_id)
            non_trovati.append(nodo_id)

        else:
            # Normalizzazione del Dizionario e Iniezione nel Grafo Locale
            dati_arricchiti.pop("trovato", None)
            dati_arricchiti.pop("wikidata_id", None) 
            
            # Tracciamento dell'integrità del ciclo di arricchimento
            dati_arricchiti["wikidata_checked"] = True

            print(f" -> [PAYLOAD READY] Proprietà estratte: {dati_arricchiti}")

            # Persistenza tramite Mutazione Dinamica (SET += unisce il dizionario alle properties del nodo)
            query_update = """
            MATCH (n {id: $id})
            SET n += $props
            """
            with driver.session() as session:
                session.run(query_update, id=nodo_id, props=dati_arricchiti)

            print(f" -> [SUCCESS] Mutazione Neo4j completata.")
            completati.append(nodo_id)

    except Exception as e:
        print(f" -> [EXCEPTION] Esecuzione interrotta durante il processing di '{nodo_nome}': {e}")
        errori.append(nodo_id)

   
    print(" -> [RATE LIMIT] Applicazione backoff di 15 secondi...")
    time.sleep(15)

    return {
        "nodi_da_arricchire": da_processare,
        "nodi_completati": completati,
        "nodi_non_trovati": non_trovati,
        "nodi_errore": errori
    }


# ==========================================
# 3. ROUTER CONDIZIONALE
# ==========================================
def continua_o_termina(state: EnrichmentState):
    """Gestione deterministica dell'iterazione della Macchina a Stati."""
    if len(state["nodi_da_arricchire"]) == 0:
        return "fine"
    return "continua"


# ==========================================
# 4. COMPILAZIONE DELLA MACCHINA A STATI
# ==========================================
workflow = StateGraph(EnrichmentState)

workflow.add_node("scoperta", scoperta_nodi)
workflow.add_node("arricchimento", arricchimento_nodo)

workflow.set_entry_point("scoperta")
workflow.add_edge("scoperta", "arricchimento")

workflow.add_conditional_edges(
    "arricchimento",
    continua_o_termina,
    {
        "continua": "arricchimento",
        "fine": END
    }
)

app_enrichment = workflow.compile()


# ==========================================
# RUNTIME PRINCIPALE
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print(" AVVIO SISTEMA ORCHESTRATO - FASE 3 (SEMANTIC ENRICHMENT)")
    print("="*50)

    stato_iniziale = {
        "nodi_da_arricchire": [],
        "nodi_completati": [],
        "nodi_non_trovati": [],
        "nodi_errore": []
    }

    risultato_finale = app_enrichment.invoke(stato_iniziale)

    print("\n" + "="*50)
    print(" TELEMETRIA FINALE (CREW 3) ")
    print("="*50)
    print(f"Nodi integrati con successo in Neo4j  : {len(risultato_finale['nodi_completati'])}")
    print(f"Nodi privi di estensione semantica    : {len(risultato_finale['nodi_non_trovati'])}")
    print(f"Eccezioni a runtime (Errori)          : {len(risultato_finale['nodi_errore'])}")