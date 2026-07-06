"""
Run the analysis engine over stored data and print a report.

    python scripts/run_analysis.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.analysis import engine
from src.rootcause import engine as rc
from src.storage.duckdb_store import DuckStore

pd.set_option("display.max_rows", 20)
pd.set_option("display.width", 100)


def section(title: str):
    print("\n" + "=" * 68 + f"\n  {title}\n" + "=" * 68)


def main():
    store = DuckStore()
    alarms = store.alarms_df()
    if alarms.empty:
        print("No data. Run scripts/generate_demo_data.py first.")
        return
    alarms["ts"] = pd.to_datetime(alarms["ts"])

    section("LAYER 3 · Bad actors (Pareto)")
    print(engine.bad_actors(alarms).to_string(index=False))

    section("LAYER 3 · Chattering instruments")
    ch = engine.chattering(alarms)
    print(ch.to_string(index=False) if len(ch) else "None detected.")

    section("LAYER 3 · Alarm floods (EEMUA-191: >10 / 10 min)")
    fl = engine.alarm_floods(alarms)
    print(fl.to_string(index=False) if len(fl) else "No floods.")

    section("LAYER 3 · Co-occurring alarm pairs")
    print(engine.co_occurrence(alarms).head(8).to_string(index=False))

    section("LAYER 3 · Frequent pre-incident sequences")
    print(engine.pre_incident_sequences(alarms).to_string(index=False))

    section("LAYER 4 · Root-cause ranking (first 3 incidents)")
    ranked = rc.rank_candidates(alarms)
    for inc in ranked["incident_id"].unique()[:3]:
        print(f"\n  {inc}:")
        print(ranked[ranked.incident_id == inc]
              .head(4)[["rank", "tag", "level"]].to_string(index=False))

    gt_path = Path("ground_truth.json")
    if gt_path.exists():
        section("LAYER 4 · Root-cause accuracy vs ground truth")
        gt = json.loads(gt_path.read_text())
        print(rc.validate(ranked, gt))


if __name__ == "__main__":
    main()
