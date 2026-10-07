


#Serve a capire se le singole compoennti che verranno usate dagli agenti sono in funzione
#isolando eventuali errori


import os
from dotenv import load_dotenv #gestione del file env con le credenziali
from langchain_google_genai import ChatGoogleGenerativeAI #wrapper per gestire il modello google permettendola comunicazione standardizzata tra langchain e crewai
from neo4j import GraphDatabase

#carico il file env e ottengo le info dichiarate all'interno
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

#funzione principale che avvia il test
def run_diagnostics():
    print("Avvio diagnostica di sistema...\n")

    # 1. Diagnostica Gemini
    #definisco modello e chiave
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-flash-lite-latest",
            temperature=0,
            api_key=GEMINI_API_KEY
        )
        risposta = llm.invoke("Rispondi solo con 'OK' se la connessione è attiva.")
        
        # Gestione sicura del formato di risposta (stringa o lista)
        contenuto = risposta.content
        testo = contenuto[0].get("text", "") if isinstance(contenuto, list) else contenuto
        print(f"Connessione Gemini LLM: Stabilita ({testo.strip() if isinstance(testo, str) else testo})")
        
    except Exception as e:
        print(f"Errore connessione Gemini: {e}")

    # 2. Diagnostica Neo4j & APOC
    try:
        # Creazione del connection pool verso il server Neo4j locale
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("Connessione Neo4j: Stabilita")

        #apertura sessione con chiusura gestita autoaticamente
        with driver.session() as session:
            # Esecuzione di una query Cypher amministrativa
            # YIELD estrae solo il nome delle procedure per non sovraccaricare la memoria
            result = session.run(
                "SHOW PROCEDURES YIELD name "
                "WHERE name STARTS WITH 'apoc.refactor.mergeNodes' "
                "RETURN count(name) AS apoc_count"
            )
            # Estrazione del conteggio numerico (1 = procedura trovata, 0 = mancante)
            count = result.single()["apoc_count"]
            if count > 0:
                print("Plugin APOC (MergeNodes): Rilevato e pronto per eventuale Agente che deve usare la procedura ")
            else:
                print(" Attenzione: Procedura 'apoc.refactor.mergeNodes' non trovata nel DB.")
                
        driver.close()
    except Exception as e:
        print(f" Errore connessione Neo4j: {e}")

if __name__ == "__main__":
    run_diagnostics()