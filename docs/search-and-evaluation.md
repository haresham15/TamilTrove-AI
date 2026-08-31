# Search, personalization, and evaluation

## Query understanding

Normalization applies Unicode NFKC, case folding where applicable, safe whitespace/punctuation cleanup, and conservative domain aliases while preserving Tamil code points. The original query and normalized form remain separate. Tamil script is detected directly; common romanized Tamil words and mixed Tamil-cinema phrasing identify Tanglish. Proper names change only through curated aliases.

An empty query is discovery mode. Explicit constraints can be supplied in the typed filter object for release year, genre/theme, cast/crew, runtime, certificate, popularity, quality, and exclusion of watched/dismissed titles. Natural-language hints may supplement but never silently override explicit filters.

## Candidate retrieval and ranking

The production design retrieves bounded semantic and lexical candidate sets from PostgreSQL/pgvector. The local adapter uses the same service contract over the bundled catalog so development remains reproducible.

Ranking uses transparent, configuration-driven evidence:

1. Multilingual semantic similarity retrieves paraphrases and plot concepts.
2. Lexical similarity covers titles, genres, themes, overviews, and exact names.
3. Reciprocal-rank or weighted fusion combines independently ranked candidates.
4. Structured constraints remove incompatible candidates.
5. Preference, data-quality, hidden-gem, and already-consumed features adjust scores.
6. Maximal marginal relevance limits near-duplicate results.
7. The explanation service selects only evidence that actually contributed.

Weights, embedding model/version, normalization version, diversity configuration, and experiment flag values form the ranking-version identifier. Development responses may expose component scores; public explanations use plain evidence rather than internal vectors or private history.

Negative signals are not interchangeable: a dismissal strongly suppresses the same movie, a dislike negatively weights its content features, and an old passive impression is weak. Explicit ratings and likes dominate clicks. Users can inspect, edit, and reset their stored preference state.

## Explanation guarantees

Every result has a summary and structured evidence. Evidence is limited to matched trusted metadata, an applied filter, a score contribution, a public popularity attribute, or a consenting user's own liked movie. The generator cannot invent a theme absent from canonical metadata. Low confidence falls back to a statement about broad genre/metadata similarity.

Public collection pages never include private personalization evidence. A phrase such as “because you liked…” is shown only to its authenticated owner.

## Versioned benchmark

`evaluation/datasets/relevance-v2.0.json` contains 120 reviewed catalog-grounded queries: 40 English, 40 Tamil, and 40 Tanglish. It deliberately includes plot, actor/director, hidden-gem, mixed-language, and structured-constraint patterns. Seed targets are unambiguous; an independent audience review remains required before publishing external model-quality claims.

The runner records:

- Hit@1/5/10, Precision@5/10, Recall@5/10, MRR, and NDCG@10;
- catalog coverage, result diversity, zero-result rate, and error rate;
- p50/p95/p99 and mean latency;
- separate language and query-category slices;
- code revision, dataset/model/ranker versions, ranking weights, runtime, and measured peak memory.

The fast PR evaluation is a deterministic lexical guardrail. Main-branch and release decisions must additionally run against the live API with its configured multilingual embedding model. The release gate requires at least 80% Hit@5, per-language floors, p95 below 750 ms, and no MRR/NDCG regression larger than two percentage points against the approved baseline.

Never tune weights on the release-test judgments. Create a development split for tuning, record every experiment, and update the approved baseline only with an explained review. Raw clicks are not relevance labels because position affects click probability.

## Current recorded baseline

The committed offline lexical baseline reaches 94.2% Hit@5 over all 120 seed queries. This is a reproducibility guardrail, not a provider-verified semantic-model or production-latency claim. Run the live-API mode in the target deployment before publishing V2 performance.
