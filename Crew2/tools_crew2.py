import os
from crewai.tools import tool 
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# INIZIALIZZAZIONE DRIVER DATABASE
# ==========================================
driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"), 
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
)

# ==========================================
# TOOL 1: ESECUZIONE CYPHER CON CONTROLLO
# ==========================================
# In alternativa a tool generici nativi, questo tool
# personalizzato funge da Lexical Filter.
# Ispeziona la stringa generata dall'agente prima dell'invio al database,
# intercettando e neutralizzando tentativi di esecuzione di comandi DML distruttivi 
# (DELETE, DROP, DETACH). Se rilevati, solleva un'eccezione morbida che costringe 
# l'agente (grazie al loop ReAct) a riformulare la query in modo costruttivo.

@tool("Esegui_Query_Cypher")
def execute_cypher_tool(query: str) -> str:
    """
    Esegue una query Cypher sul database Neo4j.
    Usa questo tool SOLO per inserire nuovi nodi e relazioni (CREATE/MERGE).
    
    ATTENZIONE: Devi chiamare questo tool passando gli argomenti come un dizionario JSON valido, 
    usando ESCLUSIVAMENTE la chiave "query". 
    Esempio corretto: {"query": "MERGE (p:Person {id: 'person_mario'}) RETURN p"}
    """
    query_upper = query.upper()
    
    # Livello 1: Lexical Filtering di Sicurezza
    if "DELETE" in query_upper or "DROP" in query_upper:
        return "ERRORE DI SICUREZZA: Esecuzione bloccata dal sistema. Le query distruttive non sono ammesse in questo dominio. Riformulare utilizzando MERGE."

    # Livello 2: Esecuzione Transazionale
    try:
        with driver.session() as session:
            session.run(query)
            return "SUCCESS: Transazione Cypher eseguita e persistita sul database."
    except Exception as e:
        # Il ritorno dell'eccezione come stringa alimenta l'Observation dell'agente
        # abilitando la capacità di self-correction a runtime.
        return f"EXCEPTION: Fallimento esecuzione Cypher. Dettaglio errore: {e}"

# ==========================================
# TOOL 2: DEDUPLICAZIONE GRAFO (APOC)
# ==========================================
# non viene mai usato nell'effettivo dato che le istruzioni del prompt e del tool1 
# evitano duplicati

@tool("Deduplica_Entita_APOC")
def apoc_merge_entities_tool(label: str, property_name: str, entity_value: str) -> str:
    """
    Unisce nodi duplicati nel grafo Neo4j utilizzando apoc.refactor.mergeNodes.
    Usa questo tool quando rilevi che ci sono entità scritte in modo diverso ma che 
    rappresentano lo stesso concetto (es. differenze di maiuscole/minuscole).
    
    ATTENZIONE: Devi chiamare questo tool passando gli argomenti come un dizionario JSON valido.
    Esempio corretto: {"label": "Person", "property_name": "name", "entity_value": "mario rossi"}
    """
    query = f"""
    MATCH (n:{label})
    WHERE toLower(n.{property_name}) = toLower($entity_value)
    WITH collect(n) AS nodes
    CALL apoc.refactor.mergeNodes(nodes, {{properties: 'overwrite', mergeRels: true}})
    YIELD node
    RETURN count(node) AS merged_count
    """
    try:
        with driver.session() as session:
            result = session.run(query, entity_value=entity_value)
            count = result.single()["merged_count"] if result.peek() else 0
            if count > 0:
                return f"SUCCESS: Deduplicazione topologica completata per '{entity_value}'."
            else:
                return f"INFO: Nessun cluster di duplicati rilevato per l'entità '{entity_value}'."
    except Exception as e:
        return f"EXCEPTION: Errore durante l'invocazione della procedura APOC: {e}"