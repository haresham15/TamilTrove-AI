import json
import os
import sys
import time
from pathlib import Path

import pydantic

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Please install google-genai: uv pip install google-genai")
    sys.exit(1)

class Triplet(pydantic.BaseModel):
    query: str
    hard_negative_title: str

class TripletsList(pydantic.BaseModel):
    triplets: list[Triplet]

def main():
    print("Loading movies_processed.json...")
    current_dir = Path(__file__).resolve().parent.parent
    data_dir = current_dir / 'data'
    
    movies_path = data_dir / 'movies_processed.json'
    with open(movies_path, encoding='utf-8') as f:
        movies_data = json.load(f)
        
    benchmark_path = data_dir / 'benchmark_queries.json'
    benchmark_titles = set()
    if benchmark_path.exists():
        with open(benchmark_path, encoding='utf-8') as f:
            bm_data = json.load(f)
            benchmark_titles = {item['target_title'] for item in bm_data}
            
    print(f"Loaded {len(movies_data)} movies. Found {len(benchmark_titles)} in benchmark to exclude.")
    
    train_movies = [m for m in movies_data if m.get('title') not in benchmark_titles and m.get('overview')]
    
    # Read API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Please set GEMINI_API_KEY environment variable.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    triplets = []
    
    print(f"Generating triplets for {len(train_movies)} training movies...")
    
    chunk_size = 20
    
    for i in range(0, len(train_movies), chunk_size):
        chunk = train_movies[i:i+chunk_size]
        
        prompt = """
For each of the following movies, generate a 'query' and a 'hard_negative_title'.

1. query: Write a search query (can be English, Tamil, or Tanglish) that perfectly describes the plot or vibe of the movie. Do not use the exact title.
2. hard_negative_title: Pick the exact title of ANOTHER movie from the provided list that is somewhat similar in genre or keywords, but definitely NOT a match for the query. (e.g. if the query is 'cop seeking revenge', pick another cop movie as the hard negative).

Return the results as a JSON list of objects in the EXACT same order as the input movies.
"""
        for j, movie in enumerate(chunk):
            title = movie.get('title', '')
            overview = movie.get('overview', '')
            prompt += f"\n{j+1}. Title: {title}\nOverview: {overview}\n"

        # Try generating chunk with retries
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=TripletsList,
                    ),
                )
                
                result = response.parsed
                if result and len(result.triplets) == len(chunk):
                    for idx, t in enumerate(result.triplets):
                        anchor_movie = chunk[idx]
                        print(f"[{i+idx+1}/{len(train_movies)}] {anchor_movie.get('title')} -> Query: {t.query} | Hard Neg: {t.hard_negative_title}")
                        
                        # Find the hard negative movie object
                        hard_neg_title = t.hard_negative_title
                        hard_neg_movie = next((m for m in movies_data if m.get('title') == hard_neg_title), None)
                        
                        if not hard_neg_movie:
                            hard_neg_movie = next((m for m in movies_data if m.get('title') != anchor_movie.get('title')), None)
                        
                        triplets.append({
                            "query": t.query,
                            "positive_movie": anchor_movie,
                            "hard_negative_movie": hard_neg_movie
                        })
                    break # Success, exit retry loop
                else:
                    print(f"Warning: Expected {len(chunk)} triplets but got {len(result.triplets) if result else 0}. Retrying...")
                    time.sleep(10 * (attempt + 1))
                    
            except Exception as e:
                print(f"Attempt {attempt + 1} failed for chunk starting with {chunk[0].get('title', 'Unknown')}: {e}")
                time.sleep(20 * (attempt + 1))
        else:
            print(f"Failed to generate chunk starting with {chunk[0].get('title', 'Unknown')} after {max_retries} attempts. Skipping.")
        
        # Sleep 15 seconds to stay strictly under the 5 RPM limit
        time.sleep(15)
            
    out_path = data_dir / 'training_triplets.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(triplets, f, ensure_ascii=False, indent=2)
        
    print(f"Saved {len(triplets)} triplets to {out_path}")

if __name__ == "__main__":
    main()
