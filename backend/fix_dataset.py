import json
import urllib.request
import urllib.parse
import os
import time
import concurrent.futures
from threading import Lock
import urllib.error

# Get the path to movies_processed.json
current_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(current_dir, 'data', 'movies_processed.json')

with open(data_path, 'r', encoding='utf-8') as f:
    movies_data = json.load(f)

print_lock = Lock()
processed_count = 0
total_movies = len(movies_data)

def fetch_wiki_data(movie):
    global processed_count
    title = movie.get('title', '')
    director = movie.get('director', '').lower()
    
    cast_str = movie.get('cast', '')
    cast_members = [c.strip().lower() for c in cast_str.split(',') if c.strip()]
    
    director_parts = [p for p in director.split() if len(p) > 2]
    cast_parts = []
    for c in cast_members:
        cast_parts.extend([p for p in c.split() if len(p) > 2])

    query = f'{title} Tamil film'
    search_url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json'
    
    headers = {'User-Agent': 'TamilMoviesSortBot/1.0 (test@example.com)'}
    
    def do_request(url):
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(1.5 ** attempt) # Exponential backoff
                else:
                    return None
            except Exception:
                time.sleep(1)
        return None

    try:
        search_data = do_request(search_url)
        if search_data and search_data.get('query', {}).get('search'):
            for res in search_data['query']['search'][:3]:
                res_title = res['title']
                sum_url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(res_title)}'
                s_data = do_request(sum_url)
                
                if s_data:
                    extract = s_data.get('extract', '').lower()
                    is_match = False
                    if director_parts and any(dp in extract for dp in director_parts):
                        is_match = True
                    elif cast_parts and any(cp in extract for cp in cast_parts):
                        is_match = True
                        
                    if not is_match and res_title.lower() == f"{title.lower()} (film)":
                        is_match = True
                    
                    if is_match or res_title.lower().startswith(title.lower()):
                        movie['overview'] = s_data.get('extract', movie.get('overview'))
                        img_info = s_data.get('originalimage') or {}
                        movie['poster_url'] = img_info.get('source', None)
                        break 
                        
    except Exception as e:
        pass
        
    with print_lock:
        processed_count += 1
        if processed_count % 50 == 0:
            print(f"Processed {processed_count}/{total_movies} movies...")

print(f"Starting Wikipedia data augmentation for {total_movies} movies...")

# Run concurrently with fewer workers to avoid hammering Wikipedia
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    executor.map(fetch_wiki_data, movies_data)

print("Saving updated dataset...")
with open(data_path, 'w', encoding='utf-8') as f:
    json.dump(movies_data, f, ensure_ascii=False, indent=2)
    
print("Data augmentation complete!")
