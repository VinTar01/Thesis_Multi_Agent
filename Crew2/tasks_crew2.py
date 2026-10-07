from crewai import Task
from Crew2.agents_crew2 import agente_dba

task_ingestion_db = Task(
    description=(
        "Hai a disposizione il seguente JSON estratto da un caso di cronaca:\n"
        "--------------------------------------------------\n"
        "{json_da_inserire}\n"
        "--------------------------------------------------\n\n"
        
        "Il tuo compito è scrivere ed eseguire query Cypher per popolare il database Neo4j. "
        "REGOLE DA RISPETTARE:\n"
        "1. Usa SEMPRE 'MERGE (n:Label {{id: \"id_nodo\"}})' per i nodi, impostando le proprietà di base con 'SET n.name = \"nome\"'.\n"
        "2. GESTIONE DELLE PROPRIETÀ OPZIONALI: I nodi (in particolare 'Person') nel JSON possono contenere le proprietà 'role', 'gender', 'age' e 'profession'. "
        "Se il JSON riporta un valore testuale valido (es. \"age\": \"26\"), aggiungilo alla clausola SET (es. SET n.age = \"26\", n.role = \"Vittima\"). "
        "Se il JSON riporta il valore null, DEVI IGNORARE quella proprietà e NON inserirla nella query Cypher (NON scrivere SET n.age = \"null\").\n"
        "3. Crea le relazioni usando MERGE dopo aver fatto il MATCH dei due nodi.\n"
        "4. Usa il tool 'Esegui_Query_Cypher' per iniettare i dati. Puoi unire tutte le istruzioni MERGE in una singola grande query per risparmiare tempo e token.\n"
        "5. Se noti anomalie o possibili duplicati evidenti, che differiscono soltanto per nome case sensitive ecc...\n"
        ", puoi usare il tool 'Deduplica_Entita_APOC'."
    ),
    expected_output="Un messaggio che conferma il successo dell'inserimento nel database tramite il tool.",
    agent=agente_dba
)