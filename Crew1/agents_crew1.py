import os
from dotenv import load_dotenv
from crewai import Agent, LLM #per la creazione degli agenti

# Importiamo i custom tools
#from Crew1.tools_crew1 import *

load_dotenv()

# L'LLM principale 
gemini_llm = LLM(
    model="gemini-flash-lite-latest",
    temperature=0,
    api_key=os.getenv("GEMINI_API_KEY")
)

# TEAM 1: 1 Agente

#chiamo la classe Agent di CrewAi per definire ruolo, obiettivo e 
#agente_ingestion = Agent(
    #grazie a CrewAI, i parametri compongono un contesto che verrà iniettato nel prompt dell'LLM
    # CrewAI legge i tools definiti nell'agente e aggancia il contesto ai prompt/docstring
    # dei tools e l'LLM comprende qualistrumenti ha a disposizione e come si usano
    #role='Specialista di Acquisizione e Filtraggio',
    #goal='Recuperare i fascicoli dei casi di cronaca nera da Wikipedia e scartare precisamente opere di finzione o biografie.',
    #backstory=(
       # "Sei un esperto investigativo inflessibile. Il tuo unico scopo è "
        #"garantire che nel sistema entrino solo report su veri casi di cronaca. "
        #"Usi i tuoi strumenti per cercare le pagine e filtrare il rumore."
    #),
    #tools=[search_wikipedia_tool, filter_case_tool],
   # llm=gemini_llm,
   # verbose=True # Stampa nel terminale i pensieri dell'agente (Reasoning)
#)

#esperto nell'estrazione di entità e relazioni dai testi grezzi
#l'agente deve restituire un JSON che poi possa essere letto dall'agente del Team 2
#che si occupa della creaione del grafo su neo4j
#potremmo chiedere direttamente all'LLm di restituire il JSON ma
# si può sfruttare CrewAi che usa una libreria Python chiamata Pydantic per la validazione dei dati
# Si definiscono le classi pydantic, queste vengono passate al task dell'agente
#CreaAI traduce in automatico le classi in un JSONSchema e lo inietta al prompt di gemini
# garantendo la struttura da ricevere in output e limitando le allucinazioni dell'LLM
#in caso di errore di gemini, pydantic blocca l'output, spiega 
# l'errore all'agente e lo costringe a correggersi da solo prima di far proseguire la pipeline
#controllare schemas.py per vedere la definizione della struttura dell'output
agente_extraction = Agent(
    role='Esperto di Profilazione ed Estrazione Dati',
    goal='Analizzare i testi dei casi di cronaca ed estrarre entità, i loro attributi anagrafici/investigativi e le relazioni strutturate.',
    backstory=(
        "Sei un ingegnere della conoscenza specializzato in investigazioni e profilazione. "
        "La tua abilità è leggere testi complessi e mappare con precisione chirurgica "
        "i nodi, gli archi e le caratteristiche specifiche delle persone coinvolte (età, genere, ruolo), "
        "rispettando rigorosamente gli schemi dati richiesti."
    ),
    tools=[], # L'estrazione usa solo le capacità di comprensione del testo dell'LLM
    llm=gemini_llm,
    verbose=True
)