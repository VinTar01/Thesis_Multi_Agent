#QUESTO FILE NON VIENE USATO AL MOMENTO DALL'AGENTE


#CUSTOM TOOL WIKIPEDIA NON VIENE USATO A CAUSA DELLE CHIAMATE API 
import wikipedia
from crewai.tools import tool #decoratore per tool LangChain ma compatibile con CrewAI

# Forza il wrapper a interrogare esclusivamente it.wikipedia.org
wikipedia.set_lang("it")
# Una soluzione che permette di superare venetuali blocchi anti-bot di wikipedia
wikipedia.set_user_agent("MyThesis/1.0 (progetto di ricerca accademica)")

#decoratore tool di langchain: prende la funzione python e geenra un file JSON Schema
#che indica nome funzione, cosa fa(prompt) e input consentiti
#LLM legge questo schema, capisce lo scopo dello strumento e
#quando serve, risponde generando un JSON con i parametri corretti. 
#LangChain prende quel JSON, esegue la tua funzione Python reale 
# e restituisce il risultato testuale all'agente.
#in un tool è obbligatorio il type hinting: serve a frcapire all'llm dell'agente cosa puo ricevere in input e che output deve dare
# query è il nome delle variabili di input delle funzioni python
#LLM per far funzionare il tool, deve riempire quel parametro grazie a LangChain
@tool("Cerca_Fascicolo_Wikipedia")
def search_wikipedia_tool(query: str) -> str: 
    #prompt per far capire all'LLM dell'agente che usa il tool quando e come usarlo
    """
    Cerca su Wikipedia Italia una pagina specifica e ne restituisce il testo grezzo.
    Utilizza questo strumento per scaricare il fascicolo di un caso di cronaca partendo dal titolo.
    Se la ricerca fallisce per ambiguità, lo strumento ti suggerirà alternative valide.
    """
    try:
        page = wikipedia.page(query)
        # Formatto l'output unendo il titolo e il testo integrale
        risultato_formattato = f"TITOLO: {page.title}\n\nTESTO COMPLETO:\n{page.content}"
        return risultato_formattato
    except wikipedia.exceptions.DisambiguationError as e:
        # Cruciale per il reasoning dell'agente: forniamo opzioni per fargli correggere il tiro da solo
        return f"Errore: la ricerca '{query}' è ambigua. Prova con uno di questi titoli esatti: {e.options[:5]}"
    except wikipedia.exceptions.PageError:
        return f"Errore: Nessuna pagina trovata per la query '{query}'."
    except Exception as e:
        return f"Errore imprevisto di rete o parsing: {e}"


def test_wikipedia():
    print("\n--- TEST WIKIPEDIA ---")
    risultato = search_wikipedia_tool.invoke({"query": "Mostro di Firenze"})
    print(f"{risultato[:150]}...")


    #Descrizione pipeline interazione tool agente
    #Quando avvii LangGraph, la prima cosa che fa in background è leggere
    # tutti i decoratori @tool definiti. LangChain traduce la funzione python in un JSONSchema
    # il JSONSchema è una breve presentazione che LangChain fa per l'LLM dell'agente che può usare il tool
    # specificando che ha a disposizione uno strumento che si chiama .....
    # che serve a ..... 
    # che si usa fornendomi un parametro query che deve essere una stringa di testo/ecc...
    # Un agente riceve da LangGraph un task: es: trova le info sul caso mostro di firenze
    # LLM dell'agente sfoglia i suoi strumenti e capisce che ha bisogno di Wikipedia eche
    # il tool wikipedia ha bisogno di una query stringa
    # LLm genera un output del tipo {
     #"nome_tool": "Cerca_Fascicolo_Wikipedia",
     #   "argomenti": {
     #   "query": "Mostro di Firenze"
     #   }
#   }

    #LangChain cattura questo JSON, vede che un agente con LLM vuole usare il tool di Wikipedia,
    # estrae il valore "Mostro di Firenze" e lo inserisce nella funzione Python:
    #search_wikipedia_tool(query="Mostro di Firenze")
    #la  funzione Python si attiva, si connette a internet, scarica la pagina e restituisce il testo formattato.

    #LangChain prende questo blocco di testo restituito dal tool 
    # e lo inserisce di nuovo nella chat con LLM, dicendogli
    #"Ecco il risultato del tool che hai chiamato....."
    #LLM vede che il Task è stato completato e passa il risultato all'Agente successivo (l'Extraction Expert).

#----------------------------------------------------------------------------------



@tool("Filtro_Casi") #NON VIENE USATO A CAUSA DELLE CHIAMATE API
def filter_case_tool(testo_scaricato: str) -> str:
    """
    Analizza il testo scaricato per verificare se si tratta di un'opera di finzione (film, romanzo, serie tv) o di una pagina biografica.
    Usa sempre questo tool PRIMA di passare il testo all'agente di estrazione.
    """
    # 1. Estraiamo il titolo e il testo dalla stringa formattata dal tool di Wikipedia
    titolo = ""
    testo = testo_scaricato
    if "TITOLO:" in testo_scaricato and "TESTO COMPLETO:" in testo_scaricato:
        parti = testo_scaricato.split("TESTO COMPLETO:")
        titolo = parti[0].replace("TITOLO:", "").strip()
        testo = parti[1].strip()

    testo_lower = testo.lower()
    titolo_lower = titolo.lower()
    
    # 2. Controllo Finzione e Media
    keyword_finzione = ["film", "romanzo", "regista", "attore", "cinema", "serie televisiva", "fiction", "cortometraggio", "romanzi"]
    for kw in keyword_finzione:
        if kw in testo_lower:
            return f"SCARTATO: Il testo contiene '{kw}', indicando che è un'opera di finzione o media."

    # 3. Controllo Biografia (applicando la tua logica originale)
    keyword_biografia = ["nato a", "nata a", "nato il", "nata il", "è stato un", "è stata una", "politico", "deputato", "senatore", "militare"]
    keyword_casi = ["omicidio", "delitto", "strage", "massacro", "caso", "attentato", "mistero"]

    has_bio = any(marker in testo_lower for marker in keyword_biografia)
    has_case_title = any(kw in titolo_lower for kw in keyword_casi)

    if has_bio and not has_case_title:
        return f"SCARTATO (Biografia Persona): Il titolo '{titolo}' non indica un caso e il testo descrive una persona."
            
    return "VALIDO: Il caso è un evento di cronaca reale."


def test_filter():
    print("\n--- TEST FILTRO EURISTICO ---")
    
    # 1. Simuliamo un testo di cronaca reale (dovrebbe passare)
    testo_valido = "TITOLO: Omicidio di Test\nTESTO COMPLETO:\nQuesto è un grave delitto avvenuto in Campania nel 1990."
    print("Test 1 (Caso Valido):", filter_case_tool.invoke({"testo_scaricato": testo_valido}))
    
    # 2. Simuliamo la pagina di un film (dovrebbe essere scartato per la parola "film"/"regista")
    testo_film = "TITOLO: Il delitto perfetto\nTESTO COMPLETO:\nUn famoso film diretto da un noto regista."
    print("Test 2 (Film):", filter_case_tool.invoke({"testo_scaricato": testo_film}))
    
    # 3. Simuliamo una biografia senza parole chiave criminali nel titolo (dovrebbe essere scartata)
    testo_bio = "TITOLO: Mario Rossi\nTESTO COMPLETO:\nMario Rossi nato a Napoli, è stato un politico italiano."
    print("Test 3 (Biografia):", filter_case_tool.invoke({"testo_scaricato": testo_bio}))


#inserisci test filter

#----------------------------------------------------------------------------------------

if __name__ == "__main__":
    
    # test_wikipedia()
    # test_cypher()
    # test_apoc()
     test_filter()