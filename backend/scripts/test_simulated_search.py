import sys, os
sys.path.insert(0, os.path.abspath("."))
from app.catalog import Catalog
from app.config import Settings
import numpy as np
from sentence_transformers import SentenceTransformer

settings = Settings()
catalog = Catalog.load(settings.data_path, settings.embeddings_path)
encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

dense_semantic_query = "courtroom legal drama lawyer advocate fighting against injustice and state oppression"
q_vec = encoder.encode([dense_semantic_query], normalize_embeddings=True)
dense_sims = (catalog.source_embeddings @ q_vec.T).reshape(-1)

print("Top 10 by Dense Semantic Similarity:")
top_indices = np.argsort(-dense_sims)[:10]
for rank, idx in enumerate(top_indices):
    m = catalog.movies[idx]
    print(f"#{rank+1}: {m.title:25} ({m.release_year}) | Sim: {dense_sims[idx]:.4f} | Themes: {m.themes} | Genre: {m.genre}")

