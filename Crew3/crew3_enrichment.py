from crewai import Crew, Process
from Crew3.agents_crew3 import agente_ricercatore_lod
from Crew3.tasks_crew3 import task_ricerca_wikidata

crew_wikidata = Crew(
    agents=[agente_ricercatore_lod],
    tasks=[task_ricerca_wikidata],
    process=Process.sequential,
    verbose=True
)