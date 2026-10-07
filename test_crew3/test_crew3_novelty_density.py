import os
import sys
import json
import re
import time
import requests
from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Crew3.crew3_enrichment import crew_wikidata

load_dotenv()

# 1. CONNESSIONE NEO4J
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USERNAME", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "myThesis")

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


# 2. RICERCA DEL Q-ID COME FATTA NELL'ORCHESTRATORE 
def cerca_qid_wikidata(nome_entita: str) -> str | None:
    url = "https://www.wikidata.org/w/api.php"
    params = {"action": "wbsearchentities", "format": "json", "language": "it", "search": nome_entita}
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "GraceBench/1.0"})
        data = resp.json()
        if data.get("search"):
            return data["search"][0]["id"]
    except Exception:
        pass
    return None


# 3. RECUPERO DEI NODI DEL CAMPIONE DA NEO4J CON LE LORO PROPRIETA' ATTUALI
def recupera_campione_nodi(limite_minimo: int = 20) -> list[dict]:
    nomi_target = [
        # Casi
        "Delitto di Garlasco", "Delitto di Cogne", "Omicidio di Giulia Cecchettin",
        "Omicidio di Marta Russo", "Omicidio di Marco Vannini", "Delitto di Novi Ligure",
        "Delitto di via Poma",
        # Luoghi
        "Garlasco", "Cogne", "Roma", "Novi Ligure", "Ladispoli", "Vigonovo",
        "Università La Sapienza", "Via Poma",
        # Armi e Strumenti
        "Coltello da cucina", "Pistola Beretta", "Pistola calibro 22", 
        "Pistola calibro 9", "Tagliacarte", "Arma da taglio", "Fucile"
    ]
    
    nodi = []
    
    # Tentativo 1: Recupero dei nodi esatti dalla lista target
    query_esatta = """
    MATCH (n)
    WHERE n.name IN $nomi_target AND (n:Location OR n:Weapon OR n:Case)
    RETURN n.id AS id, n.name AS name, labels(n)[0] AS label, keys(n) AS proprieta_attuali
    """
    
    try:
        with driver.session() as session:
            result = session.run(query_esatta, nomi_target=nomi_target)
            for r in result:
                nodi.append({
                    "id": r["id"], 
                    "name": r["name"], 
                    "label": r["label"],
                    "props_keys": r["proprieta_attuali"]
                })
    except Exception as e:
        print(f"Errore query esatta Neo4j: {e}")

    # Tentativo 2 (Fallback): Se i nomi esatti non bastano a raggiungere il num minimo del campione, estraiamo nodi extra
    if len(nodi) < limite_minimo:
        print(f"Trovati solo {len(nodi)} nodi target esatti. Integrazione con altri nodi rilevanti dal DB...")
        nodi_id_esistenti = [n["id"] for n in nodi]
        
        query_extra = """
        MATCH (n)
        WHERE (n:Location OR n:Weapon OR n:Case) 
          AND n.name IS NOT NULL 
          AND NOT n.id IN $esclusi
        RETURN n.id AS id, n.name AS name, labels(n)[0] AS label, keys(n) AS proprieta_attuali
        LIMIT $limite
        """
        try:
            with driver.session() as session:
                result_extra = session.run(query_extra, esclusi=nodi_id_esistenti, limite=(limite_minimo - len(nodi)))
                for r in result_extra:
                    nodi.append({
                        "id": r["id"], 
                        "name": r["name"], 
                        "label": r["label"],
                        "props_keys": r["proprieta_attuali"]
                    })
        except Exception as e:
            print(f"Errore query fallback Neo4j: {e}")
            
    return nodi


# 4. ESECUZIONE DEL TEST (NOVELTY ANALYSIS)
if __name__ == "__main__":
    print("=" * 70)
    print(" AVVIO TEST: GRAPH DENSITY E INFORMATION GAIN (NOVELTY ANALYSIS) ")
    print("=" * 70)

    nodi = recupera_campione_nodi(limite_minimo=20)
    if not nodi:
        print("Nessun nodo target trovato. Controlla il database Neo4j.")
        sys.exit(1)

    print(f"Estratti {len(nodi)} nodi. Inizio arricchimento simulato...\n")

    statistiche = {
        "nodi_processati": 0,
        "totale_proprieta_pre": 0,
        "totale_proprieta_post": 0,
        "nuove_proprieta_scoperte": 0
    }

    for idx, nodo in enumerate(nodi, 1):
        nome = nodo["name"]
        label = nodo["label"]
        props_pre = set(nodo["props_keys"])
        num_pre = len(props_pre)
        
        print(f"[{idx}/{len(nodi)}] Analisi: '{nome}' ({label})")
        print(f"    -> Proprietà attuali in DB : {num_pre} {list(props_pre)}")

        # 1. Ricerca del Q-ID
        qid = cerca_qid_wikidata(nome)
        if not qid:
            print("    -> Q-ID non trovato. Salto.\n")
            continue

        # 2. Invocazione dell'Agente 3
        try:
            risultato = crew_wikidata.kickoff(inputs={
                "nome_entita": nome,
                "label_entita": label,
                "q_id": qid
            })
            
            output_str = str(risultato).strip()
            
            # Estraiamo il JSON dalla risposta dell'agente
            match_json = re.search(r"\{.*\}", output_str, re.DOTALL)
            if match_json:
                dati_nuovi = json.loads(match_json.group(0))
                # Pulizia chiavi di servizio generate dall'agente
                dati_nuovi.pop("trovato", None)
                dati_nuovi.pop("wikidata_id", None)
                
                # Calcolo del guadagno di informazioni
                # Le chiavi che ci restituisce l'agente sono nuove proprietà scoperte
                chiavi_nuove = set(dati_nuovi.keys())
                num_nuove = len(chiavi_nuove)
                
                if num_nuove > 0:
                    print(f"    -> Dati estratti da Agent 3: {dati_nuovi}")
                    print(f"    -> INFORMAZIONI AGGIUNTE   : +{num_nuove} proprietà ({list(chiavi_nuove)})")
                    
                    statistiche["nodi_processati"] += 1
                    statistiche["totale_proprieta_pre"] += num_pre
                    statistiche["totale_proprieta_post"] += (num_pre + num_nuove)
                    statistiche["nuove_proprieta_scoperte"] += num_nuove
                else:
                    print("    -> Nessuna nuova proprietà utile trovata su Wikidata (trovato: false).")
            else:
                print("    -> Formato JSON non valido restituito dall'agente.")
                
        except Exception as e:
            print(f"    -> Errore esecuzione Agente: {e}")

        # Rispetto dei limiti API Google e Wikidata
        print("    [Pausa di sicurezza 8s...]\n")
        time.sleep(8)


    # 5. STAMPA REPORT FINALE
    
    print("=" * 70)
    print(" REPORT FINALE: GRAPH DENSITY E INFORMATION GAIN ")
    print("=" * 70)
    
    if statistiche["nodi_processati"] > 0:
        densita_pre = statistiche["totale_proprieta_pre"] / statistiche["nodi_processati"]
        densita_post = statistiche["totale_proprieta_post"] / statistiche["nodi_processati"]
        incremento_perc = (statistiche["nuove_proprieta_scoperte"] / statistiche["totale_proprieta_pre"]) * 100
        
        print(f"Nodi elaborati con successo (trovati in WD) : {statistiche['nodi_processati']}")
        print(f"Densità media pre-Agente 3                  : {densita_pre:.2f} proprietà per nodo")
        print(f"Densità media post-Agente 3                 : {densita_post:.2f} proprietà per nodo")
        print(f"Proprietà Totali Nuove Aggiunte (Novelty)   : {statistiche['nuove_proprieta_scoperte']}")
        print(f"Information Gain Relativo                   : +{incremento_perc:.1f}% di densità semantica")
    else:
        print("Nessun nodo è stato arricchito con successo. Verifica i Q-ID o l'output dell'agente.")
    print("=" * 70)