import json
import csv
from pathlib import Path
import pandas as pd

def main():
    base_dir = Path(r"data/competition")
    results_dir = base_dir / "experiments" / "legalir" / "autonomous" / "results"
    
    val_file = base_dir / "configs" / "validation_manifest.json"
    with open(val_file, "r", encoding="utf-8") as f:
        val_data_manifest = json.load(f)
        if isinstance(val_data_manifest, dict) and "task1" in val_data_manifest:
            val_qids = val_data_manifest["task1"]
        else:
            val_qids = val_data_manifest
            
    train_file = base_dir.parent.parent / "sample_data" / "dataset.json"
    with open(train_file, "r", encoding="utf-8") as f:
        train_data = json.load(f)
        
    gold_map = {}
    for qid, item in train_data.items():
        if qid in val_qids:
            gold_map[qid] = item["answer"][0]
            
    runner_dir = base_dir / "experiments" / "legalir" / "autonomous" / "runner"
    with open(runner_dir / "dense_ranks.json", "r", encoding="utf-8") as f:
        dense_ranks = json.load(f)
    with open(runner_dir / "bm25_ranks.json", "r", encoding="utf-8") as f:
        bm25_ranks = json.load(f)
        
    matrix = []
    
    dense_surv = 0
    bm25_surv = 0
    rrf100_surv = 0
    rrf200_surv = 0
    rrf300_surv = 0
    rrf500_surv = 0
    
    k_rrf = 60
    
    for qid in val_qids:
        if qid not in gold_map:
            continue
        gold = gold_map[qid]
        
        dense_docs = dense_ranks.get(qid, [])[:500] # Top 500
        bm25_docs = bm25_ranks.get(qid, [])[:500] # Top 500
        
        # Calculate RRF
        scores_dict = {}
        for rank, doc in enumerate(dense_docs):
            scores_dict[doc] = scores_dict.get(doc, 0.0) + 1.0 / (k_rrf + rank + 1)
        for rank, doc in enumerate(bm25_docs):
            scores_dict[doc] = scores_dict.get(doc, 0.0) + 1.0 / (k_rrf + rank + 1)
            
        rrf_docs = sorted(scores_dict.keys(), key=lambda x: scores_dict[x], reverse=True)
        
        d_hit = gold in dense_docs
        b_hit = gold in bm25_docs
        
        r100_hit = gold in rrf_docs[:100]
        r200_hit = gold in rrf_docs[:200]
        r300_hit = gold in rrf_docs[:300]
        r500_hit = gold in rrf_docs[:500]
        
        if d_hit: dense_surv += 1
        if b_hit: bm25_surv += 1
        if r100_hit: rrf100_surv += 1
        if r200_hit: rrf200_surv += 1
        if r300_hit: rrf300_surv += 1
        if r500_hit: rrf500_surv += 1
        
        if not d_hit and not b_hit:
            miss_type = "BOTH_MISS"
        elif not d_hit:
            miss_type = "DENSE_MISS"
        elif not b_hit:
            miss_type = "BM25_MISS"
        else:
            miss_type = "NONE"
            
        if not r500_hit:
            miss_type = "RRF_MISS"
            
        matrix.append({
            "qid": qid,
            "dense_hit": d_hit,
            "bm25_hit": b_hit,
            "rrf100_hit": r100_hit,
            "rrf200_hit": r200_hit,
            "rrf300_hit": r300_hit,
            "rrf500_hit": r500_hit,
            "miss_type": miss_type
        })
        
    with open(results_dir / "candidate_survival_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=matrix[0].keys())
        writer.writeheader()
        writer.writerows(matrix)
        
    # We need to know ranking miss: gold in rrf500 but not in top 5 of E2 model_outputs
    # Wait, H400_A was saved in policy_h_oof_results.csv
    e2_preds_file = base_dir / "experiments" / "legalir" / "autonomous" / "results" / "policy_h_oof_results.csv"
    if e2_preds_file.exists():
        preds_df = pd.read_csv(e2_preds_file)
        preds_df['doc_id'] = preds_df['doc_id'].astype(str)
        preds_df['qid'] = preds_df['qid'].astype(str)
        preds_df = preds_df.sort_values(['qid', 'Policy_H'], ascending=[True, False])
        top5_map = preds_df.groupby('qid').head(5).groupby('qid')['doc_id'].apply(list).to_dict()
                
        ranking_misses = 0
        for row in matrix:
            qid = row['qid']
            gold = gold_map[qid]
            r500_hit = row['rrf500_hit']
            in_top5 = gold in top5_map.get(qid, [])
            if r500_hit and not in_top5:
                row['miss_type'] = "RANKING_ONLY_MISS"
                ranking_misses += 1
    else:
        ranking_misses = 0
        print("Warning: policy_h_oof_results.csv not found, ranking_misses set to 0")
            
    # Phase 2
    n_queries = len(matrix)
    candidate_loss = n_queries - rrf500_surv
    ranking_loss = ranking_misses
    
    candidate_loss_rate = candidate_loss / n_queries
    ranking_loss_rate = ranking_loss / n_queries
    
    summary = (
        f"N validation queries: {n_queries}\n"
        f"Dense gold survival: {dense_surv}\n"
        f"BM25 gold survival: {bm25_surv}\n"
        f"RRF100 gold survival: {rrf100_surv}\n"
        f"RRF200 gold survival: {rrf200_surv}\n"
        f"RRF300 gold survival: {rrf300_surv}\n"
        f"RRF500 gold survival: {rrf500_surv}\n\n"
        f"Candidate Loss Rate: {candidate_loss_rate:.4f} ({candidate_loss})\n"
        f"Ranking Loss Rate: {ranking_loss_rate:.4f} ({ranking_loss})\n"
    )
    
    with open(results_dir / "candidate_survival_summary.md", "w", encoding="utf-8") as f:
        f.write(summary)
        
    print(summary)
    
if __name__ == "__main__":
    main()
