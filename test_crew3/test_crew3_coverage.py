import os
import sys
import time
import requests
from dotenv import load_dotenv
from neo4j import GraphDatabase
from crewai import LLM

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Crew3.tools_crew3 import interroga_wikidata_sparql

load_dotenv()

# ===============================
# CONNESSIONE E DATASET 
# ==========================
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "myThesis")
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

def recupera_nodi_campione(limite: int = 20) -> list[dict]:
    """Isola un gruppo entità eterogeneo (Vittime, Strumenti, Luoghi) dal grafo locale."""
    nomi_target = [
        "Giulia Cecchettin", "Filippo Turetta", "Chiara Poggi", "Alberto Stasi",
        "Samuele Lorenzi", "Annamaria Franzoni", "Marta Russo", "Giovanni Scattone",
        "Marco Vannini", "Antonio Ciontoli", "Simonetta Cesaroni", "Erika De Nardo",
        "Delitto di Garlasco", "Omicidio di Giulia Cecchettin", "Delitto di Cogne",
        "Via Poma", "Garlasco", "Cogne", "Coltello da cucina", "Pistola Beretta"
    ]
    
    query = """
    MATCH (n) WHERE n.name IN $nomi_target
    RETURN n.id AS id, n.name AS name, labels(n)[0] AS label
    """
    
    nodi = []
    try:
        with driver.session() as session:
            result = session.run(query, nomi_target=nomi_target)
            for r in result:
                nodi.append({"id": r["id"], "name": r["name"], "label": r["label"]})
    except Exception as e:
        print(f"[DB ERROR] Inizializzazione target fallita: {e}")
        
    if len(nodi) < 5:
        print("[INFO] Fallback su topologia limitrofa...")
        query_fallback = """
        MATCH (c:Case)<-[:INVOLVED_IN|IS_VICTIM_OF|COMMITTED|OCCURRED_AT]-(n)
        WHERE n.name IS NOT NULL
        RETURN DISTINCT n.id AS id, n.name AS name, labels(n)[0] AS label LIMIT $limite
        """
        try:
            with driver.session() as session:
                res = session.run(query_fallback, limite=limite)
                nodi = [{"id": r["id"], "name": r["name"], "label": r["label"]} for r in res]
        except Exception as e:
            pass
            
    return nodi

llm = LLM(
    model="gemini-flash-lite-latest",
    temperature=0.0,
    api_key=os.getenv("GEMINI_API_KEY")
)

# ==============================================================================
# ALGORITMI DI ENTITY LINKING (A vs B)
# ==============================================================================

def metodo_a_llm_sparql(nodo_id: str, nodo_nome: str, nodo_label: str) -> str | None:
    """
    Delega all'LLM l'individuazione autonoma del Q-ID. 
    Vulnerabile ad allucinazioni sugli ID interni di Neo4j.
    """
    prompt = f"""
    Sei un assistente semantico. Trova il Q-ID di Wikidata per questa entità:
    ID interno: "{nodo_id}" | Nome: "{nodo_nome}" | Tipo: "{nodo_label}"
    Scrivi una query SPARQL SELECT per individuare la variabile item corrispondente.
    Restituisci ESCLUSIVAMENTE il codice della query.
    """
    try:
        raw_response = llm.call([{"role": "user", "content": prompt}]).strip()
        query_sparql = raw_response.replace("```sparql", "").replace("```", "").strip()
        risultato_raw = interroga_wikidata_sparql.run(query=query_sparql)
        
        if "Errore" in risultato_raw or risultato_raw == "[]":
            return None

        import ast
        risultati = ast.literal_eval(risultato_raw)
        if risultati and len(risultati) > 0:
            for k in risultati[0]:
                val = risultati[0][k].get("value", "")
                if "/entity/Q" in val:
                    return val.split("/entity/")[-1]
    except Exception:
        return None
    return None


def metodo_b_hybrid_search(nome_entita: str) -> str | None:
    """(Architettura Proposta) Entity Resolution via Fuzzy API deterministica."""
    url = "https://www.wikidata.org/w/api.php"
    params = {"action": "wbsearchentities", "format": "json", "language": "it", "search": nome_entita}
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "GraceBench/1.0"})
        data = resp.json()
        if data.get("search"):
            return data["search"][0]["id"]
    except Exception:
        return None
    return None


def recupera_tipo_wikidata(q_id: str) -> str:
    """Interroga P31 (Instance Of) per validare l'allineamento ontologico (Semantic Shift)."""
    query = f"""
    SELECT ?typeLabel WHERE {{
      wd:{q_id} wdt:P31 ?type.
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
    }} LIMIT 1
    """
    url = "https://query.wikidata.org/sparql"
    headers = {"User-Agent": "GraceBench/1.0", "Accept": "application/sparql-results+json"}
    try:
        resp = requests.get(url, params={'query': query}, headers=headers, timeout=5)
        bindings = resp.json().get("results", {}).get("bindings", [])
        if bindings:
            return bindings[0]["typeLabel"]["value"].lower()
    except Exception:
        pass
    return "sconosciuto"

# ==============================================================================
# ESECUZIONE DEL BENCHMARK
# ==============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print(" ENTITY LINKING COVERAGE & SEMANTIC SHIFT ANALYSIS ")
    print("=" * 70)

    nodi = recupera_nodi_campione(limite=20)
    if not nodi:
        print("[FATAL] Dataset inaccessibile.")
        sys.exit(1)

    stats = {"totale": len(nodi), "successo_a": 0, "successo_b": 0, "semantic_shifts_b": 0}

    # Definizioni ontologiche ristrette per il controllo semantico
    ontologia_mapping = {
        "Person": ["umano", "human", "essere umano", "donna", "uomo"],
        "Location": ["comune", "città", "frazione", "luogo", "stato", "regione", "city", "edificio", "istituto"],
        "Weapon": ["arma", "pistola", "coltello", "weapon", "fucile"],
        "Case": ["omicidio", "delitto", "caso", "evento", "processo", "strage", "murder"]
    }

    for idx, n in enumerate(nodi, start=1):
        nid, name, label = n["id"], n["name"], n["label"]
        print(f"\n[{idx}/{stats['totale']}] Target: '{name}' (Neo4j Label: {label})")

        qid_a = metodo_a_llm_sparql(nid, name, label)
        if qid_a:
            stats["successo_a"] += 1
            print(f"  -> Metodo A (LLM) : [MATCH] Q-ID: {qid_a}")
        else:
            print(f"  -> Metodo A (LLM) : [MISS]")

        qid_b = metodo_b_hybrid_search(name)
        if qid_b:
            stats["successo_b"] += 1
            tipo_reale = recupera_tipo_wikidata(qid_b)
            print(f"  -> Metodo B (API) : [MATCH] Q-ID: {qid_b} (Wikidata P31: {tipo_reale})")

            keywords_attese = ontologia_mapping.get(label, [])
            match_ontologico = any(kw in tipo_reale for kw in keywords_attese) if keywords_attese else True
            
            if not match_ontologico:
                stats["semantic_shifts_b"] += 1
                print(f"     [WARNING] Semantic Shift Rilevato! Ontologia attesa incompatibile con l'istanza Wikidata.")
        else:
            print(f"  -> Metodo B (API) : [MISS]")

        time.sleep(2)

    cov_a = (stats["successo_a"] / stats["totale"]) * 100
    cov_b = (stats["successo_b"] / stats["totale"]) * 100
    shift_rate = (stats["semantic_shifts_b"] / stats["successo_b"] * 100) if stats["successo_b"] > 0 else 0

    print("\n" + "=" * 70)
    print(" RISULTATI FINALI ")
    print("=" * 70)
    print(f"Coverage Metodo A (LLM SPARQL)  : {cov_a:.2f}% ({stats['successo_a']}/{stats['totale']})")
    print(f"Coverage Metodo B (Hybrid API)  : {cov_b:.2f}% ({stats['successo_b']}/{stats['totale']})")
    print(f"Semantic Shift Rate (Metodo B)  : {shift_rate:.2f}% ({stats['semantic_shifts_b']}/{stats['successo_b']})")
    print("=" * 70)