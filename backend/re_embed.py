import json
import numpy as np
import os
import sys

# Force flush prints
def print_flush(msg):
    print(msg)
    sys.stdout.flush()

def main():
    print_flush("Loading movies_processed.json...")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(current_dir, 'data', 'movies_processed.json')
    
    with open(data_path, 'r', encoding='utf-8') as f:
        movies_data = json.load(f)
        
    print_flush(f"Loaded {len(movies_data)} movies. Preparing text...")
    
    texts_to_embed = []
    for movie in movies_data:
        genre = movie.get('genre', '')
        overview = movie.get('overview', '')
        texts_to_embed.append(f"Genre: {genre}. Overview: {overview}")
        
    print_flush("Loading SentenceTransformer (all-MiniLM-L6-v2)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    print_flush("Generating embeddings...")
    embeddings = model.encode(texts_to_embed, show_progress_bar=False)
    
    out_npy = os.path.join(current_dir, 'data', 'embeddings.npy')
    np.save(out_npy, embeddings)
    print_flush(f"Saved {embeddings.shape} embeddings to {out_npy}!")

if __name__ == "__main__":
    main()
