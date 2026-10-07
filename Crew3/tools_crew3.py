import requests
from crewai.tools import tool

# ==========================================
# TOOL: INTERFACCIA ENDPOINT SPARQL
# ==========================================
# Questo strumento incapsula la comunicazione HTTP con il cloud Wikidata.
# Implementa due difese ingegneristiche fondamentali:
# 1. Identity Masking (User-Agent): Indispensabile per conformarsi alle policy di Wikidata 
#    e prevenire il blocco dell'IP (HTTP 403 Forbidden) durante elaborazioni massive.
# 2. Token Optimization: Il payload JSON restituito da SPARQL contiene metadati prolissi. 
#    Estraendo solo la chiave 'bindings', si protegge la context window dell'LLM, 
#    abbattendo i costi di latenza e computazione.

@tool("Interroga_Wikidata_SPARQL")
def interroga_wikidata_sparql(query: str) -> str:
    """
    Esegue una query SPARQL sull'endpoint pubblico di Wikidata.
    
    ATTENZIONE: L'invocazione di questo tool richiede un dizionario JSON valido, 
    utilizzando ESCLUSIVAMENTE la chiave "query". 
    Esempio di sintassi accettata: {"query": "SELECT ?prop WHERE { ... }"}
    """
    url = "https://query.wikidata.org/sparql"
    
    # Intestazioni obbligatorie per l'identificazione e la negoziazione del formato
    headers = {
        "User-Agent": "GraceMultiAgent/1.0 (Python/Requests)",
        "Accept": "application/sparql-results+json"
    }
    try:
        response = requests.get(url, params={'query': query}, headers=headers)
        response.raise_for_status()
        dati = response.json()
        
        # Filtraggio del payload per l'estrazione esclusiva dei dati relazionali
        risultati_puliti = dati.get("results", {}).get("bindings", [])
        return str(risultati_puliti)
        
    except Exception as e:
        # Il passaggio dell'eccezione come stringa innesca il meccanismo di 
        # auto-riflessione dell'agente (ReAct), consentendo correzioni dinamiche della query.
        return f"Fallimento esecuzione SPARQL. Dettaglio eccezione: {e}"