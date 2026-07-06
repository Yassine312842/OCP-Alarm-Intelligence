"""
EEMUA-191 alarm management KPIs for OCP Alarm Intelligence.

Assumes alarm events arrive as a pandas DataFrame (from the synthetic
source today, the historian/OPC feed later) with at least these columns:

    timestamp    : datetime64, when the alarm event occurred
    tag          : str, alarm/tag identifier
    description  : str
    priority     : str, one of 'critical' | 'high' | 'medium' | 'low'
    operator_id  : str
    state        : str, one of 'active' | 'acknowledged' | 'cleared'

Adjust the column names in COLUMN MAP below if your synthetic generator
uses different names — the functions reference the constants, not the
literal strings, so it's a one-line change per column.

Reference: EEMUA 191 (3rd edition) target rates and definitions summarized
inline where used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

# ---------------------------------------------------------------------------
# Column map — change these if your schema differs
# ---------------------------------------------------------------------------
COL_TIMESTAMP = "timestamp"
COL_TAG = "tag"
COL_PRIORITY = "priority"
COL_OPERATOR = "operator_id"
COL_STATE = "state"

PRIORITY_ORDER = ["critical", "high", "medium", "low"]

# EEMUA-191 target: a well-performing system averages ≤ 1 alarm per operator
# per 10 minutes in steady state (the "very likely to be acceptable" band is
# 1/10min average with a manageable-peak ceiling around 10 in 10 min).
EEMUA_TARGET_RATE_PER_10MIN = 1.0
EEMUA_MANAGEABLE_PEAK_PER_10MIN = 10.0

# An alarm is considered "standing" / "stale" if it's been continuously
# active (not cleared) longer than this threshold. EEMUA doesn't mandate a
# single number — 24h is a common operational default; tune per your process.
DEFAULT_STANDING_ALARM_THRESHOLD = timedelta(hours=24)


@dataclass
class StaleAlarmResult:
    tag: str
    operator_id: str | None
    became_active_at: pd.Timestamp
    duration: timedelta


def stale_alarms(
    df: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    threshold: timedelta = DEFAULT_STANDING_ALARM_THRESHOLD,
) -> list[StaleAlarmResult]:
    """
    Standing/stale alarms: alarms currently active whose most recent
    'active' transition happened more than `threshold` ago, with no
    subsequent 'cleared' event.

    Returns one row per tag currently in this state.
    """
    as_of = as_of or df[COL_TIMESTAMP].max()

    df = df.sort_values(COL_TIMESTAMP)
    results: list[StaleAlarmResult] = []

    for tag, group in df.groupby(COL_TAG):
        last_state_row = group.iloc[-1]
        if last_state_row[COL_STATE] != "active":
            continue  # currently cleared or acknowledged-and-cleared, not stale

        # find when it last transitioned into 'active'
        became_active = group[group[COL_STATE] == "active"][COL_TIMESTAMP].max()
        duration = as_of - became_active

        if duration >= threshold:
            results.append(
                StaleAlarmResult(
                    tag=tag,
                    operator_id=last_state_row.get(COL_OPERATOR),
                    became_active_at=became_active,
                    duration=duration,
                )
            )

    return sorted(results, key=lambda r: r.duration, reverse=True)


def alarm_rate_per_operator(
    df: pd.DataFrame,
    window: str = "10min",
) -> pd.DataFrame:
    """
    Alarm rate per operator per window (default 10 min, per EEMUA-191).

    Returns a DataFrame indexed by (window_start, operator_id) with a
    'count' column and a 'within_target' boolean flag (<=
    EEMUA_TARGET_RATE_PER_10MIN) and 'exceeds_manageable_peak' flag.

    Only counts alarm activations ('active' state rows), not acks/clears,
    since EEMUA-191 rate metrics are about alarms presented to the operator.
    """
    activations = df[df[COL_STATE] == "active"].copy()
    activations = activations.set_index(COL_TIMESTAMP)

    grouped = (
        activations
        .groupby(COL_OPERATOR)
        .resample(window)
        .size()
        .rename("count")
        .reset_index()
    )

    grouped["within_target"] = grouped["count"] <= EEMUA_TARGET_RATE_PER_10MIN
    grouped["exceeds_manageable_peak"] = grouped["count"] > EEMUA_MANAGEABLE_PEAK_PER_10MIN

    return grouped.rename(columns={COL_TIMESTAMP: "window_start"})


def priority_distribution_over_time(
    df: pd.DataFrame,
    window: str = "1h",
) -> pd.DataFrame:
    """
    Priority distribution over time: count of alarms per priority level
    per time window, plus each priority's share of the window's total.

    EEMUA-191 gives target distribution guidance (e.g. roughly
    5% critical / 15% high / 30% medium / 50% low as a commonly cited
    starting ratio) — expose the raw counts + percentages here and let
    the frontend compare against whatever target ratio you configure,
    since the "right" target is process/site-specific.
    """
    activations = df[df[COL_STATE] == "active"].copy()
    activations = activations.set_index(COL_TIMESTAMP)

    counts = (
        activations
        .groupby(COL_PRIORITY)
        .resample(window)
        .size()
        .rename("count")
        .reset_index()
    )

    totals = counts.groupby(COL_TIMESTAMP)["count"].transform("sum").astype(float)
    pct = (counts["count"] / totals.where(totals != 0) * 100).round(1)
    counts["pct_of_window"] = pct

    # ensure consistent priority ordering for charting
    counts[COL_PRIORITY] = pd.Categorical(
        counts[COL_PRIORITY], categories=PRIORITY_ORDER, ordered=True
    )
    return counts.sort_values([COL_TIMESTAMP, COL_PRIORITY]).rename(
        columns={COL_TIMESTAMP: "window_start"}
    )


def summary_kpis(df: pd.DataFrame) -> dict:
    """Single-call convenience wrapper returning the headline numbers for
    a KPI dashboard tile row."""
    rates = alarm_rate_per_operator(df)
    stale = stale_alarms(df)

    return {
        "avg_alarm_rate_per_operator_10min": round(rates["count"].mean(), 2) if not rates.empty else 0,
        "pct_windows_within_target": (
            round(100 * rates["within_target"].mean(), 1) if not rates.empty else None
        ),
        "peak_alarm_rate_10min": int(rates["count"].max()) if not rates.empty else 0,
        "stale_alarm_count": len(stale),
        "stale_alarms": [
            {"tag": r.tag, "operator_id": r.operator_id, "hours_standing": round(r.duration.total_seconds() / 3600, 1)}
            for r in stale[:20]  # cap for dashboard display
        ],
    }
