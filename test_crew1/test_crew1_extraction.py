import json
import os
import difflib


# FUNZIONI DI SUPPORTO ALLA VALIDAZIONE SEMANTICA

def fuzzy_match(str1, str2, threshold=0.8):
    """
    Calcola la similarità basata su caratteri tra due stringhe.
    """
    if not str1 or not str2:
        return False
    return difflib.SequenceMatcher(None, str1.lower().strip(), str2.lower().strip()).ratio() >= threshold


def extract_graph_data(filepath):
    """
    Esegue il parsing del file JSON (sia Gold Standard che Predizione).
    Poiché le metriche di valutazione si basano sui nomi reali delle entità e non 
    sugli ID generati arbitrariamente dall'LLM, questa funzione mappa ogni ID al 
    suo 'name' leggibile e ricostruisce la topologia delle relazioni.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entities = data.get('entities', [])
    
    # Costruzione dizionario per risoluzione rapida ID -> Nome Leggibile
    id_to_name = {e['id']: e.get('name', '') for e in entities}
    
    # Normalizzazione delle chiavi strutturali (gestisce eventuali deviazioni minori dell'LLM)
    raw_relations = data.get('relationships') or data.get('relations') or []
    relationships = []
    
    for r in raw_relations:
        src_id = r.get('source_id') or r.get('source')
        tgt_id = r.get('target_id') or r.get('target')
        rel_type = r.get('type')
        
        # Risoluzione semantica: l'arco viene salvato come (Nome1, Tipo_Relazione, Nome2)
        src_name = id_to_name.get(src_id, '')
        tgt_name = id_to_name.get(tgt_id, '')
        
        if src_name and tgt_name:
            relationships.append((src_name, rel_type, tgt_name))
            
    return entities, relationships


def calculate_metrics(gold_items, pred_items, item_type="Entità"):
    """
    Motore di calcolo per le metriche di Information Retrieval.
    Calcola True Positives (TP), False Positives (FP) e False Negatives (FN) 
    per derivare Precision, Recall e F1-Score
    """
    tp = 0
    # Copia della lista per rimuovere gli elementi matchati (evita doppi conteggi)
    pred_pool = list(pred_items) 
    
    for gold in gold_items:
        match_found = False
        for pred in pred_pool:
            if item_type == "Entità":
                # Match Entità: Stessa Etichetta Ontologica e Nome simile (Fuzzy)
                if gold['label'] == pred['label'] and fuzzy_match(gold['name'], pred['name']):
                    match_found = True
                    pred_pool.remove(pred)
                    break
            else: 
                # Match Relazioni: Stessa Direzionalità, Stesso Tipo e Nodi simili
                g_src, g_type, g_tgt = gold
                p_src, p_type, p_tgt = pred
                if g_type == p_type and fuzzy_match(g_src, p_src) and fuzzy_match(g_tgt, p_tgt):
                    match_found = True
                    pred_pool.remove(pred)
                    break
                    
        if match_found:
            tp += 1

    # FP: Entità/Relazioni estratte dall'LLM ma non presenti nel Gold Standard (Allucinazioni)
    fp = len(pred_pool)
    # FN: Entità/Relazioni presenti nel Gold Standard ma ignorate dall'LLM (Omissioni)
    fn = len(gold_items) - tp

    # Calcolo Metriche
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return precision, recall, f1, tp, fp, fn

# ==========================================
# ESECUZIONE DELLA VALIDAZIONE
# ==========================================

def run_evaluation(gold_dir, pred_dir, case_mapping):
    """Itera il processo di valutazione sull'intero dataset di test e calcola le medie globali."""
    results = []
    
    for case_name, files in case_mapping.items():
        gold_path = os.path.join(gold_dir, files['gold'])
        pred_path = os.path.join(pred_dir, files['pred'])
        
        # Verifica di integrità del filesystem
        if not os.path.exists(gold_path) or not os.path.exists(pred_path):
            print(f"\n[WARNING] Skipping {case_name}: file mancanti nel filesystem.")
            continue
            
        # Estrazione dati e normalizzazione
        g_ent, g_rel = extract_graph_data(gold_path)
        p_ent, p_rel = extract_graph_data(pred_path)
        
        # Calcolo separato per Nodi (Entità) e Archi (Relazioni)
        ep, er, ef1, etp, efp, efn = calculate_metrics(g_ent, p_ent, "Entità")
        rp, rr, rf1, rtp, rfp, rfn = calculate_metrics(g_rel, p_rel, "Relazioni")
        
        results.append({
            'case': case_name,
            'ent_f1': ef1, 'ent_p': ep, 'ent_r': er,
            'rel_f1': rf1, 'rel_p': rp, 'rel_r': rr
        })
        
        # Logging report per singolo caso
        print(f"\n=== CASO: {case_name} ===")
        print(f"ENTITÀ    -> Precision: {ep:.2f} | Recall: {er:.2f} | F1: {ef1:.2f} (TP:{etp} FP:{efp} FN:{efn})")
        print(f"RELAZIONI -> Precision: {rp:.2f} | Recall: {rr:.2f} | F1: {rf1:.2f} (TP:{rtp} FP:{rfp} FN:{rfn})")

    # Calcolo medie globali del sistema 
    if results:
        avg_ent_f1 = sum(r['ent_f1'] for r in results) / len(results)
        avg_rel_f1 = sum(r['rel_f1'] for r in results) / len(results)
        print("\n" + "="*30)
        print(f"MEDIA GLOBALE F1-SCORE ENTITÀ   : {avg_ent_f1:.2f}")
        print(f"MEDIA GLOBALE F1-SCORE RELAZIONI: {avg_rel_f1:.2f}")
        print("="*30)


if __name__ == "__main__":
    GOLD_DIR = "test_crew1/gold_standard"
    PRED_DIR = "casi_inseriti_db"
    
    # Mapping statico dei dataset di validazione
    CASES = {
        "Cogne": {"gold": "gold_standard_delitto_di_cogne.json", "pred": "delitto_di_cogne.json"},
        "Via Poma": {"gold": "gold_standard_delitto_di_via_poma.json", "pred": "delitto_di_via_carlo_poma.json"},
        "Marta Russo": {"gold": "gold_standard_omicidio_di_marta_russo.json", "pred": "omicidio_di_marta_russo.json"},
        "Marco Vannini": {"gold": "gold_standard_omicidio_di_marco_vannini.json", "pred": "omicidio_di_marco_vannini.json"},
        "Giulia Cecchettin": {"gold": "gold_standard_omicidio_di_giulia_cecchettin.json", "pred": "omicidio_di_giulia_cecchettin.json"},
        "Novi Ligure": {"gold": "gold_standard_delitto_di_novi_ligure.json", "pred": "delitto_di_novi_ligure.json"}
    }
    
    run_evaluation(GOLD_DIR, PRED_DIR, CASES)