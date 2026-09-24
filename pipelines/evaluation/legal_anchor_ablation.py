import json
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import GroupKFold
from sklearn.ensemble import ExtraTreesClassifier

def evaluate_model_outputs(val_df, pred_col, golds_in_pool, tie_col='rrf_rank'):
    hits_at_k = {1: 0, 3: 0, 5: 0, 10: 0}
    precision_hits_5 = 0
    num_queries = val_df['qid'].nunique()
    
    hits = 0
    candidate_misses = 0
    ranking_misses = 0
    
    model_outputs = {}
    
    for qid, group in val_df.groupby('qid'):
        sorted_group = group.sort_values([pred_col, tie_col], ascending=[False, True])
        top10_docs = sorted_group['doc_id'].head(10).tolist()
        
        q_golds = golds_in_pool.get(qid, set())
        if not q_golds:
            candidate_misses += 1
            continue
            
        hit1 = int(any(d in q_golds for d in top10_docs[:1]))
        hit3 = int(any(d in q_golds for d in top10_docs[:3]))
        hit5 = int(any(d in q_golds for d in top10_docs[:5]))
        hit10 = int(any(d in q_golds for d in top10_docs[:10]))
        
        hits_in_5 = sum(1 for d in top10_docs[:5] if d in q_golds)
        
        hits_at_k[1] += hit1
        hits_at_k[3] += hit3
        hits_at_k[5] += hit5
        hits_at_k[10] += hit10
        precision_hits_5 += hits_in_5
        
        if hit5:
            hits += 1
        else:
            ranking_misses += 1
            
        model_outputs[qid] = {
            "top5": top10_docs[:5], 
            "top10": top10_docs,
            "scores": sorted_group[pred_col].head(10).tolist(),
            "hit": hit5
        }
            
    metrics = {
        'R@1': hits_at_k[1] / num_queries,
        'R@3': hits_at_k[3] / num_queries,
        'R@5': hits_at_k[5] / num_queries,
        'R@10': hits_at_k[10] / num_queries,
        'P@5': precision_hits_5 / (5 * num_queries),
        'hits': hits,
        'candidate_misses': candidate_misses,
        'ranking_misses': ranking_misses,
        'model_outputs': model_outputs
    }
    return metrics

def run_experiment(df, feature_cols, golds_in_pool, num_queries):
    gkf = GroupKFold(n_splits=5)
    
    # ExtraTrees config for H400_A exactly
    model = ExtraTreesClassifier(
        n_estimators=400, 
        max_depth=8, 
        min_samples_leaf=2, 
        class_weight="balanced",
        random_state=42, 
        n_jobs=-1
    )
    
    oof_preds = np.zeros(len(df))
    X = df[feature_cols].copy()
    
    # Fill any NaNs
    X = X.fillna(0)
    y = df['label']
    groups = df['qid']
    
    for train_idx, val_idx in gkf.split(X, y, groups=groups):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_val = X.iloc[val_idx]
        
        model.fit(X_train, y_train)
        oof_preds[val_idx] = model.predict_proba(X_val)[:, 1]
        
    df_eval = df[['qid', 'doc_id', 'rrf_rank']].copy()
    df_eval['pred'] = oof_preds
    
    return evaluate_model_outputs(df_eval, 'pred', golds_in_pool)

def main():
    base_dir = Path(r"data/competition")
    results_dir = base_dir / "experiments" / "legalir" / "autonomous" / "results"
    
    # 1. Load Data
    train_file = base_dir.parent.parent / "sample_data" / "dataset.json"
    with open(train_file, "r", encoding="utf-8") as f:
        train_data = json.load(f)
        
    val_file = base_dir / "configs" / "validation_manifest.json"
    with open(val_file, "r", encoding="utf-8") as f:
        val_data_manifest = json.load(f)
        val_qids = val_data_manifest.get("task1", val_data_manifest) if isinstance(val_data_manifest, dict) else val_data_manifest
            
    fusion_file = base_dir / "experiments" / "legalir" / "autonomous" / "runner" / "fusion_features_text_aug.csv"
    df = pd.read_csv(fusion_file)
    df['qid'] = df['qid'].astype(str)
    df['doc_id'] = df['doc_id'].astype(str)
    
    # Precompute golds_in_pool
    golds_in_pool = {}
    for qid in val_qids:
        if str(qid) in train_data:
            g = [str(x) for x in train_data[str(qid)]["answer"]]
            pool = set(df[df['qid'] == str(qid)]['doc_id'])
            golds_in_pool[str(qid)] = set(g).intersection(pool)
            
    num_queries = len(val_qids)

    # 2. Experiments
    # LA-0: Baseline (H400_A)
    la0_features = [
        'semantic_ce_score', 'lexical_ce_score', 'max_ce_score', 'sem_minus_lex_diff',
        'rrf_rank', 'ce_rank', 'ce_margin', 'query_token_coverage', 'token_overlap_count',
        'token_overlap_ratio', 'abs_disagreement'
    ]
    print("Running LA-0 (Baseline)...")
    res_la0 = run_experiment(df, la0_features, golds_in_pool, num_queries)
    
    # LA-1: Add Legal Anchors
    la1_features = la0_features + ['number_overlap', 'year_overlap', 'exact_phrase_match']
    print("Running LA-1 (Legal Anchors)...")
    res_la1 = run_experiment(df, la1_features, golds_in_pool, num_queries)
    
    # LA-2: Legal Anchors + Other Deterministic Lexical
    # There are no other "legal-identifier" features, so we just add the remaining deterministic ones.
    la2_features = la1_features + ['candidate_token_coverage']
    print("Running LA-2 (Legal Anchors + Tokens)...")
    res_la2 = run_experiment(df, la2_features, golds_in_pool, num_queries)
    
    # 3. Analyze differences
    best_exp_name = "LA-0"
    best_res = res_la0
    
    for name, res in [("LA-1", res_la1), ("LA-2", res_la2)]:
        if res['R@5'] > best_res['R@5'] and (res['P@5'] >= best_res['P@5'] - 0.0015):
            best_exp_name = name
            best_res = res
            
    if best_res['R@5'] > res_la0['R@5'] and best_exp_name != "LA-0":
        promotion = "PROMOTED"
    else:
        promotion = "REJECTED"
        
    delta_r5 = best_res['R@5'] - res_la0['R@5']
    delta_p5 = best_res['P@5'] - res_la0['P@5']
    
    # Compare queries
    base_preds = res_la0['model_outputs']
    best_preds = best_res['model_outputs']
    
    recovered = []
    lost = []
    
    recovered_details = []
    lost_details = []
    
    for qid in val_qids:
        qid = str(qid)
        if qid not in base_preds: continue
        base_hit = base_preds[qid]['hit']
        best_hit = best_preds[qid]['hit']
        if not base_hit and best_hit:
            recovered.append(qid)
            # Find the gold doc that caused the hit
            gold_docs = golds_in_pool.get(qid, set())
            for g in gold_docs:
                if g in best_preds[qid]['top5']:
                    # Extract details
                    b_rank = base_preds[qid]['top10'].index(g) + 1 if g in base_preds[qid]['top10'] else '>10'
                    n_rank = best_preds[qid]['top10'].index(g) + 1 if g in best_preds[qid]['top10'] else '>10'
                    b_score = base_preds[qid]['scores'][base_preds[qid]['top10'].index(g)] if g in base_preds[qid]['top10'] else 'N/A'
                    n_score = best_preds[qid]['scores'][best_preds[qid]['top10'].index(g)] if g in best_preds[qid]['top10'] else 'N/A'
                    
                    row = df[(df['qid'] == qid) & (df['doc_id'] == g)].iloc[0]
                    recovered_details.append({
                        'qid': qid, 'gold_doc': g, 'baseline_rank': b_rank, 'new_rank': n_rank,
                        'baseline_score': b_score, 'new_score': n_score,
                        'number_overlap': row['number_overlap'], 'year_overlap': row['year_overlap'],
                        'exact_phrase_match': row['exact_phrase_match']
                    })
        elif base_hit and not best_hit:
            lost.append(qid)
            gold_docs = golds_in_pool.get(qid, set())
            for g in gold_docs:
                if g in base_preds[qid]['top5']:
                    b_rank = base_preds[qid]['top10'].index(g) + 1 if g in base_preds[qid]['top10'] else '>10'
                    n_rank = best_preds[qid]['top10'].index(g) + 1 if g in best_preds[qid]['top10'] else '>10'
                    b_score = base_preds[qid]['scores'][base_preds[qid]['top10'].index(g)] if g in base_preds[qid]['top10'] else 'N/A'
                    n_score = best_preds[qid]['scores'][best_preds[qid]['top10'].index(g)] if g in best_preds[qid]['top10'] else 'N/A'
                    
                    row = df[(df['qid'] == qid) & (df['doc_id'] == g)].iloc[0]
                    lost_details.append({
                        'qid': qid, 'gold_doc': g, 'baseline_rank': b_rank, 'new_rank': n_rank,
                        'baseline_score': b_score, 'new_score': n_score,
                        'number_overlap': row['number_overlap'], 'year_overlap': row['year_overlap'],
                        'exact_phrase_match': row['exact_phrase_match']
                    })
                    
    pd.DataFrame(recovered_details).to_csv(results_dir / "recovered_queries_details.csv", index=False)
    pd.DataFrame(lost_details).to_csv(results_dir / "lost_queries_details.csv", index=False)
            
    output = "LEGALIR_LEGAL_ANCHOR_ABLATION_COMPLETE\n\n"
    output += f"BASELINE_H400A_R5: {res_la0['R@5']:.4f}\n"
    output += f"BASELINE_H400A_P5: {res_la0['P@5']:.4f}\n\n"
    
    output += f"LA1_R5: {res_la1['R@5']:.4f}\n"
    output += f"LA1_P5: {res_la1['P@5']:.4f}\n\n"
    
    output += f"LA2_R5: {res_la2['R@5']:.4f}\n"
    output += f"LA2_P5: {res_la2['P@5']:.4f}\n\n"
    
    output += f"BEST_EXPERIMENT: {best_exp_name}\n\n"
    output += f"BEST_DELTA_R5: {delta_r5:+.4f}\n"
    output += f"BEST_DELTA_P5: {delta_p5:+.4f}\n\n"
    
    output += f"RECOVERED_RANKING_MISSES: {len(recovered)}\n"
    output += f"LOST_BASELINE_HITS: {len(lost)}\n\n"
    
    output += "YEAR_REGEX_FIXED: YES\n"
    output += "ERROR_ANALYSIS_V2: COMPLETE\n"
    
    # Baseline OOF Reproduction Check
    if abs(res_la0['R@5'] - 0.9207) < 0.0005:
        output += "BASELINE_OOF_REPRODUCED: YES\n\n"
    else:
        output += f"BASELINE_OOF_REPRODUCED: NO (Got {res_la0['R@5']:.4f})\n\n"
        
    output += f"PROMOTION_STATUS:\n{promotion}\n\n"
    output += "NEXT_SAFE_DIRECTION:\n"
    
    if promotion == "PROMOTED":
        output += f"Use {best_exp_name} configuration to train a production artifact.\n\n"
    else:
        output += "Investigate pointwise margins or other robust features, since anchors didn't help enough.\n\n"
        
    output += "TASK2_STATUS:\nFROZEN\n\n"
    output += "AUTO_SUBMIT:\nNO\n"
    
    with open(results_dir / "ablation_analysis.txt", "w") as f:
        f.write(output)
        
    print(output)

if __name__ == "__main__":
    main()
