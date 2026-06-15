"""Call Detail Record (CDR) analysis for DRISHTI.

Three grounded, vectorised analyses over CDR rows (each row is a single
call/SMS event). Built for scale: the demo CDR has ~120k rows, so all
aggregation goes through pandas group-bys rather than Python loops.

Expected (tolerant) CDR row schema -- any field may be missing/None::

    {a_party, b_party, tower / cell_id, timestamp / start_time,
     duration / duration_seconds, type}

  * :func:`cdr_contacts` -- top contacts, common towers, and co-location
    (two numbers at the same tower within a ~60-min window).
  * :func:`cdr_network` -- ego who-calls-whom graph (same node/edge shape as
    the main ``/network`` endpoint so the frontend can reuse sigma.js).
  * :func:`tower_dump` -- all numbers active at a tower within a window.

Pure functions: list[dict] in -> JSON-serialisable dict out.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

# Candidate column names we will normalise onto canonical names.
_A_COLS = ["a_party", "a_number", "caller", "msisdn", "from", "source", "a"]
_B_COLS = ["b_party", "b_number", "callee", "called", "to", "target", "b"]
_TOWER_COLS = ["tower", "cell_id", "tower_id", "cell", "lac_cid", "site"]
_TS_COLS = ["timestamp", "start_time", "datetime", "call_time", "ts", "time", "occurred_at"]
_DUR_COLS = ["duration", "duration_seconds", "dur", "seconds", "call_duration"]
_TYPE_COLS = ["type", "call_type", "direction"]

_WINDOW_SECONDS = 3600  # ~60 minute co-location / windowing bucket


def _frame(cdr: list[dict]) -> pd.DataFrame:
    """Normalise heterogeneous CDR rows into a canonical DataFrame."""
    if not cdr:
        return pd.DataFrame(columns=["a", "b", "tower", "ts", "dur", "type"])
    df = pd.DataFrame(list(cdr))

    def pick(cols):
        for c in cols:
            if c in df.columns:
                return df[c]
        return pd.Series([None] * len(df))

    out = pd.DataFrame({
        "a": pick(_A_COLS).astype("string"),
        "b": pick(_B_COLS).astype("string"),
        "tower": pick(_TOWER_COLS).astype("string"),
        "type": pick(_TYPE_COLS).astype("string"),
    })
    out["ts"] = pd.to_datetime(pick(_TS_COLS), errors="coerce", utc=False)
    out["dur"] = pd.to_numeric(pick(_DUR_COLS), errors="coerce").fillna(0.0)
    return out


def cdr_contacts(cdr: list[dict], msisdn: str) -> dict:
    """Contact, tower and co-location profile for a single number.

    Args:
        cdr: list of CDR event dicts.
        msisdn: the number of interest (A or B party).

    Returns:
        ``{msisdn, total_calls, top_contacts:[{number,count,total_seconds}],
        common_towers:[{tower,count}], co_location:[{number, shared_towers,
        shared_windows}]}``. Co-location pairs ``msisdn`` with other numbers
        seen at the same tower in the same ~60-min window.
    """
    msisdn = str(msisdn) if msisdn is not None else ""
    df = _frame(cdr)
    if df.empty or not msisdn:
        return {"msisdn": msisdn, "total_calls": 0, "top_contacts": [],
                "common_towers": [], "co_location": []}

    mine = df[(df["a"] == msisdn) | (df["b"] == msisdn)]
    if mine.empty:
        return {"msisdn": msisdn, "total_calls": 0, "top_contacts": [],
                "common_towers": [], "co_location": []}

    # The counterparty is whichever side is not msisdn.
    mine = mine.copy()
    mine["other"] = np.where(mine["a"] == msisdn, mine["b"], mine["a"])

    # --- top contacts ---
    valid = mine[mine["other"].notna()]
    grp = valid.groupby("other", dropna=True).agg(
        count=("other", "size"), total_seconds=("dur", "sum")
    ).sort_values(["count", "total_seconds"], ascending=False)
    top_contacts = [
        {"number": str(num), "count": int(row["count"]),
         "total_seconds": int(row["total_seconds"])}
        for num, row in grp.head(15).iterrows()
    ]

    # --- common towers ---
    tw = mine[mine["tower"].notna()].groupby("tower").size().sort_values(ascending=False)
    common_towers = [{"tower": str(t), "count": int(c)} for t, c in tw.head(15).items()]

    # --- co-location: same tower + same time bucket as another number ---
    co_location = _co_location(df, msisdn)

    return {
        "msisdn": msisdn,
        "total_calls": int(len(mine)),
        "top_contacts": top_contacts,
        "common_towers": common_towers,
        "co_location": co_location,
    }


def _co_location(df: pd.DataFrame, msisdn: str) -> list[dict]:
    """Numbers sharing a tower + ~60-min window with ``msisdn``."""
    sub = df[df["tower"].notna() & df["ts"].notna()].copy()
    if sub.empty:
        return []
    # Long form: every event contributes (number, tower, window).
    sub["win"] = (sub["ts"].astype("int64") // 10**9 // _WINDOW_SECONDS)
    a = sub[["a", "tower", "win"]].rename(columns={"a": "num"})
    b = sub[["b", "tower", "win"]].rename(columns={"b": "num"})
    long = pd.concat([a, b], ignore_index=True)
    long = long[long["num"].notna()]

    mine = long[long["num"] == msisdn][["tower", "win"]].drop_duplicates()
    if mine.empty:
        return []
    others = long[long["num"] != msisdn]
    # Inner-join on (tower, win) gives co-present (tower, window) hits.
    merged = others.merge(mine, on=["tower", "win"], how="inner")
    if merged.empty:
        return []
    agg = merged.groupby("num").agg(
        shared_towers=("tower", "nunique"),
        shared_windows=("win", "nunique"),
    ).sort_values(["shared_windows", "shared_towers"], ascending=False)
    return [
        {"number": str(num), "shared_towers": int(r["shared_towers"]),
         "shared_windows": int(r["shared_windows"])}
        for num, r in agg.head(20).iterrows()
    ]


def cdr_network(cdr: list[dict], msisdn: str, depth: int = 1) -> dict:
    """Ego who-calls-whom network around ``msisdn`` (sigma.js shape).

    Args:
        cdr: list of CDR event dicts.
        msisdn: ego number.
        depth: number of hops to expand from the ego (capped, ~300 nodes).

    Returns:
        ``{nodes:[{id,label,type:'phone',meta:{calls}}],
        edges:[{source,target,label:'calls', weight}]}`` -- same node/edge
        shape as the main ``/network`` endpoint.
    """
    msisdn = str(msisdn) if msisdn is not None else ""
    df = _frame(cdr)
    if df.empty or not msisdn:
        return {"nodes": [], "edges": []}

    pairs = df[df["a"].notna() & df["b"].notna()][["a", "b"]]
    if pairs.empty:
        return {"nodes": [], "edges": []}

    # Undirected adjacency for BFS expansion.
    adj = defaultdict(set)
    for a, b in pairs.itertuples(index=False):
        if a == b:
            continue
        adj[a].add(b)
        adj[b].add(a)

    if msisdn not in adj:
        return {"nodes": [], "edges": []}

    depth = max(0, int(depth or 0))
    cap = 300
    selected = {msisdn}
    frontier = {msisdn}
    for _ in range(depth):
        nxt = set()
        for node in frontier:
            for nb in adj.get(node, ()):  # noqa: B007
                if nb not in selected:
                    nxt.add(nb)
        if not nxt:
            break
        # Add deterministically until cap reached.
        for nb in sorted(nxt):
            if len(selected) >= cap:
                break
            selected.add(nb)
        frontier = nxt & selected
        if len(selected) >= cap:
            break

    # Edge weights (directed a->b call counts) restricted to selected nodes.
    ego = pairs[pairs["a"].isin(selected) & pairs["b"].isin(selected)]
    ego = ego[ego["a"] != ego["b"]]
    weights = ego.groupby(["a", "b"]).size()

    # Per-number call volume for node meta.
    calls_per = defaultdict(int)
    for (a, b), w in weights.items():
        calls_per[a] += int(w)
        calls_per[b] += int(w)

    nodes = [
        {"id": f"phone:{n}", "label": str(n), "type": "phone",
         "meta": {"calls": int(calls_per.get(n, 0))}}
        for n in sorted(selected)
    ]
    edges = [
        {"source": f"phone:{a}", "target": f"phone:{b}", "label": "calls",
         "weight": int(w)}
        for (a, b), w in weights.items()
    ]
    return {"nodes": nodes, "edges": edges}


def tower_dump(cdr: list[dict], tower: str, start: str | None, end: str | None) -> dict:
    """All numbers active at a tower within an optional time window.

    Args:
        cdr: list of CDR event dicts.
        tower: tower / cell id to dump.
        start: ISO start (inclusive) or None for open-ended.
        end: ISO end (inclusive) or None for open-ended.

    Returns:
        ``{tower, numbers:[{number, calls, first, last}]}`` sorted by call
        count desc.
    """
    tower = str(tower) if tower is not None else ""
    df = _frame(cdr)
    if df.empty or not tower:
        return {"tower": tower, "numbers": []}

    sub = df[df["tower"] == tower].copy()
    if start:
        ts0 = pd.to_datetime(start, errors="coerce")
        if pd.notna(ts0):
            sub = sub[sub["ts"].isna() | (sub["ts"] >= ts0)]
    if end:
        ts1 = pd.to_datetime(end, errors="coerce")
        if pd.notna(ts1):
            sub = sub[sub["ts"].isna() | (sub["ts"] <= ts1)]
    if sub.empty:
        return {"tower": tower, "numbers": []}

    # Long form: a number is "active" at the tower if it is the A or B party.
    a = sub[["a", "ts"]].rename(columns={"a": "num"})
    b = sub[["b", "ts"]].rename(columns={"b": "num"})
    long = pd.concat([a, b], ignore_index=True)
    long = long[long["num"].notna()]
    if long.empty:
        return {"tower": tower, "numbers": []}

    agg = long.groupby("num").agg(
        calls=("num", "size"), first=("ts", "min"), last=("ts", "max"),
    ).sort_values("calls", ascending=False)

    def _iso(v):
        return None if pd.isna(v) else pd.Timestamp(v).isoformat()

    numbers = [
        {"number": str(num), "calls": int(r["calls"]),
         "first": _iso(r["first"]), "last": _iso(r["last"])}
        for num, r in agg.iterrows()
    ]
    return {"tower": tower, "numbers": numbers}
