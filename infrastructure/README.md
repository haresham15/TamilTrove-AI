# Infrastructure and production checks

Start the application with PostgreSQL/pgvector:

```bash
cp .env.example .env
docker compose --env-file .env -f infrastructure/compose.yml up --build
```

Add local metrics, traces, alerts, and the Grafana dashboard by setting `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` and adding `--profile observability`. Redis is deliberately optional; enable `--profile cache` only after configuring and measuring a cache or job workload.

Run deployment smoke checks with `python infrastructure/scripts/smoke.py --api-url https://your-api.example`. Run the warm multilingual load profile with `k6 run -e API_URL=https://your-api.example infrastructure/load-tests/search.js`. The checked-in thresholds enforce less than 1% errors, search p95 below 750 ms, and p99 below 1.5 seconds.

Validate Compose, observability YAML, dashboards, pinned workflow actions, example environment keys, and local documentation links before opening a pull request:

```bash
python -m pip install -r infrastructure/requirements-validation.txt
python infrastructure/scripts/validate_config.py
docker compose --env-file .env.example -f infrastructure/compose.yml config --quiet
```

All Compose host ports bind to loopback. The `database`, `backend`, and `frontend` services form the default profile; cache and telemetry services remain opt-in.

Compose is intended for local integration and single-host demonstrations. A public deployment must replace all development passwords, terminate TLS at a trusted proxy, restrict database/metrics ports, use a managed secret store, persist encrypted backups, and configure a durable trace exporter instead of the collector's local debug exporter.
