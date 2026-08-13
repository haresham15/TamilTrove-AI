import json
import numpy as np
import os
from sentence_transformers import SentenceTransformer

def main():
    print("Loading movies_processed.json...")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(current_dir, 'data', 'movies_processed.json')
    
    with open(data_path, 'r', encoding='utf-8') as f:
        movies_data = json.load(f)
        
    print(f"Loaded {len(movies_data)} movies. Preparing text for re-embedding...")
    
    texts_to_embed = []
    for movie in movies_data:
        genre = movie.get('genre', '')
        overview = movie.get('overview', '')
        texts_to_embed.append(f"Genre: {genre}. Overview: {overview}")
        
    print("Loading lightweight SentenceTransformer (all-MiniLM-L6-v2)...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    print("Generating new embeddings...")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)
    
    out_npy = os.path.join(current_dir, 'data', 'embeddings.npy')
    np.save(out_npy, embeddings)
    print(f"Saved {embeddings.shape} embeddings to {out_npy}!")

if __name__ == "__main__":
    main()
