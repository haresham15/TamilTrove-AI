import urllib.request
import urllib.parse
import json

def search_wiki(title, director=''):
    # Search for 'Title (film)' or 'Title (Tamil film)'
    query = f'{title} Tamil film'
    url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json'
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            if data['query']['search']:
                for res in data['query']['search'][:3]:
                    print(f"Found: {res['title']}")
                    # Fetch summary
                    sum_url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(res["title"])}'
                    req2 = urllib.request.Request(sum_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req2) as r2:
                        s_data = json.loads(r2.read())
                        print('  Extract snippet:', s_data.get('extract', '')[:100])
                        print('  Poster:', s_data.get('originalimage', {}).get('source'))
    except Exception as e:
        print('Error:', e)

search_wiki('Goli Soda')
