from crewai import Task
from Crew3.agents_crew3 import agente_ricercatore_lod

# Il task che verrà assegnato all'agente ricercatore
# L'orchestratore invierà al task il nome dell'entità, la sua label e il Q-ID esatto
task_ricerca_wikidata = Task(
    description="""
    Hai ricevuto l'entità "{nome_entita}" (Label in Neo4j: "{label_entita}").
    Un modulo Python ha già scansionato Wikidata e ha confermato che questa entità corrisponde al Q-ID esatto: {q_id}.
    
    Il tuo obiettivo è usare il tool 'Interroga_Wikidata_SPARQL' per interrogare il nodo {q_id} ed estrarne le proprietà fisiche, geografiche o temporali formattandole in modo chiaro.
    
    ATTENZIONE FONDAMENTALE: Usa SEMPRE clausole OPTIONAL nelle tue query SPARQL. Non dare mai per scontato che una proprietà esista.
    
    Regole di estrazione in base alla Label:
    
    - Se la Label è 'Case':
      Interroga il nodo {q_id} e recupera:
      1. P585 (punto nel tempo / data dell'evento) oppure P580 (data di inizio).
      2. P276 (luogo) se presente.
      
    - Se la Label è 'Weapon':
      Interroga il nodo {q_id} e recupera:
      1. P279 (sottoclasse di - es. per capire se è un'arma da taglio o da fuoco).
      2. P17 (paese di origine) o P176 (produttore), se presenti.
      
    - Se la Label è 'Location':
      Interroga il nodo {q_id} e recupera:
      1. P625 (coordinate geografiche).
      2. P131 (entità territoriale amministrativa in cui si trova, es. provincia/regione).
      
    Se la query SPARQL non restituisce risultati validi per le proprietà richieste, restituisci semplicemente un JSON con "trovato": false.
    """,
    expected_output="""Un blocco JSON valido e ben formato con le chiavi corrispondenti alle proprietà trovate. 
    Esempio per Location: {"wikidata_id": "Q123", "coordinates": "Point(12.49 41.89)", "located_in": "Lombardia"}
    Esempio per Case: {"wikidata_id": "Q456", "point_in_time": "2007-08-13", "location": "Garlasco"}
    Esempio per mancato ritrovamento di proprietà: {"trovato": false}""",
    agent=agente_ricercatore_lod
)