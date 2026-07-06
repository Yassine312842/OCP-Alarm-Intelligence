"""
Layer 3 — Analysis engine.

Everything here is grounded in ISA-18.2 / EEMUA-191 alarm management. These are
the high-value, low-complexity analytics that justify the project on day one.
All functions take the alarms DataFrame from storage and return a DataFrame.
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd


def _active(alarms: pd.DataFrame) -> pd.DataFrame:
    return alarms[alarms["state"] == "ACTIVE"].copy()


def bad_actors(alarms: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Pareto of alarm sources. Usually ~10 tags cause ~80% of the load."""
    a = _active(alarms)
    counts = (a.groupby("tag").size().sort_values(ascending=False)
              .rename("alarm_count").reset_index())
    total = counts["alarm_count"].sum()
    counts["pct"] = (100 * counts["alarm_count"] / total).round(1)
    counts["cum_pct"] = counts["pct"].cumsum().round(1)
    return counts.head(top)


def chattering(alarms: pd.DataFrame, window_s: int = 60,
               min_repeats: int = 3) -> pd.DataFrame:
    """Chattering = same alarm re-activating >= min_repeats within window_s.
    Counts how many such rapid re-activations each tag/level produces."""
    a = _active(alarms).sort_values("ts")
    rows = []
    for (tag, level), g in a.groupby(["tag", "level"]):
        ts = g["ts"].values
        chatter = 0
        for i in range(len(ts)):
            window = ts[(ts > ts[i]) & (ts <= ts[i] + pd.Timedelta(seconds=window_s).to_timedelta64())]
            if len(window) + 1 >= min_repeats:
                chatter += 1
        if chatter:
            rows.append({"tag": tag, "level": level,
                         "activations": len(g), "chattering_events": chatter})
    out = pd.DataFrame(rows)
    return out.sort_values("chattering_events", ascending=False) if len(out) else out


def alarm_floods(alarms: pd.DataFrame, window_min: int = 10,
                 threshold: int = 10) -> pd.DataFrame:
    """EEMUA-191 flood: > threshold alarms per operator per window_min.
    Returns each flood window with its alarm count and dominant priority."""
    a = _active(alarms).set_index("ts").sort_index()
    if a.empty:
        return pd.DataFrame(columns=["window_start", "alarm_count", "top_priority"])
    counts = a["tag"].resample(f"{window_min}min").count()
    floods = counts[counts > threshold]
    rows = []
    for start, n in floods.items():
        chunk = a.loc[start:start + pd.Timedelta(minutes=window_min)]
        top = chunk["priority"].mode()
        rows.append({"window_start": start, "alarm_count": int(n),
                     "top_priority": (top.iloc[0] if len(top) else "-")})
    return pd.DataFrame(rows)


def co_occurrence(alarms: pd.DataFrame, window_min: int = 15,
                  min_pairs: int = 3) -> pd.DataFrame:
    """Tag pairs whose ACTIVE alarms repeatedly fall within window_min of each
    other. A cheap correlation signal that feeds root-cause analysis."""
    a = _active(alarms).sort_values("ts").reset_index(drop=True)
    pair_counts: dict[tuple[str, str], int] = {}
    ts = a["ts"]
    for i in range(len(a)):
        j = i + 1
        while j < len(a) and (ts[j] - ts[i]) <= pd.Timedelta(minutes=window_min):
            t1, t2 = a.loc[i, "tag"], a.loc[j, "tag"]
            if t1 != t2:
                key = tuple(sorted((t1, t2)))
                pair_counts[key] = pair_counts.get(key, 0) + 1
            j += 1
    rows = [{"tag_a": k[0], "tag_b": k[1], "co_occurrences": v}
            for k, v in pair_counts.items() if v >= min_pairs]
    out = pd.DataFrame(rows)
    return out.sort_values("co_occurrences", ascending=False) if len(out) else out


def pre_incident_sequences(alarms: pd.DataFrame, top: int = 8) -> pd.DataFrame:
    """Frequent ordered alarm sequences that precede a CRITICAL alarm.

    Groups the ACTIVE alarm stream into episodes (gap-split), and for every
    episode ending in a CRITICAL alarm, records the ordered tag:level sequence.
    In real data there is no incident_id, so this uses the CRITICAL alarm as the
    'incident' anchor. Frequent sequences are candidate early-warning patterns.
    """
    a = _active(alarms).sort_values("ts").reset_index(drop=True)
    a["gap"] = a["ts"].diff().dt.total_seconds().fillna(0)
    episode = (a["gap"] > 1800).cumsum()  # split on >30 min silence
    seqs: dict[str, int] = {}
    for _, g in a.groupby(episode):
        if not (g["priority"] == "CRITICAL").any():
            continue
        steps = [f"{r.tag}:{r.level}" for r in g.itertuples()]
        # de-dupe consecutive repeats, keep order
        deduped = [s for i, s in enumerate(steps) if i == 0 or s != steps[i - 1]]
        sig = " -> ".join(deduped[-5:])  # last 5 steps up to the trip
        seqs[sig] = seqs.get(sig, 0) + 1
    rows = [{"sequence": k, "occurrences": v} for k, v in seqs.items()]
    out = pd.DataFrame(rows)
    return (out.sort_values("occurrences", ascending=False).head(top)
            if len(out) else out)
