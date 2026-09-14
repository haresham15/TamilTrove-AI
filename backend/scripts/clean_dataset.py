import json
import os
import re
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

def clean_title(title: str) -> str:
    cleaned = re.sub(r"\s*\((?:U|A|UA|U/A)\)\s*$", "", title, flags=re.IGNORECASE).strip()
    return cleaned

def extract_cert(title: str) -> str | None:
    match = re.search(r"\((U|A|UA|U/A)\)\s*$", title, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    root_dir = os.path.dirname(backend_dir)
    
    csv_path = os.path.join(root_dir, "Movies(Tamil)2015-2025.csv")
    json_path = os.path.join(backend_dir, "data", "movies_processed.json")
    npy_path = os.path.join(backend_dir, "data", "embeddings.npy")
    
    print("Loading CSV and JSON...")
    df_csv = pd.read_csv(csv_path)
    if "tittle" in df_csv.columns:
        df_csv = df_csv.rename(columns={"tittle": "title"})
    
    with open(json_path, "r", encoding="utf-8") as f:
        movies = json.load(f)
        
    print(f"Loaded {len(movies)} processed movies and {len(df_csv)} CSV rows.")
    
    csv_map = {}
    for idx, row in df_csv.iterrows():
        r_dict = row.to_dict()
        t = str(r_dict.get("title", "")).strip().lower()
        clean_t = clean_title(t).lower()
        csv_map[t] = r_dict
        csv_map[clean_t] = r_dict
        csv_map[re.sub(r"[^a-z0-9]", "", clean_t)] = r_dict

    KNOWN_POSTERS = {
        "Aambala": "https://upload.wikimedia.org/wikipedia/en/e/e6/Aambala_poster.jpg",
        "Darling": "https://upload.wikimedia.org/wikipedia/en/8/87/Darling_Movie_Poster.jpg",
        "Kakki Sattai": "https://upload.wikimedia.org/wikipedia/en/2/21/Kaaki_Sattai_2015_poster.jpg",
        "Kaakki Sattai": "https://upload.wikimedia.org/wikipedia/en/2/21/Kaaki_Sattai_2015_poster.jpg",
        "Enakkul Oruvan": "https://upload.wikimedia.org/wikipedia/en/d/dc/Enakkul_Oruvan_2015.jpg",
        "Deiva Thirumagal": "https://upload.wikimedia.org/wikipedia/en/7/7b/Deiva_Thirumagal_poster.jpg",
        "Vazhakku Enn 18/9": "https://upload.wikimedia.org/wikipedia/en/b/b3/Vazhakku_Enn_18_9_poster.jpg",
        "Visaaranai": "https://upload.wikimedia.org/wikipedia/en/a/a4/Visaaranai_poster.jpg",
        "2.0": "https://upload.wikimedia.org/wikipedia/en/c/cf/2.0_film_poster.jpg",
        "2": "https://upload.wikimedia.org/wikipedia/en/c/cf/2.0_film_poster.jpg",
        "Crime 23": "https://upload.wikimedia.org/wikipedia/en/1/1d/Kuttram_23_Poster.jpg",
        "Kuttram 23": "https://upload.wikimedia.org/wikipedia/en/1/1d/Kuttram_23_Poster.jpg",
        "Kaithi": "https://upload.wikimedia.org/wikipedia/en/7/79/Kaithi_2019_poster.jpg",
        "Jai Bhim": "https://upload.wikimedia.org/wikipedia/en/a/ad/Jai_Bhim_film_poster.jpg",
        "Master": "https://upload.wikimedia.org/wikipedia/en/5/53/Master_2021_poster.jpg",
        "Vikram": "https://upload.wikimedia.org/wikipedia/en/9/93/Vikram_2022_poster.jpg",
        "Leo": "https://upload.wikimedia.org/wikipedia/en/7/75/Leo_%282023_Indian_film%29.jpg",
        "Jailer": "https://upload.wikimedia.org/wikipedia/en/c/cb/Jailer_2023_Tamil_film_poster.jpg",
    }

    KNOWN_COMPOSERS = {
        "Leo": "Anirudh Ravichander",
        "Jailer": "Anirudh Ravichander",
        "Vikram": "Anirudh Ravichander",
        "Master": "Anirudh Ravichander",
        "Beast": "Anirudh Ravichander",
        "Doctor": "Anirudh Ravichander",
        "Don": "Anirudh Ravichander",
        "Petta": "Anirudh Ravichander",
        "Darbar": "Anirudh Ravichander",
        "Thiruchitrambalam": "Anirudh Ravichander",
        "Kaathuvaakula Rendu Kaadhal": "Anirudh Ravichander",
        "Velaikkaran": "Anirudh Ravichander",
        "Vivegam": "Anirudh Ravichander",
        "Remo": "Anirudh Ravichander",
        "Naanum Rowdy Dhaan": "Anirudh Ravichander",
        "Vedalam": "Anirudh Ravichander",
        "Maari": "Anirudh Ravichander",
        "Thaanaa Serndha Koottam": "Anirudh Ravichander",
        "Kolamavu Kokila": "Anirudh Ravichander",
        "Indian 2": "Anirudh Ravichander",
        "Vettaiyan": "Anirudh Ravichander",
        "Kaththi": "Anirudh Ravichander",
        "Mersal": "A. R. Rahman",
        "Bigil": "A. R. Rahman",
        "Sarkar": "A. R. Rahman",
        "Ponniyin Selvan: I": "A. R. Rahman",
        "Ponniyin Selvan: II": "A. R. Rahman",
        "2.0": "A. R. Rahman",
        "Ayalaan": "A. R. Rahman",
        "Vendhu Thanindhathu Kaadu": "A. R. Rahman",
        "Raayan": "A. R. Rahman",
        "Cobra": "A. R. Rahman",
        "24": "A. R. Rahman",
        "Kaatru Veliyidai": "A. R. Rahman",
        "Chekka Chivantha Vaanam": "A. R. Rahman",
        "I": "A. R. Rahman",
        "Sarvam Thaala Mayam": "A. R. Rahman",
        "Achcham Yenbadhu Madamaiyada": "A. R. Rahman",
        "Maanaadu": "Yuvan Shankar Raja",
        "The Greatest of All Time": "Yuvan Shankar Raja",
        "Valimai": "Yuvan Shankar Raja",
        "Nerkonda Paarvai": "Yuvan Shankar Raja",
        "Super Deluxe": "Yuvan Shankar Raja",
        "Love Today": "Yuvan Shankar Raja",
        "Pyaar Prema Kaadhal": "Yuvan Shankar Raja",
        "Dharma Durai": "Yuvan Shankar Raja",
        "Iraivi": "Yuvan Shankar Raja",
        "Maari 2": "Yuvan Shankar Raja",
        "NGK": "Yuvan Shankar Raja",
        "Hero": "Yuvan Shankar Raja",
        "Kabali": "Santhosh Narayanan",
        "Kaala": "Santhosh Narayanan",
        "Vada Chennai": "Santhosh Narayanan",
        "Sarpatta Parambarai": "Santhosh Narayanan",
        "Karnan": "Santhosh Narayanan",
        "Mahaan": "Santhosh Narayanan",
        "Chithha": "Santhosh Narayanan",
        "Jigarthanda DoubleX": "Santhosh Narayanan",
        "Pariyerum Perumal": "Santhosh Narayanan",
        "Irudhi Suttru": "Santhosh Narayanan",
        "Bairavaa": "Santhosh Narayanan",
        "Kodi": "Santhosh Narayanan",
        "Kalki 2898 AD": "Santhosh Narayanan",
        "Vikram Vedha": "Sam C. S.",
        "Kaithi": "Sam C. S.",
        "Iravukku Aayiram Kangal": "Sam C. S.",
        "Adanga Maru": "Sam C. S.",
        "Yennai Arindhaal": "Harris Jayaraj",
        "Iru Mugan": "Harris Jayaraj",
        "Si3": "Harris Jayaraj",
        "Singam 3": "Harris Jayaraj",
        "Kavan": "Harris Jayaraj",
        "Dev": "Harris Jayaraj",
        "Kaappaan": "Harris Jayaraj",
        "The Legend": "Harris Jayaraj",
        "Thunivu": "Ghibran",
        "Ratsasan": "Ghibran",
        "Theeran Adhigaaram Ondru": "Ghibran",
        "Papanasam": "Ghibran",
        "Saaho": "Ghibran",
        "Vishwaroopam II": "Ghibran",
        "Asuran": "G. V. Prakash Kumar",
        "Soorarai Pottru": "G. V. Prakash Kumar",
        "Captain Miller": "G. V. Prakash Kumar",
        "Vaathi": "G. V. Prakash Kumar",
        "Theri": "G. V. Prakash Kumar",
        "Thalaivi": "G. V. Prakash Kumar",
        "Bachelor": "G. V. Prakash Kumar",
        "Sardar": "G. V. Prakash Kumar",
        "Viswasam": "D. Imman",
        "Annaatthe": "D. Imman",
        "Tik Tik Tik": "D. Imman",
        "Kadaikutty Singam": "D. Imman",
        "Miruthan": "D. Imman",
        "Namma Veettu Pillai": "D. Imman",
        "Thani Oruvan": "Hiphop Tamizha",
        "Aambala": "Hiphop Tamizha",
        "Imaikkaa Nodigal": "Hiphop Tamizha",
        "Meesaya Murukku": "Hiphop Tamizha",
        "Natpe Thunai": "Hiphop Tamizha",
        "Action": "Hiphop Tamizha",
    }

    BAD_POSTER_PATTERNS = [
        "director", "launch", "event", "press", "audio", "actor",
        "at_an_", "at_the_", "cropped", "awards", "book"
    ]

    fixed_overviews = 0
    fixed_posters = 0
    fixed_years = 0

    cleaned_movies = []
    texts_to_embed = []

    for i, m in enumerate(movies):
        title = m.get("title", "").strip()
        canonical_title = clean_title(title)
        cert = extract_cert(title) or m.get("certificate")
        
        t_key = title.lower()
        clean_key = canonical_title.lower()
        flat_key = re.sub(r"[^a-z0-9]", "", clean_key)
        csv_row = csv_map.get(t_key)
        if csv_row is None:
            csv_row = csv_map.get(clean_key)
        if csv_row is None:
            csv_row = csv_map.get(flat_key)
        
        overview = m.get("overview", "").strip()
        is_corrupted = False
        overview_lower = overview.lower()
        if (
            "is an indian film director" in overview_lower
            or "is an indian actor" in overview_lower
            or "is an indian film producer" in overview_lower
            or "is an indian politician" in overview_lower
            or "known professionally as vikram" in overview_lower
            or "veerapandiya kattabomman is a 1959" in overview_lower
            or "darling, darling, darling is a 1982" in overview_lower
            or "kaakki sattai is a 1985" in overview_lower
            or "enakkul oruvan is a 1984" in overview_lower
            or (title in ["2", "2.0"] and "jailer is a 2023" in overview_lower)
            or (canonical_title == "Aambala" and "veerapandiya" in overview_lower)
            or (canonical_title == "Sandamarudham" and "a. venkatesh is an" in overview_lower)
            or (canonical_title == "Visaaranai" and "aadukalam murugadoss" in overview_lower)
            or (canonical_title == "The Fly" and "eega is a" in overview_lower)
            or (canonical_title == "Crime 23" and "dc is a" in overview_lower)
            or (canonical_title == "Bommai" and "1964" in overview_lower)
            or (canonical_title == "Achamillai Achamillai" and "1984" in overview_lower)
            or (canonical_title == "Magalir Mattum" and "1994" in overview_lower)
            or (canonical_title == "Neeya 2" and "1979" in overview_lower)
            or (canonical_title == "Rudra Thandavam" and "1978" in overview_lower)
            or (canonical_title == "Vikram" and "1986" in overview_lower)
        ):
            is_corrupted = True

        if is_corrupted and csv_row is not None:
            csv_overview = str(csv_row.get("overview", "")).strip()
            if csv_overview and len(csv_overview) > 15:
                overview = csv_overview
                fixed_overviews += 1
        elif is_corrupted and not overview:
            if csv_row is not None:
                overview = str(csv_row.get("overview", "")).strip()
                fixed_overviews += 1

        release_year = m.get("release_year")
        if canonical_title == "Vikram":
            release_year = 2022
            overview = "A special investigator is assigned to track down a masked drug cartel, uncovering a web of crime, corruption, and the legacy of a retired black-ops commander."
            fixed_overviews += 1
        elif canonical_title == "Aambala": release_year = 2015
        elif canonical_title == "Darling": release_year = 2015
        elif canonical_title in ["Kakki Sattai", "Kaakki Sattai"]: release_year = 2015
        elif canonical_title == "Enakkul Oruvan": release_year = 2015
        elif canonical_title in ["2", "2.0"]: release_year = 2018
        elif canonical_title == "Deiva Thirumagal": release_year = 2011
        elif canonical_title == "Sandamarudham": release_year = 2015
        elif canonical_title == "Visaaranai": release_year = 2015
        elif canonical_title == "Vazhakku Enn 18/9": release_year = 2012
        elif canonical_title == "Crime 23": release_year = 2017
        elif canonical_title == "Bommai": release_year = 2023
        elif canonical_title == "Achamillai Achamillai": release_year = 2024
        elif csv_row is not None and "index" in csv_row:
            if release_year is not None and release_year < 2010 and canonical_title != "12-12-1950":
                release_year = 2015 + (int(csv_row["index"]) // 80)
                release_year = min(release_year, 2024)
                fixed_years += 1

        poster_url = m.get("poster_url")
        if canonical_title in KNOWN_POSTERS:
            poster_url = KNOWN_POSTERS[canonical_title]
            fixed_posters += 1
        elif poster_url:
            p_lower = poster_url.lower()
            if any(bad in p_lower for bad in BAD_POSTER_PATTERNS):
                poster_url = None
                fixed_posters += 1
            elif "veerapandiya_kattabomman" in p_lower and canonical_title != "Veerapandiya Kattabomman":
                poster_url = None
                fixed_posters += 1
            elif "darling%2c_darling%2c_darling" in p_lower:
                poster_url = KNOWN_POSTERS["Darling"]
                fixed_posters += 1
            elif "kaakki_sattai_poster.jpg" in p_lower:
                poster_url = KNOWN_POSTERS["Kakki Sattai"]
                fixed_posters += 1
            elif "enakkul_oruvan_1984" in p_lower:
                poster_url = KNOWN_POSTERS["Enakkul Oruvan"]
                fixed_posters += 1
            elif "jailer_2023" in p_lower and canonical_title in ["2", "2.0"]:
                poster_url = KNOWN_POSTERS["2.0"]
                fixed_posters += 1

        display_title = canonical_title
        if canonical_title == "2":
            display_title = "2.0"
            canonical_title = "2.0"

        director = m.get("director") or (str(csv_row.get("director", "")) if csv_row is not None else "")
        if canonical_title == "Vikram":
            director = "Lokesh Kanagaraj"
            cast = "Kamal Haasan, Vijay Sethupathi, Fahadh Faasil, Suriya"
            genre = "Action Thriller"
        elif canonical_title == "Ace":
            director = "Arumuga Kumar"
            cast = "Vijay Sethupathi, Rukmini Vasanth, Yogi Babu"
            genre = "Romantic Crime Comedy"
        else:
            cast = m.get("cast") or (str(csv_row.get("cast", "")) if csv_row is not None else "")
            genre = m.get("genre") or (str(csv_row.get("genre", "")) if csv_row is not None else "")


        composer = KNOWN_COMPOSERS.get(canonical_title, "")
        if not composer and overview:
            match = re.search(r'(?:music|soundtrack|score)\s+(?:is|was)?\s*(?:composed|scored)?\s*by\s+([A-Z][A-Za-z\.\s]+?)(?:,|\.|\sand\s|\swith\s)', overview)
            if match:
                composer = match.group(1).strip()

        updated_movie = dict(m)
        updated_movie["title"] = display_title
        updated_movie["canonical_title"] = canonical_title
        updated_movie["overview"] = overview
        if release_year:
            updated_movie["release_year"] = int(release_year)
        if cert:
            updated_movie["certificate"] = cert
        updated_movie["director"] = director
        updated_movie["cast"] = cast
        updated_movie["genre"] = genre
        updated_movie["music_director"] = composer
        updated_movie["poster_url"] = poster_url

        cleaned_movies.append(updated_movie)

        rich_text = f"Title: {display_title}. Directed by {director}. Starring {cast}. Music by {composer}. Genre: {genre}. {overview}".strip()
        texts_to_embed.append(rich_text)

    print(f"Sanitization complete: Fixed {fixed_overviews} overviews, {fixed_posters} posters, {fixed_years} years.")
    
    print("Saving sanitized movies_processed.json...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_movies, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(cleaned_movies)} records to {json_path}.")

    print("Computing rich embeddings with all-MiniLM-L6-v2...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(texts_to_embed, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.asarray(embeddings, dtype=np.float32)

    print(f"Saving embeddings shape {embeddings.shape} to {npy_path}...")
    np.save(npy_path, embeddings)
    print("Precomputed embeddings successfully updated!")

if __name__ == "__main__":
    main()
