"""
Layer 4 — Root cause (starter).

A simple, explainable first version: for each incident episode, the earliest
alarms are the strongest root-cause candidates (causes precede effects). This
is deliberately transparent — swap in causal-discovery (causal-learn / pgmpy)
and a Neo4j knowledge graph later without changing the interface.

`rank_candidates` returns, per incident, a ranked list of contributing tags.
`validate` compares the #1 candidate against synthetic ground truth so you can
measure accuracy while building — impossible with real data until operators
confirm cases.
"""
from __future__ import annotations

import pandas as pd


def rank_candidates(alarms: pd.DataFrame) -> pd.DataFrame:
    """Rank probable root-cause tags within each incident_id (synthetic only).
    Earliest-firing tag ranked first; ties broken by priority."""
    a = alarms[(alarms["state"] == "ACTIVE") & alarms["incident_id"].notna()].copy()
    if a.empty:
        return pd.DataFrame(columns=["incident_id", "rank", "tag", "level", "first_ts"])
    first = (a.sort_values("ts")
             .groupby(["incident_id", "tag"], as_index=False)
             .agg(first_ts=("ts", "min"), level=("level", "first")))
    first = first.sort_values(["incident_id", "first_ts"])
    first["rank"] = first.groupby("incident_id").cumcount() + 1
    return first[["incident_id", "rank", "tag", "level", "first_ts"]]


def validate(ranked: pd.DataFrame, ground_truth: list[dict]) -> dict:
    """Did the #1 candidate tag match the scenario's known root-cause tag?
    Uses the scenario chain's first tag as the truth label."""
    from config import SCENARIOS
    truth_tag = {s.key: s.chain[0][0] for s in SCENARIOS}
    gt = {g["incident_id"]: truth_tag[g["scenario"]] for g in ground_truth}
    top1 = ranked[ranked["rank"] == 1].set_index("incident_id")["tag"].to_dict()
    hits = sum(1 for inc, tag in top1.items() if gt.get(inc) == tag)
    n = len(top1)
    return {"incidents": n, "top1_correct": hits,
            "accuracy": round(hits / n, 3) if n else 0.0}
