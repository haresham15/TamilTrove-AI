# Product Requirements Document: TamilTrove

**Project:** TamilTrove — Multilingual Tamil-Cinema Discovery Platform  
**Status:** V2 (Production Architecture — In Progress)  
**Target Audience:** Tamil film enthusiasts, diaspora audiences, and casual viewers seeking mood/theme-based discovery  
**Last Updated:** September 2026

---

## 1. Executive Summary

TamilTrove is a multilingual movie discovery platform that lets users describe a plot, mood, theme, or viewing situation in English, Tamil, or Tanglish and receive explainable, personalized Tamil-cinema recommendations.

V2 evolves the original semantic-search demo into a full product with stable catalog identifiers, PostgreSQL/pgvector storage, hybrid retrieval, structured filters, user accounts, explicit feedback, content-based personalization, ordered collections, data-quality pipelines, a 120-query relevance evaluation suite, and production-grade observability.

---

## 2. Problem Statement & Target Audience

### 2.1 The Discovery Problem

1. **Popularity Bias:** Mainstream platforms surface blockbusters and algorithmic trending content, burying mid-budget films, indie gems, and culturally rich regional cinema.
2. **Language Barrier:** Tamil-cinema fans think in Tamil, Tanglish, and English interchangeably. Existing search systems only handle exact English keyword matching.
3. **Blank-Query Paralysis:** Users often know a mood or situation ("something like Kaithi but slower") but not a title. Keyword search fails on intent.
4. **Opaque Recommendations:** Users cannot tell why a movie was recommended, eroding trust and preventing meaningful feedback.

### 2.2 Target Personas

- **Persona A — The Diaspora Explorer (Priya, 27):** Grew up watching Tamil films, now abroad. Searches in Tanglish: *"Vijay Sethupathi nadicha crime thriller padam"*. Wants to discover beyond what YouTube algorithms push.
- **Persona B — The Mood Searcher (Karthik, 32):** Browses by feeling: *"Village setting-la emotional family drama"*. Needs intent-based retrieval, not keyword matching.
- **Persona C — The Cinephile Curator (Meera, 24):** Builds themed watchlists and shares them. Wants collections, ratings, and evidence for why a film matched.

---

## 3. Current Implementation State

### 3.1 Implemented (V2)

| Feature | Status | Key Files |
| :--- | :---: | :--- |
| **Hybrid semantic + lexical search** | ✅ | `backend/app/ranking.py`, `services.py` |
| **English, Tamil, Tanglish query normalization** | ✅ | `backend/app/normalization.py` |
| **Structured filters** (year, genre, theme, cast, crew, runtime, certificate, popularity, quality) | ✅ | `backend/app/schemas.py` |
| **Evidence-based explanations** | ✅ | `backend/app/ranking.py` (`build_explanation`) |
| **User registration, login, JWT auth** | ✅ | `backend/app/security.py`, `services.py` |
| **Ratings, likes, dismissals, watchlists** | ✅ | `backend/app/services.py`, `storage.py` |
| **Content-based personalization (user vectors)** | ✅ | `backend/app/ranking.py` (`UserSignals`) |
| **ALS collaborative recommender** | ✅ | `backend/app/recommendation.py` |
| **Private, unlisted, public collections** | ✅ | `backend/app/services.py`, `storage.py` |
| **Data ingestion & quality pipeline** | ✅ | `backend/app/ingestion.py`, `catalog.py` |
| **PostgreSQL + pgvector storage adapter** | ✅ | `backend/app/postgres.py` |
| **Local development adapter (bundled catalog)** | ✅ | `backend/app/storage.py` |
| **120-query relevance benchmark (94.2% Hit@5)** | ✅ | `evaluation/` |
| **Health, readiness, Prometheus metrics** | ✅ | `backend/app/observability.py` |
| **Next.js 16 / React 19 frontend** | ✅ | `frontend/` |
| **Discovery, detail, profile, collections, auth UI** | ✅ | `frontend/src/components/` |
| **Chat-based discovery panel** | ✅ | `frontend/src/components/chat-panel.tsx` |
| **Onboarding preference selection** | ✅ | `frontend/src/components/onboarding-page.tsx` |
| **Admin data-quality dashboard** | ✅ | `frontend/src/components/data-quality-page.tsx` |
| **Docker Compose deployment** | ✅ | `infrastructure/compose.yml` |
| **CI/CD workflows** | ✅ | `.github/` |
| **Unit, integration, E2E, load tests** | ✅ | `backend/tests/`, `frontend/tests/`, `frontend/e2e/` |

### 3.2 Future Roadmap

- Native mobile applications.
- Collaborative filtering at scale (after sufficient interaction volume).

> **Note:** Shareable collection deep links, search history tracking, and ranking A/B feature flags were originally listed here but have since been implemented in V2.

---

## 4. Product Features

### 4.1 Multilingual Hybrid Search

- **Purpose:** Let users describe what they want in any language they think in.
- **Supported Queries:**
  - English: `A political courtroom drama about injustice`
  - Tamil: `ஒரே இரவில் நடக்கும் அதிரடி திரைப்படம்`
  - Tanglish: `Kaithi maari one night action thriller`
  - Mixed: `Village setting-la emotional family drama`
- **Retrieval Pipeline:**
  1. Normalize query (whitespace, Tamil script preservation, Tanglish romanization).
  2. Detect language and parse structured hints (year, actor, director).
  3. Generate multilingual semantic embedding.
  4. Retrieve semantic candidates via pgvector cosine similarity.
  5. Retrieve lexical candidates via TF-IDF / hashing vectorizer.
  6. Fuse with reciprocal-rank fusion (configurable α weight).
  7. Apply structured filters.
  8. Rerank on relevance, preference, quality, hidden-gem, and diversity signals.
  9. Generate evidence-based explanations.
- **Empty-query mode:** Returns diverse, high-quality catalog results intentionally.

### 4.2 Structured Filters & Sorting

- Release-year range, genre/theme pills, actor/director, runtime, certificate.
- Prominence (popularity) and data-quality confidence sliders.
- Exclude watched or dismissed titles.
- Sort modes: relevance, year (asc/desc), popularity, hidden gems.

### 4.3 Evidence-Based Explanations

- Every recommendation includes a structured explanation with:
  - Summary sentence grounded in ranking evidence.
  - Evidence items (matched themes, genres, actors, semantic overlap, user preference contribution).
  - Confidence level (low / medium / high).
- Explanations never claim plot elements absent from trusted metadata.

### 4.4 User Accounts & Feedback

- Registration with email/password and password strength validation.
- JWT-based authentication.
- User profiles with display name, locale, preferences, and privacy settings.
- Explicit feedback: ratings (1–5), likes, dislikes, dismissals, watchlist saves.
- Profile page with watchlist, ratings, dismissed titles, and preference controls.
- Account data export and deletion.

### 4.5 Personalization & Recommendations

- **Content-based user vector:** Weighted from liked, rated, and saved movies; negative weights for dislikes/dismissals.
- **ALS collaborative recommender:** Available when interaction volume warrants.
- **Recommendation surfaces:**
  - Personalized "For You" feed.
  - Similar movies on detail pages.
  - Hidden gems matching user taste.
- **Cold start:** Onboarding genre/era/preference selection → curated diverse results.

### 4.6 Collections

- Create named, ordered movie collections.
- Visibility: private, unlisted, or public.
- Add, remove, and reorder items.
- Collection detail pages with metadata.

### 4.7 Chat-Based Discovery

- Conversational search panel alongside traditional search.
- Natural language queries processed through the same hybrid pipeline.

### 4.8 Data Ingestion & Quality

- Repeatable ingestion pipeline: staging → normalization → identity matching → duplicate detection → enrichment → validation → quarantine → promotion.
- Provenance tracking (source, timestamp, transformation version, confidence).
- Admin-only data-quality dashboard.
- Embedding generation with model version and content hash tracking.

---

## 5. System Architecture

```text
Next.js 16 Web App (React 19, TypeScript)
        |
        | HTTPS / JSON
        v
FastAPI Application (Python 3.12)
        |
        +-- AuthService (registration, login, JWT, profiles)
        +-- SearchService (hybrid ranking, explanations)
        +-- RecommendationService (personalized, similar, cold-start)
        +-- CollectionService (CRUD, visibility, ordering)
        +-- IngestionService (catalog sync, quality, embeddings)
        |
        +-------------------+
        |                   |
        v                   v
PostgreSQL + pgvector     Redis (optional)
        |                 cache / jobs
        v
Validated CSV / External Sources
```

### 5.1 Tech Stack

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Frontend** | Next.js 16.3 (App Router), React 19, TypeScript 5 | Server/client boundaries, streaming, strict types. |
| **Testing (FE)** | Vitest, Testing Library, Playwright, axe-core | Unit, component, E2E, and accessibility coverage. |
| **Backend** | FastAPI, Python 3.12, Pydantic v2 | Typed request/response contracts, async, OpenAPI. |
| **Search & Ranking** | scikit-learn (TF-IDF, SVD), NumPy, custom RRF | Transparent, testable, configuration-versioned ranking. |
| **Recommender** | ALS (custom implementation) | Lightweight collaborative filtering without heavy infra. |
| **Database** | PostgreSQL 15+ with pgvector, HNSW index | Stable IDs, full-text search, vector similarity. |
| **Auth** | JWT (HS256), bcrypt password hashing | Stateless, secure, dependency-minimal. |
| **Observability** | Prometheus metrics, structured JSON logs, OpenTelemetry (optional) | Request tracing, latency percentiles, alerting. |
| **Infra** | Docker Compose, GitHub Actions CI/CD | Reproducible local dev, automated quality gates. |

### 5.2 API Endpoints

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/health` | GET | Process health check |
| `/ready` | GET | Database and model readiness |
| `/metrics` | GET | Prometheus metrics |
| `/api/v1/search` | POST | Hybrid search with filters and explanations |
| `/api/v1/chat` | POST | Chat-based discovery via Gemini |
| `/api/v1/movies/{id}` | GET | Movie detail with metadata |
| `/api/v1/movies/{id}/similar` | GET | Similar movie recommendations |
| `/api/v1/recommendations` | GET | Personalized recommendations |
| `/api/v1/interactions` | POST/GET/DELETE | Ratings, likes, dismissals |
| `/api/v1/watchlist` | GET | Saved movie watchlist |
| `/api/v1/watchlist/{movie_id}` | PUT/DELETE | Add/remove from watchlist |
| `/api/v1/collections` | CRUD | User collections |
| `/api/v1/collections/{id}/share` | POST | Generate shareable deep link |
| `/api/v1/collections/shared/{token}` | GET | Access shared collection |
| `/api/v1/profile` | GET/PATCH/DELETE | User preferences, settings, and account deletion |
| `/api/v1/profile/export` | GET | GDPR-compliant account data export |
| `/api/v1/history/search` | GET/DELETE | Search history tracking |
| `/api/v1/auth/register` | POST | Account creation |
| `/api/v1/auth/login` | POST | JWT authentication |
| `/api/v1/auth/logout` | POST | Token revocation and session teardown |
| `/api/v1/admin/data-quality` | GET | Catalog quality dashboard data |
| `/api/v1/admin/experiments` | GET | Ranking A/B experiment configuration |
| `/api/v1/admin/ingestion/validate` | POST | Dry-run ingestion validation |
| `/api/v1/admin/ingestion/run` | POST | Execute ingestion pipeline |
| `/api/v1/admin/dataset/versions` | GET | List dataset version history |

---

## 6. Data Model

### Core Entities

- **Movie:** Canonical title, original title, year, runtime, certificate, overview, language, poster, source provenance, quality status.
- **Person:** Name, normalized name, biography, source URL.
- **Movie Credit:** Role type (actor, director, etc.), character name, billing order.
- **Genre / Theme:** Normalized taxonomy with many-to-many movie associations and confidence scores.
- **Movie Embedding:** Model name, version, content hash, 384-dim vector (all-MiniLM-L6-v2), timestamp.
- **User:** Email, display name, locale, preferences, privacy settings.
- **User Interaction:** Type (impression, click, save, rating, like, dislike, dismiss, viewed), numeric value, context.
- **Collection:** Name, description, visibility, ordered items.
- **Search Event:** Query, language, filters, ranking version, results, latency, interactions.

---

## 7. Evaluation & Quality

### 7.1 Relevance Benchmark

- **120 reviewed queries** spanning English, Tamil, and Tanglish slices.
- Graded relevance judgments per query-movie pair.
- **Baseline: 94.2% Hit@5** (deterministic local evaluation).

### 7.2 Metrics Tracked

- Hit@1, Hit@5, Hit@10.
- Precision@K, Recall@K.
- Mean Reciprocal Rank (MRR).
- NDCG@K (graded relevance).
- Catalog coverage and result diversity.
- Zero-result rate.
- p50, p95, p99 search latency.

### 7.3 Release Gate

A change cannot ship if it:
- Causes an unexplained relevance regression.
- Drops any language slice below its threshold.
- Breaks diversity or coverage limits.
- Exceeds latency or memory budgets.
- Fails data-quality validation.

---

## 8. Security & Privacy

- Server-side secrets only; no credentials in client bundles.
- JWT with HTTP-only cookies where applicable.
- Password strength validation and bcrypt hashing.
- Authorization checks on every user-owned resource.
- CORS restricted to known origins.
- Request-size and rate limits.
- No PII in analytics logs.
- Account export and deletion flows.

---

## 9. Testing Strategy

| Layer | Tools | Coverage |
| :--- | :--- | :--- |
| **Backend unit** | pytest | Validation, scoring, ranking, fusion, explanations, identity matching |
| **Backend integration** | pytest + test DB | Repositories, search API, auth boundaries, ingestion idempotency |
| **Frontend unit** | Vitest, Testing Library | Components, filters, states, API response validation |
| **E2E** | Playwright | Search → detail → save, auth flows, collections, keyboard navigation |
| **Accessibility** | axe-core | WCAG compliance scans |
| **Load** | k6 | Search latency under warm multilingual load |
| **Relevance regression** | Custom benchmark runner | Per-language-slice metric checks in CI |

---

## 10. Verification Commands

```bash
# Backend
cd backend
python -m ruff format --check .
python -m ruff check .
python -m mypy app main.py
python -m pytest tests

# Frontend
cd frontend
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build

# Evaluation
python evaluation/scripts/validate_dataset.py
python evaluation/scripts/evaluate.py
python evaluation/scripts/release_gate.py evaluation/reports/latest.json

# Deployment smoke
python infrastructure/scripts/smoke.py --api-url http://localhost:8000 --web-url http://localhost:3000
k6 run -e API_URL=http://localhost:8000 infrastructure/load-tests/search.js
```

---

## 11. Known Boundaries

- The bundled catalog is a development seed; source licensing and poster review are the deployer's responsibility.
- The deterministic local multilingual fallback is for reproducibility; a transformer change requires re-embedding and passing all language slices.
- Production latency depends on target database, model, and host.
- Analytics consent, retention, and legal notices must be defined before public launch.
- Redis, queues, large-scale collaborative filtering, native apps, streaming, and social features are outside the V2 scope.

---

## 12. V4 Vision: Enterprise-Grade AI Cinema Platform

V4 transitions TamilTrove from a production-quality search application into an enterprise-grade, multimodal AI system designed to demonstrate mastery of real-time distributed systems, multimodal machine learning, and cloud-native infrastructure — targeting competitive SWE and AI internship cycles for Summer 2027.

### 12.1 Multimodal Visual & Audio Search

Standard text-based NLP is table stakes. V4 parses actual cinematic assets to understand a film's aesthetic and auditory identity, fusing those signals into the existing pgvector retrieval pipeline.

#### Cinematography Analysis

- Process movie posters and trailer keyframes using a vision model (CLIP or SigLIP) to extract:
  - Color grading palettes and dominant hue distributions.
  - Contrast ratios and lighting tone (high-key vs. low-key).
  - Visual composition features (close-up intensity, wide-shot landscapes, crowd density).
- Store vision embeddings alongside text embeddings in pgvector with model version and content hash tracking.
- Fuse visual similarity scores into the existing reciprocal-rank fusion pipeline as a new signal channel.

#### Audio Profiling

- Analyze trailer soundtracks to classify the audio mix:
  - Tempo (BPM), energy envelope, and dynamic range.
  - Instrument isolation (synth-heavy, orchestral, percussion-driven, folk/acoustic).
  - Mood classification (tension, triumph, melancholy, frenzy).
- Generate audio embeddings (e.g., via CLAP or a fine-tuned audio encoder) stored in pgvector.

#### The User-Facing Feature

Users search with cross-modal queries like:

- *"Neon-lit night aesthetic with a heavy synth soundtrack"*
- *"Warm golden-hour village visuals with folk music"*
- *"Dark rain-soaked cinematography, tense orchestral score"*

The ranking pipeline fuses textual plot match, visual tone embeddings, and audio profile embeddings into a single unified relevance score with per-channel evidence in the explanation.

#### Technical Additions

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| Vision Encoder | CLIP / SigLIP (ViT-B/32 or larger) | Poster and frame embedding extraction |
| Audio Encoder | CLAP / PANNs / custom fine-tune | Trailer audio embedding extraction |
| Frame Extraction | FFmpeg pipeline | Keyframe sampling from trailers |
| Vector Storage | pgvector (additional embedding columns) | Multi-modal nearest-neighbor retrieval |
| Fusion | Extended RRF with per-modality weights | Configurable cross-modal ranking |

---

### 12.2 Real-Time Event-Driven Personalization

V2 relies on request-time preference computation. V4 processes user feedback instantly through a streaming architecture, demonstrating distributed-systems fluency.

#### Streaming Ingestion

- Implement an event-streaming backbone (AWS Kinesis, Apache Kafka, or Redis Streams) to capture every user interaction in real time:
  - Clicks, ratings, slider adjustments, search queries, dwell time, scroll depth.
  - Structured event schema with user ID, event type, movie ID, timestamp, and session context.
- Events published from the FastAPI application as fire-and-forget async producers.

#### Dynamic User Vector Updates

- Route interaction events to serverless consumers (AWS Lambda, Cloud Functions, or lightweight Faust workers) that:
  - Instantly recalculate the user's content-based preference vector.
  - Update genre/theme affinity weights and hidden-gem calibration.
  - Refresh the ALS collaborative signal incrementally (online matrix factorization update).
  - Write the updated vector back to PostgreSQL/Redis within milliseconds of the interaction.
- The next search or recommendation request reflects the feedback immediately — zero batch delay.

#### Event-Sourced Analytics

- Persist the raw event stream to a durable log (S3, GCS, or Kafka topic retention) for:
  - Offline model retraining and A/B experiment analysis.
  - Funnel and conversion analytics.
  - Replay capability for debugging and auditing.

#### Architecture Diagram

```text
User Interaction (click, rate, dismiss)
        |
        v
  FastAPI (async event producer)
        |
        v
  Event Stream (Kafka / Kinesis / Redis Streams)
        |
        +---> Consumer: User Vector Update (Lambda / Faust)
        |         |
        |         v
        |     PostgreSQL (updated preference vector)
        |
        +---> Consumer: Analytics Sink (S3 / BigQuery)
        |
        +---> Consumer: Real-Time Metrics (Prometheus / Grafana)
```

#### The Impact

This demonstrates understanding of:
- Distributed event-driven architectures and exactly-once semantics.
- Zero-latency data pipelines critical for modern full-stack ML engineering.
- Online learning and incremental model updates vs. batch retraining.
- Event sourcing as an auditability and replay mechanism.

---

### 12.3 Agentic Conversational Discovery

V4 upgrades the chat panel from a basic query parser into an autonomous recommendation agent with multi-step reasoning, tool calling, and clarification capabilities.

#### Reasoning Loop

- Integrate an agentic framework (LangGraph, LlamaIndex Workflows, or a custom ReAct loop) that:
  - Evaluates query ambiguity and autonomously asks clarifying questions before committing to a search.
  - Maintains multi-turn conversation state and preference memory within a session.
  - Decomposes complex requests into sub-queries (*"Something like Kaithi but more emotional"* → action retrieval + sentiment filtering + comparison ranking).
  - Self-evaluates result quality and refines the search if confidence is low.

#### Tool Calling

- Give the LLM direct access to TamilTrove's FastAPI endpoints as callable tools:
  - `search_movies(query, filters)` — Execute hybrid search with structured filters.
  - `get_movie_details(id)` — Retrieve full metadata for a specific film.
  - `get_similar_movies(id)` — Find related titles.
  - `get_user_preferences()` — Read the user's taste profile for personalized reasoning.
  - `record_feedback(movie_id, type)` — Save a like, dismiss, or rating mid-conversation.
- The agent decides which tools to invoke, in what order, and synthesizes results into a conversational, evidence-grounded recommendation.

#### Conversation Flow Example

```
User: "I want something intense but not action — more psychological"

Agent: [thinks] Query is ambiguous on genre. Clarify before searching.

Agent: "Are you thinking more courtroom/political tension, or
        psychological thriller with mind games?"

User: "Mind games, like a cat-and-mouse thing"

Agent: [calls search_movies("psychological thriller cat and mouse mind games",
        filters={genres: ["Thriller"]})]
Agent: [evaluates results, calls get_movie_details for top 3]
Agent: [synthesizes response with evidence]

Agent: "Here are 3 films that match — Ratsasan (2018) is the strongest
        match: a serial-killer investigation with layered psychological
        tension. 87% semantic overlap with your description, and it
        shares the investigative cat-and-mouse structure you described..."
```

#### Technical Additions

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| Agent Framework | LangGraph / LlamaIndex / custom ReAct | Multi-step reasoning and tool orchestration |
| LLM | Gemini 2.5 Flash / GPT-4o-mini | Conversational reasoning and synthesis |
| Tool Registry | FastAPI OpenAPI → tool schema mapping | Type-safe function calling |
| Session Memory | Redis or PostgreSQL JSONB | Multi-turn conversation state |
| Guardrails | Structured output validation (Pydantic) | Prevent hallucinated metadata claims |

---

### 12.4 V4 Implementation Phases

| Phase | Focus | Key Deliverables |
| :--- | :--- | :--- |
| **V3.0** | Multimodal Embeddings | CLIP poster embeddings, audio profiling pipeline, extended pgvector schema, cross-modal RRF fusion |
| **V3.1** | Streaming Infrastructure | Event schema, Kafka/Kinesis backbone, async producers, consumer scaffolding |
| **V3.2** | Real-Time Personalization | Dynamic vector updaters, online ALS increments, sub-second preference reflection |
| **V4.0** | Agentic Discovery | LangGraph agent, tool-calling integration, clarification loop, multi-turn memory |
| **V4.1** | Evaluation & Polish | Cross-modal retrieval benchmarks, agent conversation eval harness, latency profiling, portfolio documentation |

### 12.5 V4 Success Criteria

- Cross-modal search queries (visual + audio + text) return relevant results with per-modality evidence.
- User preference updates reflect in recommendations within < 500ms of interaction.
- The conversational agent autonomously clarifies ambiguous queries before searching in ≥ 80% of ambiguous test cases.
- Agent tool-calling produces zero hallucinated metadata claims (grounded in retrieved data only).
- All V2 relevance benchmarks continue to pass without regression.
- The system runs end-to-end in Docker Compose for local development and is deployable to a managed cloud environment.

---

### 12.6 V4 Unified Architecture

```text
                              ┌──────────────────────────────┐
                              │   Next.js 16 Web Application │
                              │   React 19 / TypeScript 5    │
                              └──────────────┬───────────────┘
                                             │ HTTPS / JSON
                                             v
                              ┌──────────────────────────────┐
                              │      FastAPI Application     │
                              │                              │
                              │  ┌─────────┐  ┌───────────┐ │
                              │  │  Auth    │  │  Search   │ │
                              │  │ Service  │  │  Service  │ │
                              │  └─────────┘  └───────────┘ │
                              │  ┌─────────┐  ┌───────────┐ │
                              │  │  Agent  │  │  Recs     │ │
                              │  │ Service  │  │  Service  │ │
                              │  └─────────┘  └───────────┘ │
                              │  ┌─────────────────────────┐ │
                              │  │ Async Event Producer    │ │
                              │  └────────────┬────────────┘ │
                              └───────┬───────┼──────────────┘
                                      │       │
                    ┌─────────────────┘       └──────────────────┐
                    v                                            v
     ┌──────────────────────────┐              ┌─────────────────────────┐
     │  PostgreSQL + pgvector   │              │   Event Stream          │
     │                          │              │   (Kafka / Kinesis)     │
     │  • Text embeddings       │              └────────┬────────────────┘
     │  • CLIP vision embeddings│                       │
     │  • Audio embeddings      │         ┌─────────────┼─────────────┐
     │  • User vectors          │         v             v             v
     │  • Collections & prefs   │   ┌──────────┐ ┌──────────┐ ┌───────────┐
     │  • Interaction logs      │   │  Vector  │ │ Analytics│ │  Metrics  │
     └──────────────────────────┘   │  Updater │ │   Sink   │ │  Consumer │
                                    │ (Lambda) │ │ (S3/BQ)  │ │ (Prom)    │
     ┌──────────────────────────┐   └────┬─────┘ └──────────┘ └───────────┘
     │  Embedding Pipelines     │        │
     │                          │        v
     │  • Sentence Transformers │   PostgreSQL
     │  • CLIP (posters/frames) │   (updated user vector)
     │  • CLAP (trailer audio)  │
     │  • FFmpeg (keyframes)    │
     └──────────────────────────┘

     ┌──────────────────────────┐
     │  Agentic Layer           │
     │                          │
     │  • LangGraph / ReAct     │
     │  • Tool Registry         │──── calls ──── FastAPI endpoints
     │  • Session Memory        │
     │  • Guardrails (Pydantic) │
     └──────────────────────────┘
```

---

### 12.7 V4 Infrastructure Requirements

| Concern | V2 (Current) | V4 (Target) |
| :--- | :--- | :--- |
| **Compute** | Single FastAPI process + Next.js | FastAPI + embedding workers + stream consumers + agent service |
| **Storage** | PostgreSQL + pgvector (text only) | PostgreSQL + pgvector (text, vision, audio) + object store for media |
| **Streaming** | None | Kafka / Kinesis / Redis Streams with consumer groups |
| **Serverless** | None | Lambda / Cloud Functions for event-driven vector updates |
| **Model Serving** | In-process scikit-learn | In-process scikit-learn + CLIP + CLAP + LLM API calls |
| **Media Processing** | None | FFmpeg for keyframe extraction, audio segmentation |
| **Cache** | Optional Redis | Redis for agent session memory + preference vector hot cache |
| **Observability** | Prometheus + structured logs | Prometheus + Grafana dashboards + OpenTelemetry traces + streaming lag monitors |
| **CI/CD** | GitHub Actions | GitHub Actions + model artifact registry + embedding versioning |

#### Local Development

All V4 components run in Docker Compose with optional profiles:

```bash
# Core: API + DB + Frontend
docker compose up --build

# + Streaming infrastructure
docker compose --profile streaming up --build

# + Observability stack
docker compose --profile observability up --build

# + Media processing workers
docker compose --profile media up --build
```

---

### 12.8 V4 Evaluation & Benchmarking

#### Cross-Modal Retrieval Benchmark

Extend the existing 120-query benchmark with new evaluation slices:

| Slice | Example Query | Evaluation Criteria |
| :--- | :--- | :--- |
| **Visual-only** | *"Dark, desaturated cinematography"* | Hit@5 on films with matching poster/frame palettes |
| **Audio-only** | *"High-energy percussion-driven soundtrack"* | Hit@5 on films with matching audio profiles |
| **Cross-modal** | *"Neon-lit night visuals with synth music"* | Hit@5 requiring both visual and audio match |
| **Text + Visual** | *"Village drama with warm golden-hour look"* | Fusion quality vs. text-only baseline |
| **Text + Audio** | *"Thriller with tense orchestral score"* | Fusion quality vs. text-only baseline |

Target: ≥ 75% Hit@5 on cross-modal slices without regressing text-only slices below 90%.

#### Agent Evaluation Harness

| Metric | Measurement | Target |
| :--- | :--- | :--- |
| **Clarification Rate** | % of ambiguous queries where agent asks before searching | ≥ 80% |
| **Tool-Call Accuracy** | % of tool invocations with correct parameters | ≥ 95% |
| **Grounding Fidelity** | % of claims traceable to retrieved metadata | 100% |
| **Conversation Turns** | Average turns to satisfactory recommendation | ≤ 4 |
| **Fallback Rate** | % of conversations requiring human escalation or failure | < 5% |

#### Real-Time Personalization Metrics

| Metric | Target |
| :--- | :--- |
| Event-to-vector-update latency (p95) | < 500ms |
| Preference reflection in next request | < 1s end-to-end |
| Event stream throughput | ≥ 1,000 events/sec sustained |
| Consumer lag (p99) | < 2s |

---

## 13. Portfolio & Resume Positioning

### 13.1 Technical Differentiators for Summer 2027

TamilTrove V4 demonstrates competencies across the full stack of modern AI engineering:

| Skill Domain | V2 Evidence | V4 Evidence |
| :--- | :--- | :--- |
| **Information Retrieval** | Hybrid semantic + lexical search, RRF, pgvector | Cross-modal fusion (text + vision + audio), per-modality evidence |
| **ML Engineering** | Sentence embeddings, ALS collaborative filtering, content-based user vectors | CLIP/SigLIP vision encoding, CLAP audio encoding, online incremental learning |
| **Distributed Systems** | Request-response REST, PostgreSQL transactions | Event streaming (Kafka/Kinesis), serverless consumers, exactly-once semantics |
| **Data Engineering** | Validated ingestion pipeline, provenance tracking, quality quarantine | Real-time event sourcing, replay capability, streaming analytics sink |
| **LLM / Agent Systems** | Chat-based query interface | Agentic reasoning (LangGraph/ReAct), tool calling, multi-turn memory, guardrails |
| **Evaluation & Testing** | 120-query relevance benchmark, release gates, per-language slices | Cross-modal retrieval benchmarks, agent conversation eval, streaming latency profiling |
| **Production Operations** | Health/readiness, Prometheus, structured logs, CI/CD | OpenTelemetry tracing, Grafana dashboards, consumer lag alerts, model versioning |

### 13.2 Resume Bullets

- **Multimodal Retrieval System:** *"Built a cross-modal movie discovery engine fusing text (sentence-transformer), visual (CLIP), and audio (CLAP) embeddings via extended reciprocal-rank fusion in PostgreSQL pgvector, achieving 75%+ Hit@5 on cross-modal queries."*

- **Real-Time Personalization Pipeline:** *"Architected an event-driven personalization system using Kafka/Kinesis streaming with serverless consumers that update user preference vectors within 500ms of interaction, enabling zero-batch-delay recommendation updates."*

- **Agentic Recommendation System:** *"Designed an autonomous LangGraph-based recommendation agent with tool-calling access to search, detail, and feedback APIs — achieving 80%+ autonomous clarification rate on ambiguous queries with 100% grounding fidelity (zero hallucinated metadata)."*

- **Multilingual Hybrid Search:** *"Engineered a hybrid semantic + lexical retrieval system supporting English, Tamil, and Tanglish queries with configurable rank fusion, structured filters, and evidence-based explanations — 94.2% Hit@5 on a 120-query reviewed benchmark."*

- **Production AI Evaluation:** *"Built an automated relevance evaluation harness with per-language-slice release gates, cross-modal retrieval benchmarks, agent conversation testing, and streaming latency profiling — enforced as CI quality gates blocking regression."*

---

## 14. Version History

| Version | Focus | Status |
| :--- | :--- | :--- |
| **V1.0** | Semantic search demo (NumPy + CSV) | Completed |
| **V2.0** | Production architecture: PostgreSQL/pgvector, hybrid search, auth, personalization, collections, evaluation, observability, CI/CD | Completed |
| **V3.0** | Multimodal embeddings (CLIP vision + CLAP audio), extended pgvector schema, cross-modal RRF | Planned |
| **V3.1** | Streaming infrastructure (Kafka/Kinesis), async event producers | Planned |
| **V3.2** | Real-time personalization: dynamic vector updaters, online ALS, sub-second reflection | Planned |
| **V4.0** | Agentic conversational discovery: LangGraph, tool calling, clarification loop, multi-turn memory | Planned |
| **V4.1** | Cross-modal benchmarks, agent eval harness, latency profiling, portfolio polish | Planned |
