# OCP Alarm Intelligence — starter platform

A runnable skeleton for the alarm-analysis / root-cause platform, built to be
developed **without real plant data**. A synthetic data source mimics what a
historian will eventually feed you, sitting behind an interface you swap for a
real PI/OPC-UA connector later. Everything above acquisition is built and
tested today.

## Quick start (no infrastructure needed)

```bash
pip install -r requirements.txt
python scripts/generate_demo_data.py   # synthetic MAP-line data -> DuckDB
python scripts/dump_sample_data.py     # refresh the frontend's offline fallback
uvicorn src.api.main:app --reload      # serves BOTH the API and the dashboard
```

Then open <http://localhost:8000> — the FastAPI backend serves the dashboard at
`/` and the JSON API under `/api/*`. DuckDB is embedded, so there is no database
server to run for local dev.

`python scripts/run_analysis.py` still prints the same analysis as a text report
if you prefer the console.

## The dashboard

A single-file React app (`frontend/index.html`, no build step) styled as a
high-performance HMI console — dark by default, color only for abnormal
conditions. Views: Overview (annunciator panel + KPIs), Bad actors (Pareto),
Nuisance alarms (chattering + flood timeline), Correlations, Sequences (the
pre-incident fault chains), and Root cause (ranked candidates + confirm-to-
knowledge-base). It fetches live from `/api/*` and falls back to embedded data
(`SAMPLE DATA` badge) when the backend isn't running, so it opens standalone.

To move to a real build pipeline later, the same components port to a Vite +
React project; the API contract stays identical.

## How the layers map to the code

| Layer | Folder | What's there |
|-------|--------|--------------|
| 1 Acquisition | `src/acquisition` | `DataSource` interface, `SyntheticDataSource`, stubbed PI/OPC-UA connectors |
| 2 Preparation | `src/preparation`, `src/storage` | resample/align/outlier flags; DuckDB store (+ TimescaleDB schema) |
| 3 Analysis | `src/analysis` | bad actors, chattering, floods, co-occurrence, pre-incident sequences |
| 4 Root cause | `src/rootcause` | explainable candidate ranking + accuracy check vs ground truth |
| 5 AI | — | extension point (anomaly detection, prediction) once data is real |
| 6 Dashboard | `src/api` | FastAPI serving analysis as JSON for Grafana/React |

## The key design decision

`src/acquisition/base.py` defines `DataSource` with two methods:
`process_samples()` and `alarm_events()`. The synthetic source and the future
historian source both implement it, so **swapping to real data is a one-line
change** in `scripts/generate_demo_data.py` — nothing downstream moves.

## Swapping in real data later

1. Implement `PIHistorianDataSource` or `OpcUaDataSource` in
   `src/acquisition/historian.py` (skeletons included).
2. Point the generator at it instead of `SyntheticDataSource`.
3. For production storage, `docker compose up -d`, apply `src/storage/schema.sql`,
   and back the store with TimescaleDB instead of DuckDB.

## What's real vs. what's demo

The analytics in Layer 3 are the real, ISA-18.2 / EEMUA-191 methods you'd ship.
The synthetic generator plants known structure (a chattering transmitter,
recurring fault chains) so you can see the analytics rediscover it. The Layer 4
root-cause accuracy of 1.0 reflects clean designed data — it's a baseline
heuristic (causes precede effects), not a claim about real-world accuracy.
Real data is messier; that's where causal discovery and the Neo4j knowledge
graph come in.

## Suggested build order from here

1. Extend the analysis engine (add stale-alarm and alarm-rate-per-operator metrics).
2. Build the React RCA views against the FastAPI endpoints; wire Grafana to the store.
3. Add the knowledge graph (Neo4j) and "similar incident" vector search.
4. Only then: the Layer 5 AI models, trained on operator-confirmed cases.
