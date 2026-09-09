"""Generate V4 cross-modal benchmark dataset (crossmodal-v4.0.json)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.catalog import Catalog

def main() -> None:
    cat = Catalog.load(ROOT / "backend" / "data" / "movies_processed.json")
    movies = cat.movies

    queries = []

    # 1. visual-only (10 queries)
    visual_queries = [
        ("Dark desaturated rain-soaked cinematography", "dark", ["dark", "noir"]),
        ("Neon-lit cyberpunk night city aesthetic", "neon", ["neon"]),
        ("Warm golden-hour village visual tone", "golden-hour", ["golden-hour"]),
        ("Vibrant colorful festival visual grading", "vibrant", ["vibrant"]),
        ("Vintage monochrome period film look", "vintage", ["vintage"]),
        ("Dark gritty alleyways and shadow lighting", "dark", ["dark", "noir"]),
        ("High contrast neon glow and laser lights", "neon", ["neon"]),
        ("Sunset golden hour rural countryside landscape", "golden-hour", ["golden-hour"]),
        ("Classic retro 1980s film aesthetic", "vintage", ["vintage"]),
        ("Bleak desaturated noir detective tone", "dark", ["noir", "dark"]),
    ]
    for q, aesthetic, tags in visual_queries:
        matches = [m.id for m in movies if any(t in m.visual_palette.get("aesthetic_tags", []) for t in tags)]
        queries.append({
            "id": f"cm-v-{len(queries)+1}",
            "slice": "visual-only",
            "query": q,
            "visual_query": q,
            "audio_query": "",
            "expected_tags": tags,
            "relevant_movie_ids": matches,
        })

    # 2. audio-only (10 queries)
    audio_queries = [
        ("High-energy fast percussion-driven beats", "percussion", ["percussion"]),
        ("Heavy synth electronic 808 soundtrack", "synth", ["synth"]),
        ("Tense orchestral symphony with strings", "orchestral", ["orchestral"]),
        ("Soft acoustic guitar with gentle flute melody", "acoustic", ["acoustic"]),
        ("Traditional rural folk thavil nadaswaram", "folk", ["folk"]),
        ("Fast BPM frenzy action beats", "frenzy", ["percussion"]),
        ("Heartbeat tension suspense score", "tension", ["orchestral"]),
        ("Melancholic violin acoustic grief soundtrack", "melancholy", ["acoustic", "orchestral"]),
        ("Upbeat celebratory festival brass music", "triumph", ["percussion"]),
        ("Ambient eerie haunting electronic whispers", "eerie", ["synth"]),
    ]
    for q, mood_or_inst, insts in audio_queries:
        matches = [
            m.id for m in movies
            if any(i in m.audio_profile.get("instruments", []) for i in insts)
            or m.audio_profile.get("mood") == mood_or_inst
        ]
        queries.append({
            "id": f"cm-a-{len(queries)+1}",
            "slice": "audio-only",
            "query": q,
            "visual_query": "",
            "audio_query": q,
            "expected_instruments": insts,
            "relevant_movie_ids": matches,
        })

    # 3. cross-modal (10 queries)
    cross_queries = [
        ("Neon-lit night visuals with heavy synth soundtrack", ["neon"], ["synth"]),
        ("Dark rain-soaked cinematography with tense orchestral score", ["dark", "noir"], ["orchestral"]),
        ("Warm golden-hour village visuals with acoustic folk music", ["golden-hour"], ["folk"]),
        ("Vibrant colorful festival look with upbeat percussion beats", ["vibrant"], ["percussion"]),
        ("Bleak noir crime visuals with haunting ambient synth", ["noir", "dark"], ["synth"]),
        ("Gritty raw action look with fast-paced heavy percussion", ["gritty", "dark"], ["percussion"]),
        ("Vintage period aesthetic with classical orchestral symphony", ["vintage"], ["orchestral"]),
        ("Rural village golden hour sunset with traditional thavil music", ["golden-hour"], ["folk"]),
        ("Dark sinister shadows with eerie horror soundscape", ["dark"], ["synth"]),
        ("Sleek high-contrast neon lights with pulsating electronic bass", ["neon"], ["synth"]),
    ]
    for q, v_tags, a_insts in cross_queries:
        matches = [
            m.id for m in movies
            if any(t in m.visual_palette.get("aesthetic_tags", []) for t in v_tags)
            and any(i in m.audio_profile.get("instruments", []) for i in a_insts)
        ]
        if not matches:
            matches = [m.id for m in movies if any(t in m.visual_palette.get("aesthetic_tags", []) for t in v_tags)]
        queries.append({
            "id": f"cm-x-{len(queries)+1}",
            "slice": "cross-modal",
            "query": q,
            "visual_query": q,
            "audio_query": q,
            "expected_tags": v_tags,
            "expected_instruments": a_insts,
            "relevant_movie_ids": matches,
        })

    # 4. text+visual (5 queries)
    tv_queries = [
        ("Police officer murder investigation with dark gritty aesthetic", "murder investigation", "dark crime", ["dark", "noir"]),
        ("Village family reunion with warm golden-hour look", "family village reunion", "village golden", ["golden-hour"]),
        ("Undercover cop fighting gangster syndicate with neon night visuals", "undercover cop gangster", "neon night", ["neon"]),
        ("College romance love story with vibrant colorful palette", "college romance", "vibrant colorful", ["vibrant"]),
        ("Historical freedom struggle with vintage sepia tone", "historical freedom struggle", "vintage sepia", ["vintage"]),
    ]
    for q, text_q, vis_q, tags in tv_queries:
        matches = [
            m.id for m in movies
            if any(t in m.visual_palette.get("aesthetic_tags", []) for t in tags)
            and any(g in m.genres for g in ("crime", "drama", "action", "romance"))
        ]
        queries.append({
            "id": f"cm-tv-{len(queries)+1}",
            "slice": "text+visual",
            "query": q,
            "text_query": text_q,
            "visual_query": vis_q,
            "audio_query": "",
            "expected_tags": tags,
            "relevant_movie_ids": matches,
        })

    # 5. text+audio (5 queries)
    ta_queries = [
        ("Psychological serial killer thriller with tense orchestral score", "serial killer thriller", "tense orchestral score", ["orchestral"]),
        ("High-stakes car chase action with fast percussion soundtrack", "car chase action", "fast percussion beats", ["percussion"]),
        ("Tragic village drama with sorrowful acoustic folk melody", "village drama tragedy", "sorrowful folk melody", ["folk", "acoustic"]),
        ("Romantic comedy with cheerful acoustic guitar music", "romantic comedy", "cheerful acoustic music", ["acoustic"]),
        ("Haunted house mystery with eerie ambient sound design", "haunted house mystery", "eerie ambient soundscape", ["synth"]),
    ]
    for q, text_q, aud_q, insts in ta_queries:
        matches = [m.id for m in movies if any(i in m.audio_profile.get("instruments", []) for i in insts)]
        queries.append({
            "id": f"cm-ta-{len(queries)+1}",
            "slice": "text+audio",
            "query": q,
            "text_query": text_q,
            "visual_query": "",
            "audio_query": aud_q,
            "expected_instruments": insts,
            "relevant_movie_ids": matches,
        })

    out_path = ROOT / "evaluation" / "datasets" / "crossmodal-v4.0.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"version": "v4.0", "total_queries": len(queries), "queries": queries}, f, indent=2)

    print(f"Generated {out_path} with {len(queries)} queries.")


if __name__ == "__main__":
    main()
