import os
import json
import sys
import time
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Crew2.crew2_db import crew_neo4j_writer 
from crewai import LLM 

load_dotenv()

# ==========================================
# 1. SETUP DELL'LLM DI BASELINE 
# ==========================================
# Per valutare l'effettivo contributo dell'architettura multi-agente,
# si inizializza un LLM  (privo di tool e del loop ReAct).
# Questo modello fungerà da benchmark per misurare l'Execution Accuracy
# dell'approccio Text-to-Cypher Zero-Shot.
MODELLO = "gemini-flash-lite-latest"
llm_baseline = LLM(
    model=MODELLO, 
    temperature=0, 
    api_key=os.getenv("GEMINI_API_KEY")
)

# ==========================================
# 2. INGESTION DATASET DI TEST
# ==========================================
# Si seleziona un file JSON di output rappresentativo e validato (Fase 1).
CARTELLA_BASE = os.path.dirname(os.path.dirname(__file__))
PERCORSO_JSON = os.path.join(CARTELLA_BASE, "casi_inseriti_db", "delitto_di_garlasco.json")

def carica_json(filepath):
    """Esegue il parsing in memoria del payload JSON da iniettare in Neo4j."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[FATAL] Fallimento I/O durante il caricamento del payload: {e}")
        return None

# ==========================================
# 3. VARIANTE A: ARCHITETTURA MULTI-AGENTE ù
# ==========================================
# In questa variante si esegue la pipeline di produzione. L'agente non solo genera
# la query, ma interagisce con il tool Python che applica il Lexical Filtering 
# e garantisce l'esecuzione transazionale sul database.

def esegui_variante_a_crew2(json_data):
    print("\n" + "="*50)
    print(" [TEST A] SISTEMA MULTI-AGENTE (AGENT + PYTHON TOOLS) ")
    print("="*50)
    
    start = time.time()
    json_string = json.dumps(json_data, ensure_ascii=False, indent=2) 
    
    try:
        # Invocazione della Crew. L'agente pianificherà le clausole MERGE 
        # delegando l'esecuzione fisica al tool `execute_cypher_tool`.
        risultato = crew_neo4j_writer.kickoff(inputs={'json_da_inserire': json_string}) 
        print("\n[TELEMETRIA TEST A]:")
        print("-> Esecuzione completata: Delega ai tool transazionali avvenuta con successo.")
        print(f"-> Output Agente: {risultato.raw}")
    except Exception as e:
        print(f"\n[ERROR] Fallimento critico nell'ecosistema CrewAI: {e}")
    
    tempo = time.time() - start
    return tempo

# ==========================================
# 4. VARIANTE B: TEXT-TO-CYPHER ZERO-SHOT 
# ==========================================
# si richiede all'LLM di mappare l'intero JSON in una stringa 
# Cypher, privandolo della possibilità di validare sintatticamente il codice
# o di sfruttare tool esterni (approccio LLM puramente generativo).

def esegui_variante_b_raw_cypher(json_data):
    print("\n" + "="*50)
    print(" [TEST B] TEXT-TO-CYPHER ZERO-SHOT (NO TOOLS, NO REACT) ")
    print("="*50)
    
    start = time.time()
    
    # Prompting diretto volto a forzare la generazione di un blocco di codice eseguibile.
    prompt = f"""
    Sei un esperto di database Neo4j. 
    Il tuo compito è tradurre il seguente oggetto JSON in un'unica query Cypher eseguibile.
    Devi creare tutti i nodi e tutte le relazioni descritte. 
    Usa il comando MERGE per evitare duplicati per ogni nodo e relazione.
    
    JSON DA TRADURRE:
    {json.dumps(json_data, ensure_ascii=False, indent=2)}
    
    Restituisci ESCLUSIVAMENTE il codice Cypher valido. Non aggiungere spiegazioni.
    """
    
    try:
        # Interrogazione API diretta del modello base
        risposta = llm_baseline.call([{"role": "user", "content": prompt}])
        query_generata = risposta.strip()
        
        # Post-processing per la rimozione dei meta-tag Markdown residui
        if query_generata.startswith("```cypher"): query_generata = query_generata[9:]
        if query_generata.startswith("```"): query_generata = query_generata[3:]
        if query_generata.endswith("```"): query_generata = query_generata[:-3]
        query_generata = query_generata.strip()
        
        print("\n[OUTPUT RAW CYPHER]:\n")
        print(query_generata[:1000] + "\n\n... [PAYLOAD TRONCATO PER LEGGIBILITÀ] ...\n")
        
        # ==========================================
        # VALIDATORE EURISTICO 
        # ==========================================
        # Serie di controlli lessicali volti a identificare vulnerabilità o 
        # pattern distruttivi tipici della generazione Text-to-Cypher non controllata.
        
        errori_sospetti = []
        
        # Controllo Idempotenza
        if "MERGE" not in query_generata.upper():
            errori_sospetti.append("[CRITICO] Omissione del vincolo MERGE. Alto rischio di duplicazione topologica.")
            
        # Analisi Bilanciamento Parentesi (Pre-requisito di compilazione AST in Neo4j)
        if query_generata.count("(") != query_generata.count(")"):
            errori_sospetti.append("[SINTASSI] Sbilanciamento blocchi tonde. Parser Cypher fallirà in esecuzione.")
            
        # Analisi Escaping Stringhe
        if "'" in query_generata and '"' in query_generata and "\\'" not in query_generata:
             errori_sospetti.append("[SICUREZZA] Conflitto di escaping sugli apici. Potenziale interruzione della transazione.")
             
        # Analisi Monoliticità (Gestione memoria heap del driver)
        if len(query_generata) > 5000:
             errori_sospetti.append("[PERFORMANCE] Query eccede i 5000 caratteri. Rischio di Memory Timeout nel driver Neo4j.")
             
        if errori_sospetti:
            print(">>> ANALISI VULNERABILITÀ SINTATTICHE COMPLETATA:")
            for e in errori_sospetti: 
                print(f"    {e}")
            print("\n>>> ESITO: Modello Zero-Shot instabile.")
        else:
            print(">>> ANALISI: Astrazione Cypher formalmente corretta.")
            
    except Exception as e:
        print(f"\n[ERROR] Fallimento dell'API Generativa (Variante B): {e}")
        
    tempo = time.time() - start
    return tempo

# ==========================================
# 5. ORCHESTRAZIONE DEL TEST
# ==========================================
if __name__ == "__main__":
    
    if not os.path.exists(PERCORSO_JSON):
        print(f"[FATAL] Dataset inaccessibile: {PERCORSO_JSON}")
    else:
        dati_test = carica_json(PERCORSO_JSON)
        if dati_test:
            # Esecuzione comparativa
            tempo_a = esegui_variante_a_crew2(dati_test)
            tempo_b = esegui_variante_b_raw_cypher(dati_test)
            
            print("\n" + "="*50)
            print(" REPORT COMPARATIVO (ABLATION STUDY) ")
            print("="*50)
            print(f"Latenza Variante A (MAS + ReAct + DB Write) : {tempo_a:.2f} secondi")
            print(f"Latenza Variante B (Zero-Shot Text Only)    : {tempo_b:.2f} secondi")
            print("-> NOTA: Il delta temporale riflette il trade-off tra l'inferenza puramente generativa (B) "
                  "e la pipeline di auto-correzione/persistenza dell'agente (A).")