from crewai import Crew, Process
from Crew2.agents_crew2 import agente_dba
from Crew2.tasks_crew2 import task_ingestion_db

crew_neo4j_writer = Crew(
    agents=[agente_dba],
    tasks=[task_ingestion_db],
    process=Process.sequential,
    verbose=True
)