import os
import time
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional
from crewai import Agent, Task, Crew, Process, LLM

load_dotenv()

# ==========================================
# 1. SETUP SCHEMI PYDANTIC (Isolati per Test)
# ==========================================
# Definizione locale degli schemi per garantire che il test non subisca 
# alterazioni in caso di modifiche al file schemas.py principale.

class Entita(BaseModel):
    id: str = Field(..., description="Stringa univoca in minuscolo")
    label: str = Field(..., description="Una delle etichette obbligatorie")
    name: str = Field(..., description="Il nome leggibile")
    role: Optional[str] = Field(None, description="Ruolo se Person, altrimenti null")
    gender: Optional[str] = Field(None, description="Genere se Person, altrimenti null")
    age: Optional[str] = Field(None, description="Età se menzionata, altrimenti null")
    profession: Optional[str] = Field(None, description="Professione se menzionata, altrimenti null")

class Relazione(BaseModel):
    source_id: str = Field(..., description="Id nodo di partenza")
    target_id: str = Field(..., description="Id nodo di arrivo")
    type: str = Field(..., description="Tipo di relazione")

class SchemaGrafo(BaseModel):
    entities: List[Entita]
    relationships: List[Relazione]

# ==========================================
# 2. SETUP LLM
# ==========================================
gemini_llm = LLM(
    model="gemini-flash-lite-latest",
    temperature=0,
    api_key=os.getenv("GEMINI_API_KEY")
)

# ==========================================
# 3. FUNZIONE SCARICAMENTO TESTI (Stub di Rete)
# ==========================================
def scarica_testo_caso(titolo: str) -> str:
    """Recupera il testo sorgente da analizzare simulando l'ingestion reale."""
    url = "https://it.wikipedia.org/w/api.php"
    params = {
        "action": "query", 
        "prop": "extracts", 
        "explaintext": True, 
        "titles": titolo, 
        "format": "json", 
        "redirects": 1
    }
    headers = {"User-Agent": "GraceBench/1.0 (Tesi AI Benchmark)"}
    try:
        risposta = requests.get(url, params=params, headers=headers)
        risposta.raise_for_status()
        pagine = risposta.json().get("query", {}).get("pages", {})
        for page_id, info in pagine.items():
            return info.get("extract", "")
    except Exception as e: 
        print(f"[API ERROR] Errore download da Wikipedia per '{titolo}': {e}")
        return ""
    return ""

# ==========================================
# 4. DEFINIZIONE AGENTE E TASK (Telemetry Wrapper)
# ==========================================
def run_crewai_extraction(testo_caso: str):
    """
    Wrapper di esecuzione. Incapsula la creazione dell'agente e del task al solo scopo
    di tracciare il tempo di esecuzione (Latenza) e l'utilizzo dei Token.
    Restituisce una tupla contenente (Latenza in secondi, Token totali, Risultato generato).
    """
    start_time = time.time()
    
    agente_extraction = Agent(
        role='Esperto di Profilazione ed Estrazione Dati',
        goal='Analizzare i testi dei casi di cronaca ed estrarre entità, i loro attributi anagrafici/investigativi e le relazioni strutturate.',
        backstory=(
            "Sei un ingegnere della conoscenza specializzato in investigazioni e profilazione. "
            "La tua abilità è leggere testi complessi e mappare con precisione chirurgica "
            "i nodi, gli archi e le caratteristiche specifiche delle persone coinvolte (età, genere, ruolo), "
            "rispettando rigorosamente gli schemi dati richiesti."
        ),
        tools=[], 
        llm=gemini_llm,
        verbose=False # Disattivato per pulire l'output console durante il benchmark
    )

    descrizione_task = (
        "Sei un analista investigativo esperto in Knowledge Graphs. "
        "Il tuo compito vitale è estrarre una mappatura ESTREMA, ESAUSTIVA E COMPLETA del seguente caso di cronaca nera. "
        "Non puoi permetterti di omettere alcun dettaglio fisico o logico.\n\n"
        
        "Ecco il testo del caso di cronaca da analizzare:\n"
        "--------------------------------------------------\n"
        f"{testo_caso}\n"
        "--------------------------------------------------\n\n"
        
        "ATTENZIONE - DIVIETO DI ALLUCINAZIONI E DI PIGRIZIA:\n"
        "1. Estrai SOLO le informazioni esplicitamente menzionate. Non inventare nulla.\n"
        "2. DIVIETO DI PIGRIZIA: Devi estrarre TUTTI i nodi possibili presenti nel testo. Non fermarti ai soli nomi delle persone. "
        "La scena del crimine (Evidence, Weapon, Location) è più importante delle persone stesse. Se salti le prove, l'indagine fallirà.\n\n"

        "ETICHETTE OBBLIGATORIE DA RICERCARE NEL TESTO:\n"
        "- Case: L'evento criminale o caso giudiziario (es. Delitto di Garlasco).\n"
        "- Person: Vittime, Sospettati, Assassini, Testimoni, Avvocati, PM.\n"
        "- Location: Tutte le macro-aree (città) e micro-ambienti (stanze, villette).\n"
        "- Weapon: L'arma del delitto, se menzionata.\n"
        "- Evidence: Esclusivamente tracce fisiche, biologiche o reperti materiali (sangue, bossoli, impronte).\n"
        "- Statement: Sintesi di dichiarazioni, testimonianze o alibi (es. 'Afferma di aver lavorato al computer').\n"
        "- Motive: Il movente (es. gelosia, ragioni economiche, pedopornografia).\n"
        "- Charge: Capi d'imputazione o reati formali (es. omicidio volontario, falsa testimonianza).\n\n"
        
        "REGOLE PER L'ESTRAZIONE DELLE PROPRIETÀ DEI NODI:\n"
        "I nodi di tipo 'Person' richiedono l'estrazione di attributi specifici.\n"
        "- 'gender' e 'role': Sono OBBLIGATORI SOLO se la label è 'Person'. Dedurrai il genere dal nome o dai pronomi, e il ruolo (es. Vittima, Sospettato, Testimone, Inquirente) dal contesto del caso. Per tutte le altre label, imposta questi campi a null.\n"
        "- 'age' e 'profession': Estraili SOLO SE sono scritti esplicitamente nel testo per quella persona. Se non sono menzionati, restituisci null. Non inventare o dedurre età o professioni non dichiarate.\n\n"

        "REGOLE FONDAMENTALI PER LE RELAZIONI (RISPETTA LA DIREZIONE):\n"
        "- COMMITTED: Person (Assassino/Colpevole) -> Case\n"
        "- IS_SUSPECTED_IN: Person (Sospettato) -> Case\n"
        "- IS_VICTIM_OF: Person (Vittima) -> Case\n"
        "- INVESTIGATES: Person (PM/Polizia) -> Case\n"
        "- DEFENDS: Person (Avvocato) -> Person (Imputato)\n"
        "- INVOLVED_IN: Person (Testimone/Parente) -> Case\n"
        "- OCCURRED_AT: Case -> Location\n"
        "- WITHIN: Location (micro) -> Location (macro)\n"
        "- USED_IN: Weapon -> Case\n"
        "- FOUND_AT: Evidence/Weapon -> Location\n"
        "- HAS_MOTIVE: Case -> Motive\n"
        "- LEFT_EVIDENCE: Person -> Evidence\n"
        "- LOCATED_IN: Person -> Location\n"
        "- MADE_STATEMENT: Person -> Statement\n"
        "- RELATES_TO: Statement -> Case/Location\n"
        "- CHARGED_WITH: Person -> Charge\n"
        "- INCLUDES_CHARGE: Case -> Charge\n"
        "- OWNS_WEAPON: Person -> Weapon\n\n"

        "CHECKLIST DI AUTOCONTROLLO:\n"
        "1. Hai mappato la scena del crimine? Ci sono Evidence o Weapon nel tuo JSON se erano nel testo?\n"
        "2. Hai invertito IS_VICTIM_OF? (Sbagliato: Case->Person. Corretto: Person->Case).\n"
        "3. Hai invertito INCLUDES_CHARGE? (Sbagliato: Charge->Case. Corretto: Case->Charge).\n"
        "4. Ci sono nodi orfani? Ogni entità in 'entities' DEVE apparire in 'relationships'.\n\n"

        "FORMATO DI OUTPUT RICHIESTO:\n"
        "Restituisci UNICAMENTE un blocco JSON valido che rispetti rigorosamente questo schema:\n"
        "```json\n"
        "{\n"
        "  \"entities\": [\n"
        "    {\n"
        "      \"id\": \"stringa univoca in minuscolo con underscore e prefisso (es. 'weapon_oggetto_contundente')\",\n"
        "      \"label\": \"una delle etichette obbligatorie sopra\",\n"
        "      \"name\": \"il nome leggibile\",\n"
        "      \"role\": \"se label è Person inserisci il ruolo (es. Vittima), altrimenti null\",\n"
        "      \"gender\": \"se label è Person inserisci il genere (es. Maschio/Femmina), altrimenti null\",\n"
        "      \"age\": \"età se menzionata nel testo, altrimenti null\",\n"
        "      \"profession\": \"professione se menzionata, altrimenti null\"\n"
        "    }\n"
        "  ],\n"
        "  \"relationships\": [\n"
        "    {\n"
        "      \"source_id\": \"id esatto del nodo di partenza\",\n"
        "      \"target_id\": \"id esatto del nodo di arrivo\",\n"
        "      \"type\": \"una delle relazioni obbligatorie sopra\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )

    # Iniezione del Guardrail Pydantic (output_pydantic)
    task_estrazione = Task(
        description=descrizione_task,
        expected_output="Un blocco JSON formattato esattamente come richiesto.",
        agent=agente_extraction,
        output_pydantic=SchemaGrafo
    )

    crew_estrazione = Crew(
        agents=[agente_extraction],
        tasks=[task_estrazione],
        process=Process.sequential,
        verbose=False
    )
    
    try:
        risultato = crew_estrazione.kickoff()
        
        # Accesso ai metadati di telemetria nativi di CrewAI
        token_totali = getattr(crew_estrazione.usage_metrics, 'total_tokens', 0)
        
        # Calcolo latenza assoluta del blocco estrattivo
        end_time = time.time()
        latenza = end_time - start_time
        
        return latenza, token_totali, risultato
    except Exception as e:
        print(f"[FATAL] Errore durante l'esecuzione della Crew: {e}")
        return 0, 0, None

# ==========================================
# 5. ESECUZIONE DEL TEST SUI CASI DI RIFERIMENTO
# ==========================================
# In questa sezione viene replicato, in un ambiente controllato e isolato, 
# l'esatto flusso di lavoro che l'agente esegue in produzione (nell'orchestratore) 
# per ogni singolo documento. 
# Iterando su un campione fisso di 6 casi di cronaca rappresentativi, il benchmark 
# simula il comportamento operativo reale al fine di quantificare empiricamente 
# il costo computazionale medio (Token consumati) e la latenza (Secondi per task) 
# richiesti dall'architettura agentica per il completamento di una singola estrazione.

if __name__ == "__main__":
    casi_wikipedia = [
        "Delitto di Cogne",
        "Delitto di via Poma",
        "Omicidio di Marta Russo",
        "Omicidio di Marco Vannini",
        "Omicidio di Giulia Cecchettin",
        "Delitto di Novi Ligure"
    ]
    
    risultati = []
    
    print("="*60)
    print(" AVVIO BENCHMARK: LATENZA E COSTO COMPUTAZIONALE (CREW 1)")
    print("="*60)

    for caso in casi_wikipedia:
        testo = scarica_testo_caso(caso)
        if not testo:
            continue
            
        print(f"\n[Benchmarking in corso] -> {caso}")
        
        tempo, token, esito = run_crewai_extraction(testo)
        
        if esito:
            risultati.append({"caso": caso, "tempo": tempo, "token": token})
            print(f"   -> Completato in {tempo:.2f} secondi.")
            print(f"   -> Token cumulativi sessione: {token}")
        else:
            print(f"   -> [FALLITO] Esecuzione interrotta.")
            
        # per evitare il superamento della quota API
        time.sleep(5)
        
    print("\n" + "="*60)
    print(" TELEMETRIA GLOBALE: SISTEMA MULTI-AGENTE ")
    print("="*60)
    if risultati:
        avg_tempo = sum(r['tempo'] for r in risultati) / len(risultati)
        
        # In base all'implementazione interna di CrewAI, il contatore token 
        # può risultare cumulativo sull'intera istanza. Estraiamo il valore finale.
        token_totali_sessione = risultati[-1]['token']
        avg_token = token_totali_sessione / len(risultati)
        
        print(f"Dataset processato con successo   : {len(risultati)}/{len(casi_wikipedia)}")
        print(f"Latenza Media di estrazione/caso  : {avg_tempo:.2f} secondi")
        print(f"Consumo Totale Token (Sessione)   : {token_totali_sessione}")
        print(f"Consumo Medio Stimato per Caso    : {avg_token:.0f} token")
    else:
        print("[WARNING] Nessun dato aggregabile. Verificare i log di errore.")
    print("="*60)