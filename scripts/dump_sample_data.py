"""
Dump every analysis output to frontend/sample_data.json.

The frontend embeds this as an offline fallback so the dashboard renders with
real analyzed numbers even when the API isn't running. Regenerate after
changing the data or analytics:  python scripts/dump_sample_data.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.analysis import engine
from src.rootcause import engine as rc
from src.storage.duckdb_store import DuckStore


def main():
    store = DuckStore()
    a = store.alarms_df()
    if a.empty:
        print("No data. Run scripts/generate_demo_data.py first.")
        return
    a["ts"] = pd.to_datetime(a["ts"])
    active = a[a["state"] == "ACTIVE"]

    ba = engine.bad_actors(active, top=10)
    floods = engine.alarm_floods(active)
    floods["window_start"] = floods["window_start"].astype(str)
    order = {"CRITICAL": 3, "HIGH": 2, "LOW": 1}
    tags_status = []
    for tag, g in active.groupby("tag"):
        worst = max(g["priority"], key=lambda p: order.get(p, 0))
        tags_status.append({"tag": tag, "alarm_count": int(len(g)),
                            "worst_priority": worst, "last_ts": str(g["ts"].max())})
    tags_status.sort(key=lambda r: r["alarm_count"], reverse=True)

    payload = {
        "summary": {
            "total_alarms": int(len(active)),
            "by_priority": active["priority"].value_counts().to_dict(),
            "incidents": int(active["incident_id"].dropna().nunique()),
            "bad_actor_share": float(ba["pct"].iloc[0]) if len(ba) else 0.0,
            "flood_windows": int(len(floods)),
            "range": [str(active["ts"].min()), str(active["ts"].max())],
        },
        "tags_status": tags_status,
        "bad_actors": ba.to_dict("records"),
        "chattering": engine.chattering(active).to_dict("records"),
        "floods": floods.to_dict("records"),
        "co_occurrence": engine.co_occurrence(active).to_dict("records"),
        "sequences": engine.pre_incident_sequences(active).to_dict("records"),
        "root_cause": rc.rank_candidates(a).astype(str).to_dict("records"),
    }

    out = Path(__file__).resolve().parents[1] / "frontend" / "sample_data.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {out} ({len(json.dumps(payload))} bytes)")


if __name__ == "__main__":
    main()
