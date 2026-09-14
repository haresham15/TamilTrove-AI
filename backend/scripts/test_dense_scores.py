import sys, os
sys.path.insert(0, os.path.abspath("."))
from app.catalog import Catalog
from app.config import Settings
from sentence_transformers import SentenceTransformer
import numpy as np

settings = Settings()
catalog = Catalog.load(settings.data_path, settings.embeddings_path)
encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

semantic_matrix = np.load(settings.embeddings_path)

queries = [
    "courtroom la injustice fight panra padam movie film",
    "courtroom legal drama lawyer advocate fighting against injustice and oppression",
    "courtroom legal drama fighting injustice lawyer",
]

targets = ["Jai Bhim", "Nerkonda Paarvai", "The Verdict", "Pavithra 1994", "Thummbad", "Tamizh Padam 2.0"]
indices = {t: next(i for i, m in enumerate(catalog.movies) if m.title == t) for t in targets}

for q in queries:
    print(f"\n==========================================")
    print(f"QUERY: '{q}'")
    print(f"==========================================")
    q_vec = encoder.encode([q], normalize_embeddings=True)
    sims = (semantic_matrix @ q_vec.T).reshape(-1)
    
    # rank of each target
    order = np.argsort(-sims)
    ranks = {order[r]: r + 1 for r in range(len(order))}
    
    for t in targets:
        idx = indices[t]
        print(f"  {t:20} -> Rank #{ranks[idx]:3d} | Cosine Sim: {sims[idx]:.4f}")
