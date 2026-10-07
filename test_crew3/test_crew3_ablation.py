import os
import sys
import time
import requests
from dotenv import load_dotenv
from crewai import LLM

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Crew3.crew3_enrichment import crew_wikidata

load_dotenv()

# ==========================================
# 1. SETUP DELL'AMBIENTE DI TEST
# ==========================================
# Si seleziona un target con Q-ID noto e verificato per standardizzare l'input 
# e misurare esclusivamente le capacità generative (Text-to-SPARQL) dell'LLM.
NODO_TEST = {
    "nome": "Omicidio di Giulia Cecchettin",
    "label": "Case",
    "q_id": "Q123558369"
}

# LLM Base: Isolato dal framework agentico per le Varianti A e B.
llm_base = LLM(
    model="gemini-flash-lite-latest",
    temperature=0.0,
    api_key=os.getenv("GEMINI_API_KEY")
)

def testa_sintassi_sparql(query: str) -> str:
    """
    Simulatore dell'Execution Accuracy.
    Interroga l'endpoint Wikidata per validare matematicamente la correttezza 
    sintattica (HTTP 200 vs 400) e la correttezza semantica (presenza di risultati 
    vs grafo vuoto a causa di filtri troppo restrittivi o assenza di OPTIONAL).
    """
    url = "https://query.wikidata.org/sparql"
    headers = {"User-Agent": "GraceAblation/1.0", "Accept": "application/sparql-results+json"}
    try:
        resp = requests.get(url, params={'query': query}, headers=headers)
        if resp.status_code == 400:
            return "ERRORE SINTATTICO (HTTP 400 - Compilazione SPARQL fallita)"
        
        dati = resp.json()
        risultati = dati.get("results", {}).get("bindings", [])
        
        if not risultati:
            return "ESECUZIONE OK, ZERO RISULTATI (Errore Semantico: Omissione costrutto OPTIONAL?)"
        return "SUCCESSO (Sintassi e Semantica validate)"
    except Exception as e:
        return f"ECCEZIONE A RUNTIME (Rete/Parsing): {e}"


# ==========================================
# 2. VARIANTE A: LLM ZERO-SHOT (NAIVE PROMPTING)
# ==========================================
def esegui_variante_a():
    """Valuta il comportamento del Foundation Model privo di costrutti ontologici."""
    print("\n--- [VARIANTE A] PROMPT ZERO-SHOT GENERICO ---")
    prompt_a = f"""
    Sei un assistente SPARQL. Scrivi una query per estrarre le proprietà geografiche 
    e temporali per l'entità Wikidata con Q-ID {NODO_TEST['q_id']}.
    Restituisci ESCLUSIVAMENTE il codice SPARQL senza markdown.
    """
    
    start_time = time.time()
    try:
        raw_response = llm_base.call([{"role": "user", "content": prompt_a}])
        query = raw_response.replace("```sparql", "").replace("```", "").strip()
        latenza = time.time() - start_time
        
        print(f"[Query Generata]:\n{query[:300]}...\n")
        esito = testa_sintassi_sparql(query)
        print(f"Esito Execution: {esito}")
        print(f"Latenza        : {latenza:.2f} s")
    except Exception as e:
        print(f"Fallimento Inferenza: {e}")


# ==========================================
# 3. VARIANTE B: KNOWLEDGE INJECTION (PROMPT ENGINEERING, NO AGENT)
# ==========================================
def esegui_variante_b():
    """
    Valuta l'impatto del Prompt Engineering. Viene fornito lo schema ontologico 
    (le direttive esatte di Crew 3) ma senza loop di retroazione (ReAct) né Tool.
    """
    print("\n--- [VARIANTE B] KNOWLEDGE INJECTION (No ReAct, No Tool) ---")
    
    prompt_b = f"""
    Hai ricevuto l'entità "{NODO_TEST['nome']}" (Label: "{NODO_TEST['label']}").
    Corrisponde al Q-ID esatto: {NODO_TEST['q_id']}.
    
    Il tuo obiettivo è generare una query SPARQL per estrarre le proprietà fisiche, geografiche o temporali.
    ATTENZIONE FONDAMENTALE: Usa SEMPRE clausole OPTIONAL nelle tue query SPARQL. 
    
    Regole di estrazione (Label 'Case'):
    1. P585 (punto nel tempo) oppure P580 (data di inizio).
    2. P276 (luogo) se presente.
    
    Restituisci ESCLUSIVAMENTE il codice SPARQL generato.
    """
    
    start_time = time.time()
    try:
        raw_response = llm_base.call([{"role": "user", "content": prompt_b}])
        query = raw_response.replace("```sparql", "").replace("```", "").strip()
        latenza = time.time() - start_time
        
        print(f"[Query Generata]:\n{query[:300]}...\n")
        esito = testa_sintassi_sparql(query)
        print(f"Esito Execution: {esito}")
        print(f"Latenza        : {latenza:.2f} s")
    except Exception as e:
        print(f"Fallimento Inferenza: {e}")


# ==========================================
# 4. VARIANTE C: ARCHITETTURA PROPOSTA (MAS + REACT + TOOL)
# ==========================================
def esegui_variante_c():
    """Esecuzione della pipeline integrata. Valuta la capacità dell'agente di interrogare e auto-correggersi."""
    print("\n--- [VARIANTE C] ARCHITETTURA IBRIDA (Agente + ReAct + Tool) ---")
    start_time = time.time()
    try:
        risultato = crew_wikidata.kickoff(inputs={
            "nome_entita": NODO_TEST['nome'],
            "label_entita": NODO_TEST['label'],
            "q_id": NODO_TEST['q_id']
        })
        latenza = time.time() - start_time
        
        print("[Payload Estratto (JSON)]:")
        print(str(risultato).strip())
        print(f"Esito          : SUCCESSO (Astrazione semantica completata)")
        print(f"Latenza Totale : {latenza:.2f} s")
    except Exception as e:
        print(f"Fallimento MAS: {e}")


if __name__ == "__main__":
    print("=" * 70)
    print(" ABLATION STUDY: TEXT-TO-SPARQL GENERATION ")
    print("=" * 70)
    
    esegui_variante_a()
    time.sleep(3) 
    
    esegui_variante_b()
    time.sleep(3) 
    
    esegui_variante_c()
    
    print("\n" + "=" * 70)
    print(" FINE TEST ")
    print("=" * 70)