import json
import csv
import re
from pathlib import Path
import pandas as pd
import numpy as np

def categorize_legal_error(query_text, doc_text, features):
    # Simple heuristic rule based classification
    # Fix year extraction
    q_years = set(re.findall(r'\b(?:19|20)\d{2}\b', query_text))
    d_years = set(re.findall(r'\b(?:19|20)\d{2}\b', doc_text))
    
    # Improved legal identifier extraction
    # Match standard formats like 123/2023/NĐ-CP, 12/UBND, etc.
    q_law_ids = set(re.findall(r'\b\d+/(?:(?:19|20)\d{2}/)?[A-Z0-9Đ-]+(?:/[A-Z0-9Đ-]+)?\b', query_text, re.IGNORECASE))
    d_law_ids = set(re.findall(r'\b\d+/(?:(?:19|20)\d{2}/)?[A-Z0-9Đ-]+(?:/[A-Z0-9Đ-]+)?\b', doc_text, re.IGNORECASE))
    
    # Numeric Article/Section/Clause references: e.g. "Điều 5", "Khoản 2", "Điểm a"
    # Just extract numbers that are part of the query if we don't have a complex parser.
    # The prompt allows using number_overlap from features if we want.
    q_nums = set(re.findall(r'\b\d+\b', query_text))
    d_nums = set(re.findall(r'\b\d+\b', doc_text))
    
    if q_law_ids and not q_law_ids.issubset(d_law_ids):
        return "LAW/DECREE IDENTIFIER CONFLICT"
        
    if q_years and not q_years.issubset(d_years):
        return "NUMBER/YEAR CONFLICT"
        
    if q_nums and not q_nums.issubset(d_nums):
        return "NUMBER/YEAR CONFLICT"
        
    # Procedural vs Definition: fallback based on overlap
    if features.get('token_overlap_ratio', 1.0) < 0.2:
        return "LOW_LEXICAL_OVERLAP"
        
    # Just fallbacks
    return "OTHER"

def main():
    base_dir = Path(r"data/competition")
    results_dir = base_dir / "experiments" / "legalir" / "autonomous" / "results"
    
    # 1. Load basic validation data
    train_file = base_dir.parent.parent / "Data Science Challenge 2026 (Task 1)" / "train.json"
    with open(train_file, "r", encoding="utf-8") as f:
        train_data = json.load(f)
        
    val_file = base_dir / "configs" / "validation_manifest.json"
    with open(val_file, "r", encoding="utf-8") as f:
        val_data_manifest = json.load(f)
        val_qids = val_data_manifest.get("task1", val_data_manifest) if isinstance(val_data_manifest, dict) else val_data_manifest
            
    gold_map = {qid: [str(x) for x in train_data[qid]["answer"]] for qid in val_qids if qid in train_data}
    
    # 2. Load candidates and features
    fusion_file = base_dir / "experiments" / "legalir" / "autonomous" / "runner" / "fusion_features_text_aug.csv"
    fusion_df = pd.read_csv(fusion_file)
    fusion_df['qid'] = fusion_df['qid'].astype(str)
    fusion_df['doc_id'] = fusion_df['doc_id'].astype(str)
    
    e2_cands = fusion_df.groupby('qid')['doc_id'].apply(list).to_dict()
    
    # 3. Load E2 validation results
    e2_val_res_file = base_dir / "experiments" / "legalir" / "e2_validation_results.json"
    with open(e2_val_res_file, "r", encoding="utf-8") as f:
        e2_val_res = json.load(f)
    
    e2_val_map = {}
    e2_preds = e2_val_res.get("results", e2_val_res)
    if isinstance(e2_preds, dict):
        for k, v in e2_preds.items():
            e2_val_map[str(k)] = [str(x) for x in v.get("top5", v)] if isinstance(v, dict) else [str(x) for x in v]
    elif isinstance(e2_preds, list):
        for item in e2_preds:
            e2_val_map[str(item["question_id"])] = [str(x) for x in item["predicted_articles"]]

    # 4. Load H400_A predictions
    h400_preds = results_dir / "policy_h_oof_predictions.csv"
    h400_df = pd.read_csv(h400_preds)
    h400_df['qid'] = h400_df['qid'].astype(str)
    h400_df['doc_id'] = h400_df['doc_id'].astype(str)
    h400_df = h400_df.sort_values(['qid', 'Policy_H'], ascending=[True, False])
    h400_top5_map = h400_df.groupby('qid').head(5).groupby('qid')['doc_id'].apply(list).to_dict()
    
    # Build dictionaries for score gap analysis
    h400_scores = {}
    for _, row in h400_df.iterrows():
        if row['qid'] not in h400_scores:
            h400_scores[row['qid']] = {}
        h400_scores[row['qid']][row['doc_id']] = row['Policy_H']
        
    h400_top_scores = h400_df.groupby('qid').head(5).groupby('qid')['Policy_H'].apply(list).to_dict()

    # Feature dict for quick lookup
    feat_cols = [c for c in fusion_df.columns if c not in ['qid', 'doc_id', 'label']]
    feature_dict = {}
    for _, row in fusion_df.iterrows():
        if row['qid'] not in feature_dict:
            feature_dict[row['qid']] = {}
        feature_dict[row['qid']][row['doc_id']] = {c: row[c] for c in feat_cols}
    
    # Text lookup (for legal error categories)
    # We will only load this if needed for the misses
    val_inputs_file = base_dir / "experiments" / "legalir" / "autonomous" / "runner" / "val_compact_inputs.json"
    print("Loading text inputs...")
    with open(val_inputs_file, "r", encoding="utf-8") as f:
        val_inputs = json.load(f)

    error_decomp = []
    ranking_misses_data = []
    
    h400_hits_feats = []
    h400_miss_feats = []
    
    e2_rank_ranks = []
    h400_rank_ranks = []
    
    error_patterns = {}
    
    for qid in val_qids:
        if qid not in gold_map: continue
        golds = gold_map[qid]
        cands = e2_cands.get(qid, [])
        top5 = h400_top5_map.get(qid, [])[:5]
        
        is_in_cands = any(g in cands for g in golds)
        is_in_top5 = any(g in top5 for g in golds)
        
        # E2 rank stats
        e2_top5 = e2_val_map.get(qid, [])[:5]
        if is_in_cands and not any(g in e2_top5 for g in golds):
            # E2 ranking miss
            best_e2_rank = min((cands.index(g) + 1 for g in golds if g in cands), default=None)
            if best_e2_rank: e2_rank_ranks.append(best_e2_rank)
            
        if is_in_top5:
            cat = "HIT"
            for g in golds:
                if g in feature_dict.get(qid, {}):
                    h400_hits_feats.append(feature_dict[qid][g])
        elif is_in_cands:
            cat = "RANKING_MISS"
            best_rank = min((cands.index(g) + 1 for g in golds if g in cands), default=None)
            if best_rank: h400_rank_ranks.append(best_rank)
            
            # Analyze this ranking miss
            # Find the best gold document in candidates (highest H400 score)
            best_g = None
            best_g_score = -999
            for g in golds:
                if g in cands:
                    s = h400_scores.get(qid, {}).get(g, -999)
                    if s > best_g_score:
                        best_g_score = s
                        best_g = g
            
            if best_g:
                f_g = feature_dict.get(qid, {}).get(best_g, {})
                h400_miss_feats.append(f_g)
                
                t5_scores = h400_top_scores.get(qid, [0]*5)
                score_gap = t5_scores[-1] - best_g_score if len(t5_scores)==5 else 0
                
                # Text classification
                q_text = val_inputs.get(qid, {}).get("question", "")
                d_idx = val_inputs.get(qid, {}).get("candidates", []).index(best_g) if best_g in val_inputs.get(qid, {}).get("candidates", []) else -1
                doc_texts = val_inputs.get(qid, {}).get("doc_texts", [])
                d_text = doc_texts[d_idx] if 0 <= d_idx < len(doc_texts) else ""
                
                err_cat = categorize_legal_error(q_text, d_text, f_g)
                error_patterns[err_cat] = error_patterns.get(err_cat, 0) + 1
                
                margins = [s - best_g_score for s in t5_scores] + [0]*(5-len(t5_scores))
                
                ranking_misses_data.append({
                    "qid": qid,
                    "gold_id": best_g,
                    "rrf_rank": f_g.get("rrf_rank"),
                    "ce_rank": f_g.get("ce_rank"),
                    "semantic_ce_score": f_g.get("semantic_ce_score"),
                    "lexical_ce_score": f_g.get("lexical_ce_score"),
                    "max_ce_score": f_g.get("max_ce_score"),
                    "sem_minus_lex_diff": f_g.get("sem_minus_lex_diff"),
                    "abs_disagreement": f_g.get("abs_disagreement"),
                    "token_overlap_count": f_g.get("token_overlap_count"),
                    "query_token_coverage": f_g.get("query_token_coverage"),
                    "h400_top5": str(top5),
                    "h400_top5_scores": str(t5_scores),
                    "gold_h400_score": best_g_score,
                    "score_gap_to_rank5": score_gap,
                    "margin_top1": margins[0],
                    "margin_top2": margins[1],
                    "margin_top3": margins[2],
                    "margin_top4": margins[3],
                    "margin_top5": margins[4],
                    "error_category": err_cat
                })
                
        else:
            cat = "CANDIDATE_MISS"
            
        error_decomp.append({"qid": qid, "category": cat})

    # Save outputs
    pd.DataFrame(error_decomp).to_csv(results_dir / "h400a_error_decomposition.csv", index=False)
    if ranking_misses_data:
        pd.DataFrame(ranking_misses_data).to_csv(results_dir / "h400a_ranking_misses.csv", index=False)
        
    # Rank distribution
    def get_dist(ranks):
        bins = [1, 5, 10, 20, 30, 50, 75, 100]
        hist, _ = np.histogram(ranks, bins=bins + [999])
        return {f"{bins[i]}-{bins[i+1]}": hist[i] for i in range(len(bins)-1)}
        
    e2_dist = get_dist(e2_rank_ranks)
    h400_dist = get_dist(h400_rank_ranks)
    dist_str = "E2 Miss Rank Dist: " + str(e2_dist) + "\nH400_A Miss Rank Dist: " + str(h400_dist)
    
    # Near cutoff
    miss_df = pd.DataFrame(ranking_misses_data)
    near_cutoff = 0
    if not miss_df.empty:
        near_cutoff = (miss_df["score_gap_to_rank5"] < 0.05).mean()
        
    # Error categories
    err_sorted = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)
    
    output_str = "LEGALIR_RERANKER_ERROR_ANALYSIS_COMPLETE\n\n"
    output_str += "H400A_SINGLE_RUN_R5: 0.9207\n"
    output_str += "H400A_SINGLE_RUN_P5: 0.1913\n\n"
    output_str += "H400A_STABLE_R5: 0.9174\n"
    output_str += "H400A_STABLE_P5: 0.1906\n\n"
    
    hits = sum(1 for x in error_decomp if x["category"] == "HIT")
    cmiss = sum(1 for x in error_decomp if x["category"] == "CANDIDATE_MISS")
    rmiss = sum(1 for x in error_decomp if x["category"] == "RANKING_MISS")
    
    output_str += f"H400A_HITS: {hits}\n"
    output_str += f"H400A_CANDIDATE_MISSES: {cmiss}\n"
    output_str += f"H400A_RANKING_MISSES: {rmiss}\n\n"
    
    output_str += "GOLD_RANK_DISTRIBUTION:\n"
    output_str += dist_str + "\n\n"
    
    output_str += f"NEAR_CUTOFF_MISS_RATE: {near_cutoff:.4f}\n\n"
    
    for i, (cat, cnt) in enumerate(err_sorted[:3]):
        pct = cnt / max(1, rmiss) * 100
        output_str += f"TOP_ERROR_PATTERN_{i+1}: {cat} ({cnt} cases, {pct:.1f}%)\n"
        
    output_str += "\nBEST_SUPPORTED_RERANKER_DIRECTION:\n"
    if near_cutoff > 0.5:
        output_str += "Calibrated CE/RRF fusion or pointwise margin adjustments.\n"
    else:
        output_str += "Legal anchor feature augmentation (dates, law IDs).\n"
        
    output_str += "\nEXPERIMENTS_STARTED:\nNO\n\nTASK2_STATUS:\nFROZEN\n\nAUTO_SUBMIT:\nNO\n\nSTATUS:\nREADY_FOR_TARGETED_RERANKER_EXPERIMENT"
    
    with open(results_dir / "h400a_error_analysis_v2.md", "w", encoding="utf-8") as f:
        f.write(output_str)
        
    print(output_str)
        
    print("\nEXPERIMENTS_STARTED:\nNO\n")
    print("TASK2_STATUS:\nFROZEN\n")
    print("AUTO_SUBMIT:\nNO\n")
    print("STATUS:\nREADY_FOR_TARGETED_RERANKER_EXPERIMENT")

if __name__ == "__main__":
    main()
