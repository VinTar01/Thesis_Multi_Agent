import json
import os
import requests
import time
from typing import TypedDict, List
from pydantic import ValidationError
from langgraph.graph import StateGraph, END

from Crew1.crew1_ingestion import crew_estrazione_casi
from schemas import SchemaGrafo

# ==========================================
# IL RUOLO DELL'ORCHESTRATORE (LANGGRAPH)
# ==========================================
# L'orchestratore funge da direttore del lavoro della crew.
# Anziché lanciare l'agente IA (CrewAI) alla cieca su centinaia di pagine, LangGraph 
# costruisce un flusso di lavoro ordinato (un grafo a stati). 
# 
# Il cuore di questo sistema è lo "Stato" (GraphState): una memoria globale che tiene 
# traccia di tutto. Lo Stato comprende le info su:
# 1. Quali casi dobbiamo ancora analizzare
# 2. Quali casi abbiamo completato con successo
# 3. Quali casi abbiamo scartato (perché erano film, biografie o per errori)
#
# LangGraph passa questo Stato da una funzione all'altra (chiamate "Nodi"). 
# In questo modo, il codice Python gestisce la logica di base (scaricare testi, filtrare parole) 
# in modo veloce ed economico, chiamando l'Intelligenza Artificiale solo quando 
# c'è un testo pulito e pertinente da analizzare.

class GraphState(TypedDict):
    """La struttura della memoria condivisa del sistema."""
    casi_da_processare: List[str]
    casi_completati: List[dict]
    casi_scartati: List[str]

# ==========================================
# FUNZIONI DI SUPPORTO (PRE-ELABORAZIONE)
# ==========================================

def ottieni_pagine_categoria(categoria: str, pagine_trovate=None) -> list:
    """
    Funzione esplorativa: Interroga le API di Wikipedia partendo da una categoria principale
    ("Casi di omicidio in Italia") e naviga automaticamente anche nelle sottocategorie,
    raccogliendo e restituendo tutti i titoli delle pagine trovate.
    """
    if pagine_trovate is None: pagine_trovate = set() 
    url = "https://it.wikipedia.org/w/api.php"
    params = {"action": "query", "list": "categorymembers", "cmtitle": categoria, "cmlimit": "max", "format": "json"}
    headers = {"User-Agent": "GraceBench/1.0 (Tesi AI)"} #per superare un blocco antibot di wikipedia
    
    try:
        risposta = requests.get(url, params=params, headers=headers).json()
        if "query" in risposta and "categorymembers" in risposta["query"]:
            for member in risposta["query"]["categorymembers"]:
                titolo = member["title"]
                if titolo.startswith("Categoria:"): ottieni_pagine_categoria(titolo, pagine_trovate)
                else: pagine_trovate.add(titolo)
    except Exception: pass
    return list(pagine_trovate)


def scarica_testo_caso(titolo: str) -> str:
    """
    Dato un titolo esatto, scarica solo il testo puro della pagina.
    Gestisce anche i reindirizzamenti (redirects=1) nel caso in cui il titolo della pagina sia cambiato.
    """
    url = "https://it.wikipedia.org/w/api.php"
    params = {"action": "query", "prop": "extracts", "explaintext": True, "titles": titolo, "format": "json", "redirects": 1}
    headers = {"User-Agent": "GraceBench/1.0 (Tesi AI)"}
    try:
        risposta = requests.get(url, params=params, headers=headers)
        risposta.raise_for_status()
        pagine = risposta.json().get("query", {}).get("pages", {})
        for page_id, info in pagine.items():
            return info.get("extract", "")
    except Exception as e: 
        print(f"[API ERROR] Errore di connessione su '{titolo}': {e}")
        return ""
    return ""


def passa_filtro_euristico(testo: str) -> bool:
    """
    Primo controllo di sicurezza.
    Legge i primi 1500 caratteri del testo alla ricerca di parole chiave come "film" o "romanzo".
    Se le trova, il documento non è un vero caso di cronaca e viene scartato, risparmiando la chiamata dell'LLM.
    """
    parole_vietate = ["film", "romanzo", "serie televisiva", "miniserie", "fiction", "sceneggiato"]
    testo_lower = testo.lower()[:1500]
    for parola in parole_vietate:
        if parola in testo_lower:
            return False
    return True


def passa_filtro_biografico(testo: str) -> bool:
    """
    Secondo controllo di sicurezza.
    Legge i primi 500 caratteri per capire se la pagina parla
    di una figura istituzionale, storica o politica, che non rientra nei parametri dell'analisi forense.
    """
    parole_storiche = [
        "politico italiano", "militare italiano", "nobile", "re d'italia", 
        "imperatore", "patriota", "condottiero", "partigiano", "sovrano", 
        "papa ", "vescovo", "dittatore", "senatore", "deputato", "ministro", 
        "sindacalista", "presidente", "parlamentare"
    ]
    testo_lower = testo.lower()[:500]
    for parola in parole_storiche:
        if parola in testo_lower:
            return False
    return True

# ==========================================
# I NODI DEL GRAFO (LE FASI DI LAVORO)
# ==========================================

def scoperta_casi(state: GraphState):
    """
    NODO 1: Il punto di partenza di questa fase. 
    Usa la funzione di ricerca per trovare tutti i titoli su Wikipedia. 
    Prende questi titoli e li inserisce nella "lista delle cose da fare" (casi_da_processare) dello Stato.
    """
    print("\n[NODO 1: Scoperta] Inizializzazione spider su Wikipedia...")
    titoli = ottieni_pagine_categoria("Categoria:Casi_di_omicidio_in_Italia")
    print(f"[INFO] Trovati {len(titoli)} casi potenziali da analizzare.")
    return {"casi_da_processare": titoli, "casi_completati": [], "casi_scartati": []}


def elabora_caso(state: GraphState):
    """
    NODO 2: La parte principale della fase. Viene eseguito per ogni singolo caso.
    Estrae un titolo dalla lista "da_processare" ed esegue, in ordine:
    1. Il download del testo.
    2. I controlli di sicurezza (Filtro Euristico e Biografico).
    3. Se il testo passa i controlli, viene passato all'Agente IA di crewai per l'estrazione.
    4. Salva il risultato generato dall'IA in un file JSON locale.
    Alla fine, aggiorna lo Stato spostando il titolo nella lista dei "completati" o degli "scartati".
    """
    da_processare = state["casi_da_processare"].copy()
    completati = state["casi_completati"].copy()
    scartati = state["casi_scartati"].copy()

    # Se non ci sono più casi, restituisce lo stato invariato
    if not da_processare: return state
    
    # Preleva il primo caso dalla lista
    titolo_corrente = da_processare.pop(0)
    print(f"\n[NODO 2: Elaborazione] Analisi in corso: '{titolo_corrente}' (Coda: {len(da_processare)})")

    # Step 1: Download del testo puro
    testo_pagina = scarica_testo_caso(titolo_corrente)
    if len(testo_pagina) < 100:
        print("  -> [SCARTO] Errore: Pagina vuota o non accessibile.")
        scartati.append(titolo_corrente)
        time.sleep(1) 
        return {"casi_da_processare": da_processare, "casi_completati": completati, "casi_scartati": scartati}

    # Step 2: Controlli di sicurezza (script statici)
    if not passa_filtro_euristico(testo_pagina):
        print("  -> [SCARTO] Filtro Euristico: Rilevata probabile opera di finzione cinematografica/letteraria.")
        scartati.append(titolo_corrente)
        time.sleep(1) 
        return {"casi_da_processare": da_processare, "casi_completati": completati, "casi_scartati": scartati}

    if not passa_filtro_biografico(testo_pagina):
        print("  -> [SCARTO] Filtro Biografico: Rilevato profilo di personaggio storico o istituzionale.")
        scartati.append(titolo_corrente)
        time.sleep(1) 
        return {"casi_da_processare": da_processare, "casi_completati": completati, "casi_scartati": scartati}

    # Step 3: Invocazione dell'Agente Intelligente (CrewAI)
    # Avviene solo se tutti i controlli strutturali precedenti sono stati superati
    print("  -> [AGENTE ATTIVO] Filtri superati. Avvio CrewAI per estrazione delle triple del grafo...")
    try:
        risultato = crew_estrazione_casi.kickoff(inputs={'testo_caso': testo_pagina})
        testo_grezzo = risultato.raw.strip()
        
        # Pulizia della formattazione generata dall'LLM
        if testo_grezzo.startswith("```json"): testo_grezzo = testo_grezzo[7:]
        if testo_grezzo.startswith("```"): testo_grezzo = testo_grezzo[3:]
        if testo_grezzo.endswith("```"): testo_grezzo = testo_grezzo[:-3]
        
        # Pydantic verifica che l'IA abbia rispettato la struttura imposta nel prompt
        grafo_validato = SchemaGrafo.model_validate_json(testo_grezzo.strip())
        
        if len(grafo_validato.entities) == 0:
            print("  -> [SCARTO] Anomalia IA: L'agente non ha individuato entità rilevanti nel testo.")
            scartati.append(titolo_corrente)
            time.sleep(1)
            return {"casi_da_processare": da_processare, "casi_completati": completati, "casi_scartati": scartati}
            
        # Step 4: Salvataggio fisico del file JSON
        cartella_output = "casi_estratti_json"
        os.makedirs(cartella_output, exist_ok=True)
        nome_file = f"{titolo_corrente.replace(' ', '_').lower()}.json"
        nome_file = "".join(c for c in nome_file if c.isalnum() or c in ('_', '.', '-'))
        percorso_file = os.path.join(cartella_output, nome_file)
        
        with open(percorso_file, "w", encoding="utf-8") as f:
            json.dump(grafo_validato.model_dump(), f, ensure_ascii=False, indent=4)
            
        print(f"  -> [SUCCESSO] Dati estratti e salvati in: {percorso_file}")
        completati.append({"titolo": titolo_corrente, "file": percorso_file})
        
    except ValidationError:
        print("  -> [ERRORE] Pydantic ha bloccato il JSON: l'agente ha generato uno schema non valido.")
        scartati.append(titolo_corrente)
    except Exception as e:
        print(f"  -> [ERRORE CRITICO] Malfunzionamento inatteso dell'LLM: {e}")
        scartati.append(titolo_corrente)

    # Pausa obbligatoria per non superare i limiti di utilizzo delle API di Gemini
    print("  -> [ATTESA] Pausa di sicurezza di 10 secondi per limite API...")
    time.sleep(10)
    
    return {"casi_da_processare": da_processare, "casi_completati": completati, "casi_scartati": scartati}


def continua_o_termina(state: GraphState):
    """
    Il "semaforo" del sistema. 
    Controlla lo Stato: se ci sono ancora titoli in "casi_da_processare", dice al sistema
    di continuare ("continua"). Se la lista è vuota, decreta la fine del programma ("fine").
    """
    if len(state["casi_da_processare"]) == 0: 
        return "fine"
    return "continua"

# ==========================================
# COSTRUZIONE DEL FLUSSO 
# ==========================================
# Qui i nodi vengono collegati insieme per creare il percorso logico.

workflow = StateGraph(GraphState)

# Aggiunta dei nodi al grafo
workflow.add_node("scoperta", scoperta_casi)
workflow.add_node("elaborazione", elabora_caso)

# Punto di partenza: inizia sempre dalla scoperta dei casi
workflow.set_entry_point("scoperta")

# Collegamento 1: Dopo aver scoperto i casi, passa all'elaborazione
workflow.add_edge("scoperta", "elaborazione")

# Collegamento 2: Dopo aver elaborato un caso, usa il "semaforo".
# Se dice "continua", torna al nodo di "elaborazione".
# Se dice "fine", esci dal programma (END).
workflow.add_conditional_edges("elaborazione", continua_o_termina, {"continua": "elaborazione", "fine": END})

# Compilazione del sistema in un'applicazione eseguibile
app = workflow.compile()

# ==========================================
# ESECUZIONE PRINCIPALE
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print(" AVVIO SISTEMA ORCHESTRATO - FASE 1 (ESTRAZIONE)")
    print("="*50)
    
    # Invia il comando di partenza fornendo una memoria (Stato) completamente vuota
    risultato_finale = app.invoke({"casi_da_processare": [], "casi_completati": [], "casi_scartati": []})
    
    print("\n" + "="*50)
    print(" REPORT FINALE DELLE OPERAZIONI ")
    print("="*50)
    print(f"Casi analizzati e salvati con successo: {len(risultato_finale['casi_completati'])}")
    print(f"Casi scartati (Filtri / Errori API): {len(risultato_finale['casi_scartati'])}")