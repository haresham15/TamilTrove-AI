from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import os
import math
from sklearn.decomposition import PCA

app = FastAPI(title="TamilTrove API")

# Setup CORS to allow Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, restrict this to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for model and data
model = None
movies_data = []
movie_embeddings = None

# PCA Visualization Model
pca_model = None
pca_scale = 1.0

@app.on_event("startup")
async def load_data():
    global model, movies_data, movie_embeddings
    print("Initializing model and loading data...")
    
    # Paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, 'data')
    json_path = os.path.join(data_dir, 'movies_processed.json')
    npy_path = os.path.join(data_dir, 'embeddings.npy')
    
    if os.path.exists(json_path) and os.path.exists(npy_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            movies_data = json.load(f)
        movie_embeddings = np.load(npy_path)
        print(f"Loaded {len(movies_data)} movies and embeddings shape: {movie_embeddings.shape}")
    else:
        print("WARNING: Data files not found. Run precompute_embeddings.py first.")
        
    print("Loading SentenceTransformer model...")
    model = SentenceTransformer('all-mpnet-base-v2')
    
    print("Fitting PCA model on embeddings for visualization...")
    global pca_model, pca_scale
    pca_model = PCA(n_components=2)
    movie_pca = pca_model.fit_transform(movie_embeddings)
    
    # Scale to roughly [-1, 1] for UI plotting
    pca_scale = np.max(np.abs(movie_pca))
    if pca_scale == 0:
        pca_scale = 1.0
        
    print("Startup complete.")

class SearchRequest(BaseModel):
    query: str
    beta: float = 0.5  # Default hidden gem weight
    alpha: float = 1.0 # Similarity weight

@app.post("/api/search")
async def search_movies(req: SearchRequest):
    if not movies_data or movie_embeddings is None or model is None:
        return {"error": "Server not fully initialized. Data or model missing."}
        
    if not req.query.strip():
        return {"results": []}
        
    # Compute query embedding
    query_vector = model.encode([req.query])[0]
    
    # Helper to calculate True Semantic Plot Coordinates bound to [-1, 1]
    def calc_semantic_coords(vec):
        proj = pca_model.transform([vec])[0]
        x = float(proj[0] / pca_scale)
        y = float(proj[1] / pca_scale)
        # Clamp to bounds for safety in UI
        return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))
        
    query_x, query_y = calc_semantic_coords(query_vector)
    
    # Calculate cosine similarity manually for zero dependencies beyond numpy
    # Cosine Similarity = (A . B) / (||A|| * ||B||)
    # The embeddings from all-MiniLM-L6-v2 are typically already normalized, but we'll do it safely
    dot_products = np.dot(movie_embeddings, query_vector)
    query_norm = np.linalg.norm(query_vector)
    
    # Assuming embeddings were normalized during encode, norm is 1. We compute anyway.
    norms = np.linalg.norm(movie_embeddings, axis=1) * query_norm
    # Avoid division by zero
    similarities = np.divide(dot_products, norms, out=np.zeros_like(dot_products), where=norms!=0)
    
    # Calculate initial scores
    candidates = []
    for i, movie in enumerate(movies_data):
        sim = float(similarities[i])
        
        # Normalize similarity from [-1, 1] to [0, 1]
        norm_sim = (sim + 1.0) / 2.0
        
        prom = movie.get('prominence_score', 0.5)
        
        # --- NEW AI SCORING ALGORITHM ---
        # Instead of a weighted average that lets obscurity overpower relevance,
        # we apply a "Hidden Gem Bonus" that scales WITH semantic similarity.
        # This means an obscure movie only gets boosted if it actually matches the query!
        
        # req.beta is [0, 2.0] from the UI slider.
        # We map this to a max boost of 40% (0.4) when the slider is maxed.
        max_boost = (req.beta / 2.0) * 0.4
        
        # The bonus is higher if the movie is actually relevant (sim > 0) AND highly obscure.
        # Use max(0, sim) instead of norm_sim to avoid boosting completely irrelevant movies.
        hidden_gem_bonus = max(0.0, sim) * max_boost * (1.0 - prom)
        
        # Calculate final score using req.alpha and clamp to 1.0 maximum
        # Base similarity score is scaled by alpha
        base_score = req.alpha * norm_sim
        final_score = min(1.0, base_score + hidden_gem_bonus)
            
        movie_x, movie_y = calc_semantic_coords(movie_embeddings[i])
            
        candidates.append({
            "index": i,
            "title": movie.get('title'),
            "genre": movie.get('genre'),
            "director": movie.get('director'),
            "cast": movie.get('cast'),
            "overview": movie.get('overview'),
            "poster_url": movie.get('poster_url'),
            "prominence_score": round(prom, 4),
            "similarity_score": round(sim, 4),
            "final_score": round(final_score, 4),
            "plot_x": round(movie_x, 4),
            "plot_y": round(movie_y, 4),
            "embedding": movie_embeddings[i]  # Keep embedding for MMR
        })
        
    # Sort by final score descending to get top candidates for MMR
    candidates.sort(key=lambda x: x["final_score"], reverse=True)
    
    # Apply Maximal Marginal Relevance (MMR) for diversity
    # We will select 20 results from the top 60 candidates
    top_candidates = candidates[:60]
    final_results = []
    
    if top_candidates:
        # First movie is always the one with the highest score
        final_results.append(top_candidates.pop(0))
        
        # Diversity weight factor (lambda). 0.0 means no diversity, 1.0 means full diversity
        diversity_weight = 0.3 # Moderate diversity
        
        while len(final_results) < 20 and top_candidates:
            best_mmr_score = -float('inf')
            best_idx = 0
            
            for idx, candidate in enumerate(top_candidates):
                cand_emb = candidate["embedding"]
                # Embeddings should be normalized, so dot product is roughly cosine similarity
                max_sim_to_selected = max([
                    float(np.dot(cand_emb, sel["embedding"]))
                    for sel in final_results
                ])
                
                # candidate["final_score"] is our relevance measure
                mmr_score = (1.0 - diversity_weight) * candidate["final_score"] - diversity_weight * max_sim_to_selected
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx
            
            final_results.append(top_candidates.pop(best_idx))
            
    # Cleanup embeddings from final results before returning
    for res in final_results:
        res.pop("embedding", None)
    
    # Return top 20 diverse results
    return {
        "query_plot": {"x": round(query_x, 4), "y": round(query_y, 4)},
        "results": final_results
    }
