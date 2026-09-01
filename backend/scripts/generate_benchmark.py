import json
import os
import random
import sys
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Please install google-genai: uv pip install google-genai")
    sys.exit(1)

def main():
    print("Loading movies_processed.json...")
    current_dir = Path(__file__).resolve().parent.parent
    data_path = current_dir / 'data' / 'movies_processed.json'
    
    with open(data_path, 'r', encoding='utf-8') as f:
        movies_data = json.load(f)
        
    print(f"Loaded {len(movies_data)} movies.")
    
    # Select 120 random movies for the benchmark
    # We will generate 40 English queries, 40 Tamil queries, 40 Tanglish queries
    random.seed(42)
    selected_movies = random.sample(movies_data, 120)
    
    english_movies = selected_movies[:40]
    tamil_movies = selected_movies[40:80]
    tanglish_movies = selected_movies[80:120]
    
    # Read API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Please set GEMINI_API_KEY environment variable.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    benchmark_data = []
    
    def generate_queries(movies, language, prompt_instruction):
        # We will batch 20 movies per request to avoid hitting the 5 RPM rate limit
        chunk_size = 20
        import time
        import pydantic
        
        class QueriesList(pydantic.BaseModel):
            queries: list[str]

        for i in range(0, len(movies), chunk_size):
            chunk = movies[i:i+chunk_size]
            prompt = prompt_instruction + "\n\nFor each of the following movies, generate the query and return them as a JSON list of strings in the EXACT same order.\n\n"
            for j, movie in enumerate(chunk):
                title = movie.get('title', '')
                overview = movie.get('overview', '')
                prompt += f"{j+1}. Title: {title}\nOverview: {overview}\n\n"
            
            try:
                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=QueriesList,
                    ),
                )
                
                result = response.parsed
                if result and len(result.queries) == len(chunk):
                    for idx, q in enumerate(result.queries):
                        print(f"[{language}] {chunk[idx]['title']}: {q}")
                        benchmark_data.append({
                            "query": q,
                            "target_title": chunk[idx]['title'],
                            "language": language,
                            "target_movie": chunk[idx]
                        })
                else:
                    print(f"Warning: Expected {len(chunk)} queries but got something else.")
                
            except Exception as e:
                print(f"Failed to generate chunk starting with {chunk[0].get('title', 'Unknown')}: {e}")
            
            # Sleep 15 seconds to stay strictly under the 5 RPM limit
            time.sleep(15)

    print("Generating English queries...")
    generate_queries(english_movies, "English", "Write a search query a user would type to find this movie. The query must be in English. It should describe the plot, characters, or vibe without using the exact title. (e.g. 'movie about a cop seeking revenge on gangsters').")
    
    print("Generating Tamil queries...")
    generate_queries(tamil_movies, "Tamil", "Write a search query a user would type to find this movie. The query must be in Tamil script. It should describe the plot, characters, or vibe without using the exact title. (e.g. 'ரவுடிகளை பழிவாங்கும் போலீஸ் படம்').")
    
    print("Generating Tanglish queries...")
    generate_queries(tanglish_movies, "Tanglish", "Write a search query a user would type to find this movie. The query must be in Tanglish (Tamil words written in English alphabet). It should describe the plot, characters, or vibe without using the exact title. (e.g. 'rowdy ah pazhivangum police padam').")
    
    out_path = current_dir / 'data' / 'benchmark_queries.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)
        
    print(f"Saved {len(benchmark_data)} benchmark queries to {out_path}")

if __name__ == "__main__":
    main()
