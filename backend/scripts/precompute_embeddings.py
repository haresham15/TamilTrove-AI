import pandas as pd
import numpy as np
import json
import os
from sentence_transformers import SentenceTransformer

def calculate_prominence_scores(df):
    # Calculate global director counts
    director_counts = df['director'].value_counts().to_dict()
    
    # Calculate global actor counts
    actor_counts = {}
    for cast_str in df['cast'].fillna(''):
        actors = [a.strip() for a in str(cast_str).split(',') if a.strip()]
        for actor in actors:
            actor_counts[actor] = actor_counts.get(actor, 0) + 1
            
    # Calculate raw scores for each movie
    raw_scores = []
    for _, row in df.iterrows():
        director = row['director']
        d_score = director_counts.get(director, 0)
        
        cast_str = str(row['cast']) if pd.notna(row['cast']) else ''
        actors = [a.strip() for a in cast_str.split(',') if a.strip()]
        
        if len(actors) > 0:
            c_score = sum(actor_counts.get(a, 0) for a in actors) / len(actors)
        else:
            c_score = 0
            
        # Combine director and average cast score
        raw_score = d_score + c_score
        raw_scores.append(raw_score)
        
    # Replace Min-Max scaling with Percentile Ranking for uniform distribution
    # This prevents the heavy left-skew and makes the Popularity bar robust.
    s = pd.Series(raw_scores)
    percentile_scores = s.rank(pct=True).tolist()
        
    return percentile_scores

def main():
    print("Loading data...")
    # Get paths relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    data_path_1 = os.path.join(project_root, 'Movies(Tamil)2015-2025.csv')
    data_path_2 = os.path.join(project_root, 'Tamil_movies_dataset.csv')
    
    # Load first dataset
    df1 = pd.read_csv(data_path_1)
    if 'tittle' in df1.columns:
        df1 = df1.rename(columns={'tittle': 'title'})
        
    # Load second dataset
    if os.path.exists(data_path_2):
        df2 = pd.read_csv(data_path_2)
        # Rename columns to match df1
        df2 = df2.rename(columns={
            'MovieName': 'title',
            'Genre': 'genre',
            'Director': 'director',
            'Actor': 'cast'
        })
        
        # Fill missing overview for df2 using available metadata to help semantic search
        df2['overview'] = df2.apply(
            lambda row: f"A {row.get('genre', '')} film starring {row.get('cast', '')} and directed by {row.get('director', '')}.", 
            axis=1
        )
        
        # Keep only the columns we need
        cols_to_keep = ['title', 'genre', 'overview', 'director', 'cast']
        df2 = df2[[c for c in cols_to_keep if c in df2.columns]]
        df1 = df1[[c for c in cols_to_keep if c in df1.columns]]
        
        # Combine and drop duplicates based on title
        df = pd.concat([df1, df2], ignore_index=True)
        df = df.drop_duplicates(subset=['title'], keep='first')
        print(f"Combined datasets. Total movies: {len(df)}")
    else:
        df = df1
        
    # Clean data
    df['genre'] = df['genre'].fillna('')
    df['overview'] = df['overview'].fillna('')
    df['director'] = df['director'].fillna('Unknown')
    df['cast'] = df['cast'].fillna('Unknown')
    
    # Calculate Prominence Scores
    print("Calculating prominence scores...")
    df['prominence_score'] = calculate_prominence_scores(df)
    
    # Create text to embed
    df['text_to_embed'] = df.apply(lambda row: f"Genre: {row['genre']}. Overview: {row['overview']}", axis=1)
    
    # Generate embeddings
    print("Loading SentenceTransformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    print("Generating embeddings...")
    embeddings = model.encode(df['text_to_embed'].tolist(), show_progress_bar=True)
    
    # Save data
    output_dir = os.path.join(project_root, 'backend', 'data')
    os.makedirs(output_dir, exist_ok=True)
    
    print("Saving processed data...")
    # Drop the text_to_embed before saving to keep JSON small
    df_out = df.drop(columns=['text_to_embed'])
    
    # Convert to list of dicts for easy JSON parsing
    movies_list = df_out.to_dict(orient='records')
    
    with open(os.path.join(output_dir, 'movies_processed.json'), 'w', encoding='utf-8') as f:
        json.dump(movies_list, f, ensure_ascii=False, indent=2)
        
    np.save(os.path.join(output_dir, 'embeddings.npy'), embeddings)
    
    print("Done! Data saved to backend/data/")

if __name__ == "__main__":
    main()
