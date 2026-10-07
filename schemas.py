#questo blocco pydantic verrà usato dall'agente dell'estrazione per forzare 
#a rispettare il formato di output
from pydantic import BaseModel, Field
from typing import List, Literal, Optional

#definisco i Literal, in questo modo l'LLM non creerà un JSON che contiene Entità e relazioni
#diverse da queste
LabelEntita = Literal["Case", "Person", "Location", "Weapon", "Evidence", "Statement", "Motive", "Charge"]
TipoRelazione = Literal["COMMITTED", "IS_SUSPECTED_IN", "IS_VICTIM_OF", "INVESTIGATES", "DEFENDS", "INVOLVED_IN", "OCCURRED_AT", "WITHIN", "USED_IN", "FOUND_AT", "HAS_MOTIVE", "OWNS_WEAPON", "LEFT_EVIDENCE", "LOCATED_IN", "MADE_STATEMENT", "RELATES_TO", "CHARGED_WITH", "INCLUDES_CHARGE"]

class Entita(BaseModel):
    id: str = Field(description="Formato: prefisso_nome. Es: 'person_mario_rossi' in minuscolo, senza spazi.")
    label: LabelEntita = Field(description="L'etichetta semantica del nodo.")
    name: str = Field(description="Il nome leggibile dell'entità.")
    
    # campi opzionali dedicati ai nodi Person (estratti da Crew 1)
    role: Optional[str] = Field(default=None, description="Ruolo nel caso (solo per Person), altrimenti null.")
    gender: Optional[str] = Field(default=None, description="Genere (solo per Person), altrimenti null.")
    age: Optional[str] = Field(default=None, description="Età se menzionata (solo per Person), altrimenti null.")
    profession: Optional[str] = Field(default=None, description="Professione se menzionata (solo per Person), altrimenti null.")


class Relazione(BaseModel):
    source_id: str = Field(description="ID del nodo di partenza (deve esistere in entities).")
    target_id: str = Field(description="ID del nodo di arrivo (deve esistere in entities).")
    type: TipoRelazione = Field(description="Il tipo di legame.")
    #properties: dict = Field(default_factory=dict, description="Dizionario per attributi extra dell'arco (es. {'data': '1990-10-12'}). Può essere vuoto.")

class SchemaGrafo(BaseModel):
    entities: List[Entita]
    relationships: List[Relazione]