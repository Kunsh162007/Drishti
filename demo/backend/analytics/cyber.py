"""Cybercrime / financial-fraud money-flow analytics for DRISHTI.

Three grounded analyses for the cyber/fraud workflow:

  * :func:`cyber_overview` -- KPI/trend roll-up over ``Cybercrime`` crimes.
  * :func:`detect_mules` -- structural (behaviour-based) mule detection over
    account + transaction graphs. Flags accounts by *how money moves through
    them* (fan-in then rapid fan-out, short hold time, pass-through ratio ~1,
    many counterparties) -- NOT by any pre-existing ``is_mule`` label, which is
    used only as an optional validation note.
  * :func:`money_flow` -- follow-the-money directed multi-hop graph from an
    account (same node/edge shape family as ``/network`` for sigma.js reuse).

Pure functions: list[dict] in -> JSON-serialisable out. Vectorised where the
data is large; robust to missing fields.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

# tolerant column candidates for transactions
_FROM_COLS = ["from_account", "src", "source", "debit_account", "sender", "from"]
_TO_COLS = ["to_account", "dst", "dest", "credit_account", "receiver", "to"]
_AMT_COLS = ["amount", "amount_inr", "value", "txn_amount", "amt"]
_TS_COLS = ["timestamp", "datetime", "txn_time", "time", "occurred_at", "ts"]
_CHAN_COLS = ["channel", "mode", "rail", "method"]


# ------------------------------------------------------------------ overview --
def cyber_overview(crimes: list[dict]) -> dict:
    """KPI/trend overview over crimes with ``crime_category == 'Cybercrime'``.

    Args:
        crimes: full list of crime dicts (filtered here to Cybercrime).

    Returns:
        ``{kpis:{total, flagged_mules?}, by_type:[{name,value}],
        trend:[{period,count}], top_districts:[{name,value}]}``. The
        ``flagged_mules`` KPI is left for the caller (money-flow) to fill;
        it is omitted here.
    """
    cyber = [c for c in (crimes or []) if (c.get("crime_category") == "Cybercrime")]
    total = len(cyber)
    if total == 0:
        return {"kpis": {"total_cases": 0, "total_loss": 0, "mule_accounts": 0, "recovery_rate": 0.0},
                "by_type": [], "trend": [], "top_districts": []}

    total_loss = int(sum(float(c.get("property_value_inr") or 0) for c in cyber))

    by_type = defaultdict(int)
    by_district = defaultdict(int)
    by_month = defaultdict(int)
    for c in cyber:
        if c.get("crime_type"):
            by_type[c["crime_type"]] += 1
        if c.get("district"):
            by_district[c["district"]] += 1
        occ = c.get("occurred_at")
        if occ:
            period = str(occ)[:7]  # YYYY-MM
            if len(period) == 7:
                by_month[period] += 1

    by_type_l = [{"name": k, "value": v}
                 for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])]
    top_districts = [{"name": k, "value": v}
                     for k, v in sorted(by_district.items(), key=lambda kv: -kv[1])][:10]
    trend = [{"period": p, "count": by_month[p]} for p in sorted(by_month)]

    return {
        "kpis": {
            "total_cases": total,
            "total_loss": total_loss,
            "mule_accounts": 0,   # augmented by the API endpoint
            "recovery_rate": 0.0,
        },
        "by_type": by_type_l,
        "trend": trend,
        "top_districts": top_districts,
    }


# ------------------------------------------------------------ txn dataframe --
def _txn_frame(transactions: list[dict]) -> pd.DataFrame:
    if not transactions:
        return pd.DataFrame(columns=["src", "dst", "amt", "ts", "chan"])
    df = pd.DataFrame(list(transactions))

    def pick(cols):
        for c in cols:
            if c in df.columns:
                return df[c]
        return pd.Series([None] * len(df))

    out = pd.DataFrame({
        "src": pick(_FROM_COLS).astype("string"),
        "dst": pick(_TO_COLS).astype("string"),
        "chan": pick(_CHAN_COLS).astype("string"),
    })
    out["amt"] = pd.to_numeric(pick(_AMT_COLS), errors="coerce").fillna(0.0)
    out["ts"] = pd.to_datetime(pick(_TS_COLS), errors="coerce", utc=False)
    return out


# ------------------------------------------------------------- mule detection --
def detect_mules(accounts: list[dict], transactions: list[dict], limit: int = 100) -> list[dict]:
    """Flag mule-like accounts by structural money-movement signals.

    Signals (all behaviour-based, label-free):
      * high fan-in followed by rapid fan-out,
      * short hold time between credits and debits,
      * pass-through ratio ~1 (out-flow ~= in-flow),
      * many distinct counterparties.

    Args:
        accounts: ``[{account_id, holder_name?, bank?, is_mule?}]``.
        transactions: ``[{from_account, to_account, amount, timestamp, ...}]``.
        limit: max accounts to return.

    Returns:
        ``[{account_id, holder_name, bank, score(0-1), reasons[],
        flagged_txns}]`` sorted by score desc. ``is_mule`` (if present) is
        used ONLY for an optional validation note, never as a feature.
    """
    df = _txn_frame(transactions)
    if df.empty:
        return []

    df = df[df["src"].notna() & df["dst"].notna()]
    if df.empty:
        return []

    acct_meta = {}
    for a in accounts or []:
        aid = a.get("account_id")
        if aid is not None:
            acct_meta[str(aid)] = a

    # Per-account aggregates (vectorised group-bys).
    inflow = df.groupby("dst").agg(
        in_amt=("amt", "sum"), in_cnt=("amt", "size"),
        in_first=("ts", "min"), in_last=("ts", "max"),
        in_partners=("src", "nunique"),
    )
    outflow = df.groupby("src").agg(
        out_amt=("amt", "sum"), out_cnt=("amt", "size"),
        out_first=("ts", "min"), out_last=("ts", "max"),
        out_partners=("dst", "nunique"),
    )

    # All accounts seen on either side, plus those in the accounts list.
    ids = set(inflow.index) | set(outflow.index) | set(acct_meta.keys())

    results = []
    for aid in ids:
        in_amt = float(inflow["in_amt"].get(aid, 0.0)) if aid in inflow.index else 0.0
        out_amt = float(outflow["out_amt"].get(aid, 0.0)) if aid in outflow.index else 0.0
        in_cnt = int(inflow["in_cnt"].get(aid, 0)) if aid in inflow.index else 0
        out_cnt = int(outflow["out_cnt"].get(aid, 0)) if aid in outflow.index else 0
        in_partners = int(inflow["in_partners"].get(aid, 0)) if aid in inflow.index else 0
        out_partners = int(outflow["out_partners"].get(aid, 0)) if aid in outflow.index else 0

        if in_amt <= 0 and out_amt <= 0:
            continue

        reasons = []
        score = 0.0

        # 1) pass-through ratio ~1 (money in roughly equals money out)
        if in_amt > 0 and out_amt > 0:
            ratio = out_amt / in_amt
            passthrough = 1.0 - min(1.0, abs(1.0 - ratio))
            if passthrough > 0.7:
                score += 0.30 * passthrough
                reasons.append(f"pass-through ratio ~{ratio:.2f} (in/out balanced)")

        # 2) fan-in then fan-out (many counterparties both sides)
        if in_partners >= 3 and out_partners >= 2:
            fan = min(1.0, (in_partners + out_partners) / 20.0)
            score += 0.25 * fan
            reasons.append(f"fan-in {in_partners} -> fan-out {out_partners} counterparties")

        # 3) short hold time (rapid debit after credit)
        in_last = inflow["in_last"].get(aid) if aid in inflow.index else None
        out_last = outflow["out_last"].get(aid) if aid in outflow.index else None
        if pd.notna(in_first := (inflow["in_first"].get(aid) if aid in inflow.index else pd.NaT)) \
                and pd.notna(out_last):
            hold_h = (pd.Timestamp(out_last) - pd.Timestamp(in_first)).total_seconds() / 3600.0
            if 0 <= hold_h <= 48:
                hold_score = 1.0 - (hold_h / 48.0)
                score += 0.25 * hold_score
                reasons.append(f"short hold time (~{hold_h:.1f}h credit->debit)")

        # 4) high churn volume relative to a normal account
        churn = in_cnt + out_cnt
        if churn >= 8:
            score += 0.20 * min(1.0, churn / 40.0)
            reasons.append(f"high transaction churn ({churn} txns)")

        score = round(float(max(0.0, min(1.0, score))), 3)
        if score <= 0 or not reasons:
            continue

        meta = acct_meta.get(aid, {})
        note = None
        if "is_mule" in meta and meta.get("is_mule") is not None:
            actual = bool(meta.get("is_mule"))
            note = ("validation: matches known mule label"
                    if actual else "validation: not labelled a mule")

        flagged = 0
        if aid in inflow.index:
            flagged += in_cnt
        if aid in outflow.index:
            flagged += out_cnt

        rec = {
            "account_id": str(aid),
            "holder_name": meta.get("holder_name"),
            "bank": meta.get("bank"),
            "score": score,
            "reasons": reasons,
            "flagged_txns": int(flagged),
        }
        if note:
            rec["validation_note"] = note
        results.append(rec)

    results.sort(key=lambda r: -r["score"])
    return results[: max(1, int(limit or 1))]


# --------------------------------------------------------------- money flow --
def money_flow(transactions: list[dict], accounts: list[dict], account_id: str,
               depth: int = 2) -> dict:
    """Follow-the-money directed graph from an account, multi-hop.

    Args:
        transactions: transaction dicts (directed src -> dst with amount).
        accounts: account dicts for node metadata (bank, is_mule).
        account_id: root account to trace from.
        depth: number of forward hops to follow (capped, ~250 nodes).

    Returns:
        ``{nodes:[{id,label,type:'account',meta:{bank,is_mule}}],
        edges:[{source,target,label:amount, weight, channel}]}`` (directed).
    """
    account_id = str(account_id) if account_id is not None else ""
    df = _txn_frame(transactions)
    if df.empty or not account_id:
        return {"nodes": [], "edges": []}
    df = df[df["src"].notna() & df["dst"].notna()]
    if df.empty:
        return {"nodes": [], "edges": []}

    acct_meta = {}
    for a in accounts or []:
        aid = a.get("account_id")
        if aid is not None:
            acct_meta[str(aid)] = a

    # Forward adjacency (directed money flow).
    fwd = defaultdict(set)
    for s, d in df[["src", "dst"]].itertuples(index=False):
        if s != d:
            fwd[s].add(d)

    depth = max(0, int(depth or 0))
    cap = 250
    selected = {account_id}
    frontier = {account_id}
    for _ in range(depth):
        nxt = set()
        for node in frontier:
            for nb in fwd.get(node, ()):  # noqa: B007
                if nb not in selected:
                    nxt.add(nb)
        if not nxt:
            break
        for nb in sorted(nxt):
            if len(selected) >= cap:
                break
            selected.add(nb)
        frontier = nxt & selected
        if len(selected) >= cap:
            break

    sub = df[df["src"].isin(selected) & df["dst"].isin(selected)]
    sub = sub[sub["src"] != sub["dst"]]
    if sub.empty:
        # Still return the root node alone.
        nodes = [_acct_node(account_id, acct_meta)]
        return {"nodes": nodes, "edges": []}

    # Aggregate amount + dominant channel per directed edge.
    agg = sub.groupby(["src", "dst"]).agg(
        amount=("amt", "sum"), n=("amt", "size"),
    )
    chan = (sub.dropna(subset=["chan"]).groupby(["src", "dst"])["chan"]
            .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None))

    nodes = [_acct_node(n, acct_meta) for n in sorted(selected)]
    edges = []
    for (s, d), row in agg.iterrows():
        amount = float(row["amount"])
        edges.append({
            "source": f"account:{s}",
            "target": f"account:{d}",
            "label": f"₹{amount:,.0f}",
            "weight": int(round(amount)),
            "channel": (str(chan.get((s, d))) if (s, d) in chan.index
                        and chan.get((s, d)) is not None else None),
        })
    return {"nodes": nodes, "edges": edges}


def _acct_node(aid: str, acct_meta: dict) -> dict:
    meta = acct_meta.get(aid, {})
    return {
        "id": f"account:{aid}",
        "label": str(meta.get("holder_name") or aid),
        "type": "account",
        "meta": {"bank": meta.get("bank"), "is_mule": meta.get("is_mule")},
    }
