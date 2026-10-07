from crewai import Crew, Process
from pydantic import ValidationError
from Crew1.agents_crew1 import agente_extraction
from Crew1.tasks_crew1 import task_estrazione

from schemas import SchemaGrafo

# Mettiamo insieme gli agenti della Crew1 per estrarre i casi e le info(solo 1 per il problema delle chiamate api)
#abbiniamo il task all'agente
crew_estrazione_casi = Crew(
    agents=[agente_extraction],
    tasks=[task_estrazione],
    process=Process.sequential, 
    verbose=True
)











# Test di come LangGraph invocherà questa Crew in futuro
if __name__ == "__main__":
    print("Test di avvio Crew 1 sul Mostro di Firenze...")
    risultato = crew_estrazione_casi.kickoff(inputs={'titolo_caso': 'Mostro di Firenze'})
    
    print("\n==========================================")
    print("FASE DI VALIDAZIONE PYDANTIC (LOCALE)")
    print("==========================================")
    
    # 1. Puliamo l'output (spesso l'LLM aggiunge i backtick ```json ... ```)
    testo_grezzo = risultato.raw.strip()
    if testo_grezzo.startswith("```json"):
        testo_grezzo = testo_grezzo[7:]
    if testo_grezzo.startswith("```"):
        testo_grezzo = testo_grezzo[3:]
    if testo_grezzo.endswith("```"):
        testo_grezzo = testo_grezzo[:-3]
    testo_grezzo = testo_grezzo.strip()

    # 2. Pydantic valida il JSON
    try:
        grafo_validato = SchemaGrafo.model_validate_json(testo_grezzo)
        print("VALIDAZIONE SUPERATA! Nessuna allucinazione sintattica rilevata.")
        print(f"Estratti: {len(grafo_validato.entities)} Nodi e {len(grafo_validato.relationships)} Relazioni.")
        
        
        # print(grafo_validato.model_dump_json(indent=2))
        
    except ValidationError as e:
        print(" ERRORE DI VALIDAZIONE PYDANTIC:")
        print(e)