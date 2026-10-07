import os
from dotenv import load_dotenv
from crewai import Agent, LLM

# Importiamo il custom tool
from Crew3.tools_crew3 import interroga_wikidata_sparql

load_dotenv()

# Configurazione del modello LLM allineata alle altre Crew
llm_gemini = LLM(
    model="gemini-flash-lite-latest",
    api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.0 # Temperatura a 0 per generare codice SPARQL deterministico
)

agente_ricercatore_lod = Agent(
    role="Semantic Web Data Extractor",
    goal="Interrogare Q-ID specifici su Wikidata tramite SPARQL per estrarre proprietà spaziali, temporali e fisiche (macro-conoscenza).",
    backstory=(
        "Sei un ingegnere esperto di Linked Open Data e Semantic Web. "
        "Conosci perfettamente il linguaggio SPARQL e le ontologie di Wikidata. "
        "Sai che P585 indica la data di un evento (Case), P625 le coordinate geografiche (Location) e P279 la sottoclasse strutturale (Weapon). "
        "La tua regola d'oro per evitare fallimenti è usare SEMPRE clausole OPTIONAL nelle tue query SPARQL. "
        "Non allucini mai i dati: estrai e formatti in JSON solo i risultati esatti restituiti dall'endpoint pubblico."
    ),
    verbose=True,
    allow_delegation=False,
    llm=llm_gemini,
    tools=[interroga_wikidata_sparql]
)