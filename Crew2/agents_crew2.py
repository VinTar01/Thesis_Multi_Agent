import os
from dotenv import load_dotenv
from crewai import Agent, LLM

# Importiamo i custom tools
from Crew2.tools_crew2 import *

load_dotenv()

# Configurazione del modello LLM
llm_neo4j = LLM(
    model="gemini-flash-lite-latest",
    api_key=os.getenv("GEMINI_API_KEY"), # 
    temperature=0.1 
)

# definisco l'agente amministratore db
agente_dba = Agent(
    role="Database Administrator Neo4j",
    goal="Prendere strutture JSON contenenti entità, proprietà testuali e relazioni e scriverle in un database a grafi Neo4j in modo sicuro ed efficiente.",
    backstory=(
        "Sei un ingegnere dei dati specializzato in grafi. "
        "Conosci perfettamente il linguaggio Cypher. La tua priorità assoluta è l'idempotenza: "
        "usi SEMPRE il comando MERGE al posto di CREATE per evitare di duplicare i nodi, "
        "e sai mappare in modo pulito le proprietà opzionali tramite il comando SET, ignorando rigorosamente i valori null. "
        "Prima di creare relazioni, ti assicuri che i nodi di partenza e arrivo esistano."
    ),
    tools=[execute_cypher_tool, apoc_merge_entities_tool],
    llm=llm_neo4j,
    verbose=True,
    allow_delegation=False
)