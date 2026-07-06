"""
Layer 6 backend — FastAPI.

    uvicorn src.api.main:app --reload

Serves the analysis outputs as JSON for a Grafana/React dashboard to consume.
Every endpoint just calls the same engine functions the CLI uses.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.analysis import engine
from src.rootcause import engine as rc
from src.storage.duckdb_store import DuckStore

app = FastAPI(title="OCP Alarm Intelligence", version="0.1.0")

# Dev CORS: the frontend may be served from a different origin (e.g. Vite on
# :5173). When FastAPI serves the built frontend itself, this is a no-op.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def _alarms() -> pd.DataFrame:
    df = DuckStore().alarms_df()
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"])
    return df


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/summary")
def summary():
    a = _alarms()
    if a.empty:
        return {"total_alarms": 0, "by_priority": {}, "incidents": 0,
                "bad_actor_share": 0, "flood_windows": 0, "range": None}
    active = a[a["state"] == "ACTIVE"]
    ba = engine.bad_actors(active, top=1)
    floods = engine.alarm_floods(active)
    return {
        "total_alarms": int(len(active)),
        "by_priority": active["priority"].value_counts().to_dict(),
        "incidents": int(active["incident_id"].dropna().nunique()),
        "bad_actor_share": float(ba["pct"].iloc[0]) if len(ba) else 0.0,
        "flood_windows": int(len(floods)),
        "range": [str(active["ts"].min()), str(active["ts"].max())],
    }


@app.get("/api/tags-status")
def tags_status():
    """Per-tag annunciator state: alarm load + worst active priority."""
    a = _alarms()
    active = a[a["state"] == "ACTIVE"]
    if active.empty:
        return []
    order = {"CRITICAL": 3, "HIGH": 2, "LOW": 1}
    rows = []
    for tag, g in active.groupby("tag"):
        worst = max(g["priority"], key=lambda p: order.get(p, 0))
        rows.append({"tag": tag, "alarm_count": int(len(g)),
                     "worst_priority": worst,
                     "last_ts": str(g["ts"].max())})
    return sorted(rows, key=lambda r: r["alarm_count"], reverse=True)


@app.get("/api/bad-actors")
def bad_actors(top: int = 10):
    return engine.bad_actors(_alarms(), top=top).to_dict("records")


@app.get("/api/chattering")
def chattering():
    return engine.chattering(_alarms()).to_dict("records")


@app.get("/api/floods")
def floods():
    df = engine.alarm_floods(_alarms())
    if "window_start" in df:
        df["window_start"] = df["window_start"].astype(str)
    return df.to_dict("records")


@app.get("/api/co-occurrence")
def co_occurrence():
    return engine.co_occurrence(_alarms()).to_dict("records")


@app.get("/api/sequences")
def sequences():
    return engine.pre_incident_sequences(_alarms()).to_dict("records")


@app.get("/api/root-cause")
def root_cause():
    return rc.rank_candidates(_alarms()).astype(str).to_dict("records")


# Serve the frontend so `uvicorn src.api.main:app` runs the whole app at :8000.
_frontend = Path(__file__).resolve().parents[2] / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
