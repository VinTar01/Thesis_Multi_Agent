#i tasks sono ciò che gli agenti devono fare

from crewai import Task
from Crew1.agents_crew1 import agente_extraction #per assegnare i task agli agenti
from schemas import SchemaGrafo #per assegnare lo schema pydantic all'agente estrattore

#definito inizialmente per far fare ad un altro agente della crew la ricerca su wikipedia
#task_acquisizione = Task(
    #description=(
       # "Cerca su Wikipedia il caso di cronaca intitolato '{titolo_caso}'. "
       # "Usa il tool di ricerca per scaricare il testo. "
       # "Una volta ottenuto, DEVI obbligatoriamente passarlo al tool 'Filtro_Casi'. "
       # "Se il filtro restituisce 'SCARTATO', fermati immediatamente."
    # ),
   # expected_output="Il testo completo del caso, oppure 'SCARTATO'.",
    #agent=agente_ingestion,
#)

task_estrazione = Task(
    description=(
        "Sei un analista investigativo esperto in Knowledge Graphs. "
        "Il tuo compito vitale è estrarre una mappatura ESTREMA, ESAUSTIVA E COMPLETA del seguente caso di cronaca nera. "
        "Non puoi permetterti di omettere alcun dettaglio fisico o logico.\n\n"
        
        "Ecco il testo del caso di cronaca da analizzare:\n"
        "--------------------------------------------------\n"
        "{testo_caso}\n"
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
    ),
    expected_output="Un blocco JSON formattato esattamente come richiesto.",
    agent=agente_extraction
)


#ho provato a usare una versione del prompt senza specificare l'output dato che
    #uso pydantic per specificare il tipo di output del json e per validare se llm lo ha rispettato
    #il passaggio dello schema pydantic direttamente all'LLM non funziona a causa di
    # un parametro che viene aggiunto automaticamente e che da problemi con Gemini API
    #specifichiamo quindi direttamente il formato json nel prompt e usiamo lo schema pydantic
    #per vedere in automatico se l'llm a rispettao il formato(non ha inventato label ecc...)