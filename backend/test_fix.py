import json
import urllib.request
import urllib.parse

with open('data/movies_processed.json', 'r', encoding='utf-8') as f:
    movies_data = json.load(f)[:5]

for movie in movies_data:
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
    
    try:
        req = urllib.request.Request(search_url, headers={'User-Agent': 'TamilMoviesSort/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            search_data = json.loads(response.read())
            
        if not search_data['query']['search']:
            print(title, 'No search results')
            continue
            
        for res in search_data['query']['search'][:3]:
            res_title = res['title']
            
            sum_url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(res_title)}'
            req2 = urllib.request.Request(sum_url, headers={'User-Agent': 'TamilMoviesSort/1.0'})
            try:
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    s_data = json.loads(r2.read())
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
                        print(title, 'MATCHED', res_title, 'URL:', movie['poster_url'])
                        break 
                        
            except Exception as e:
                print(title, 'Inner error:', type(e), e)
                continue
                
    except Exception as e:
        print(title, 'Outer error:', type(e), e)
        pass
