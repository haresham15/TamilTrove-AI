import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Please install sentence-transformers: uv pip install sentence-transformers")
    sys.exit(1)

def compute_metrics(ranks):
    """
    ranks: list of 0-indexed ranks where the true positive was found.
    """
    if not ranks:
        return {"hit@5": 0.0, "mrr": 0.0, "ndcg": 0.0}
    
    hits_at_5 = sum(1 for r in ranks if r < 5) / len(ranks)
    mrr = sum(1.0 / (r + 1) for r in ranks) / len(ranks)
    
    # NDCG: simple case where only 1 relevant item exists, so IDCG = 1.0
    # DCG = 1 / log2(rank + 2) since rank is 0-indexed (rank 0 -> log2(2) = 1)
    ndcg = sum(1.0 / np.log2(r + 2) for r in ranks) / len(ranks)
    
    return {"hit@5": hits_at_5, "mrr": mrr, "ndcg": ndcg}

def main():
    current_dir = Path(__file__).resolve().parent.parent
    data_dir = current_dir / 'data'
    
    benchmark_path = data_dir / 'benchmark_queries.json'
    if not benchmark_path.exists():
        print(f"Benchmark not found at {benchmark_path}. Please run generate_benchmark.py first.")
        sys.exit(1)
        
    with open(benchmark_path, encoding='utf-8') as f:
        benchmark_data = json.load(f)
        
    movies_path = data_dir / 'movies_processed.json'
    with open(movies_path, encoding='utf-8') as f:
        movies_data = json.load(f)
        
    embeddings_path = data_dir / 'embeddings.npy'
    if not embeddings_path.exists():
        print("Embeddings not found. Please run re_embed.py")
        sys.exit(1)
        
    print("Loading movies and embeddings...")
    movie_embeddings = np.load(embeddings_path)
    
    if len(movies_data) != movie_embeddings.shape[0]:
        print(f"Error: {len(movies_data)} movies but {movie_embeddings.shape[0]} embeddings. Run re_embed.py")
        sys.exit(1)
        
    print("Loading Baseline Model (all-MiniLM-L6-v2)...")
    # For baseline, we use all-MiniLM-L6-v2. Later for V3, we will swap this with the fine-tuned model.
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    queries = [item['query'] for item in benchmark_data]
    print(f"Encoding {len(queries)} benchmark queries...")
    query_embeddings = model.encode(queries, show_progress_bar=False)
    
    # Normalize embeddings for cosine similarity via dot product
    movie_embeddings = movie_embeddings / np.linalg.norm(movie_embeddings, axis=1, keepdims=True)
    query_embeddings = query_embeddings / np.linalg.norm(query_embeddings, axis=1, keepdims=True)
    
    # Compute similarity matrix (queries x movies)
    similarities = np.dot(query_embeddings, movie_embeddings.T)
    
    # Evaluate
    language_ranks = defaultdict(list)
    overall_ranks = []
    
    for i, item in enumerate(benchmark_data):
        lang = item['language']
        target_title = item['target_title']
        
        # Sort indices by similarity descending
        sim_scores = similarities[i]
        ranked_indices = np.argsort(sim_scores)[::-1]
        
        # Find rank of target
        rank = -1
        for r, idx in enumerate(ranked_indices):
            if movies_data[idx].get('title', '') == target_title:
                rank = r
                break
                
        if rank != -1:
            language_ranks[lang].append(rank)
            overall_ranks.append(rank)
        else:
            print(f"Warning: Target '{target_title}' not found in catalog.")
            
    print("\n--- Baseline Metrics (all-MiniLM-L6-v2) ---")
    for lang, ranks in language_ranks.items():
        metrics = compute_metrics(ranks)
        print(f"[{lang}] (N={len(ranks)}) -> Hit@5: {metrics['hit@5']:.4f} | MRR: {metrics['mrr']:.4f} | NDCG: {metrics['ndcg']:.4f}")
        
    overall_metrics = compute_metrics(overall_ranks)
    print(f"\n[OVERALL] (N={len(overall_ranks)}) -> Hit@5: {overall_metrics['hit@5']:.4f} | MRR: {overall_metrics['mrr']:.4f} | NDCG: {overall_metrics['ndcg']:.4f}")

if __name__ == "__main__":
    main()
