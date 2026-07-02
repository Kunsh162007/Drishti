"""Auto-drafted intelligence briefing for DRISHTI -- deterministic, grounded.

Assembles a plain-language briefing purely from analytics outputs already
computed elsewhere (stats, hotspots, emerging cells, anomalies). NO LLM, NO
new numbers, NO fabrication: every sentence traces back to a value present in
the inputs, and FIR numbers are cited wherever the source records expose them.
If an input section is empty, the briefing says so plainly rather than
inventing content.

Pure function: dicts/lists in -> JSON-serialisable dict out. Robust to missing
fields.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _fir_of(item: dict):
    if not isinstance(item, dict):
        return None
    return item.get("fir_number") or (item.get("crime") or {}).get("fir_number")


def generate_briefing(stats: dict, hotspots: list[dict], emerging: list[dict],
                      anomalies: list[dict], district: str | None) -> dict:
    """Assemble a grounded briefing from precomputed analytics outputs.

    Args:
        stats: ``/stats`` output (``kpis``, ``by_category``, ...). May be empty.
        hotspots: ``/hotspots`` cells (``[{h3, count, level, ...}]``).
        emerging: ``/emerging`` cells (``[{h3, category, recent, ...}]``).
        anomalies: ``/anomalies`` items (``[{fir_number, score, reasons, ...}]``).
        district: optional district scope label for the headline.

    Returns:
        ``{generated_at, headline, sections:[{title, text, citations:[fir]}]}``.
        Every claim is derived from the inputs; empty inputs are reported as
        such. No values are invented.
    """
    stats = stats or {}
    hotspots = hotspots or []
    emerging = emerging or []
    anomalies = anomalies or []

    scope = district or "All districts"
    generated_at = datetime.now(timezone.utc).isoformat()

    sections = []

    # --- 1. Overview (from stats KPIs / category mix) ---
    kpis = stats.get("kpis") or {}
    by_cat = stats.get("by_category") or []
    if kpis or by_cat:
        bits = []
        total = kpis.get("total") or kpis.get("crimes")
        if total is not None:
            bits.append(f"{total} crimes in scope")
        for key in ("open", "open_cases", "solved", "charge_sheeted"):
            if key in kpis and kpis[key] is not None:
                bits.append(f"{kpis[key]} {key.replace('_', ' ')}")
        if by_cat:
            top = max(by_cat, key=lambda x: x.get("value", 0))
            bits.append(f"top category: {top.get('name')} ({top.get('value')})")
        text = ("Overview for " + scope + ": " + "; ".join(bits) + "."
                if bits else f"Overview for {scope}: no summary statistics available.")
        sections.append({"title": "Overview", "text": text, "citations": []})
    else:
        sections.append({"title": "Overview", "text":
                         f"Overview for {scope}: no summary statistics were provided.",
                         "citations": []})

    # --- 2. Hotspots ---
    hot = [h for h in hotspots if h.get("level") == "hot"]
    if hot:
        top_hot = sorted(hot, key=lambda x: -(x.get("count") or 0))[:3]
        descr = ", ".join(
            f"cell {h.get('h3')} ({h.get('count')} incidents, "
            f"sig={h.get('significance')})" for h in top_hot
        )
        text = (f"{len(hot)} statistically significant hotspot cell(s) detected. "
                f"Highest-load: {descr}.")
    elif hotspots:
        text = (f"No 'hot' clusters crossed the significance threshold among "
                f"{len(hotspots)} analysed cell(s).")
    else:
        text = "No hotspot analysis was provided for this period."
    sections.append({"title": "Hotspots", "text": text, "citations": []})

    # --- 3. Emerging patterns (new / intensifying) ---
    notable = [e for e in emerging if e.get("category") in ("new", "intensifying")]
    if notable:
        order = {"new": 0, "intensifying": 1}
        notable = sorted(notable, key=lambda e: (order.get(e.get("category"), 9),
                                                 -(e.get("recent") or 0)))[:4]
        clauses = []
        for e in notable:
            cp = e.get("change_pct")
            cp_txt = f", +{cp}% vs baseline" if isinstance(cp, (int, float)) and cp > 0 else ""
            clauses.append(f"cell {e.get('h3')} {e.get('category')} "
                           f"({e.get('recent')} recent{cp_txt})")
        text = "Emerging patterns: " + "; ".join(clauses) + "."
    elif emerging:
        text = "No new or intensifying cells; activity is stable or diminishing."
    else:
        text = "No emerging hotspot analysis was provided."
    sections.append({"title": "Emerging Patterns", "text": text, "citations": []})

    # --- 4. Notable anomalies (with FIR citations) ---
    citations = []
    if anomalies:
        top_anom = sorted(anomalies, key=lambda a: -(a.get("score") or 0))[:5]
        clauses = []
        for a in top_anom:
            fir = _fir_of(a)
            if fir:
                citations.append(fir)
            reasons = a.get("reasons") or []
            rtxt = f" ({reasons[0]})" if reasons else ""
            label = fir or "unknown FIR"
            clauses.append(f"{label} score={a.get('score')}{rtxt}")
        text = f"{len(anomalies)} anomaly record(s) flagged. Most notable: " + \
               "; ".join(clauses) + "."
    else:
        text = "No anomalous records were flagged."
    sections.append({"title": "Notable Anomalies", "text": text,
                     "citations": _dedup(citations)})

    # --- headline (derived only from what we found) ---
    headline = _headline(scope, kpis, hot, notable, anomalies)

    return {
        "generated_at": generated_at,
        "headline": headline,
        "sections": sections,
    }


def _short(text, n=220):
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def fir_brief(row: dict) -> dict:
    """One grounded brief for a single FIR — a headline summary plus the
    structured detail an officer expands to read. Every field is copied from
    the source record; nothing is inferred or invented."""
    row = row or {}
    fir = row.get("fir_number") or "(unknown FIR)"
    ctype = row.get("crime_type") or "Unclassified"
    station = row.get("police_station") or "—"
    district = row.get("district") or "—"
    when = (row.get("occurred_at") or "")[:10] or "date n/a"
    status = row.get("status") or "—"

    summary = f"{ctype} · {station}, {district} · {when} · {status}"

    facts = []
    if row.get("severity") is not None:
        facts.append(f"severity {row['severity']}")
    if row.get("victim_count") is not None:
        facts.append(f"{row['victim_count']} victim(s)")
    if row.get("accused_count") is not None:
        facts.append(f"{row['accused_count']} accused")
    if row.get("property_value_inr"):
        facts.append(f"₹{row['property_value_inr']:,} property value")
    if row.get("weapon_used"):
        facts.append(f"weapon: {row['weapon_used']}")

    return {
        "fir_number": fir,
        "crime_type": ctype,
        "category": row.get("crime_category"),
        "district": district,
        "police_station": station,
        "occurred_at": when,
        "status": status,
        "summary": summary,
        "facts": facts,
        "modus_operandi": _short(row.get("modus_operandi"), 200),
        "description": _short(row.get("description"), 320),
    }


def per_fir_briefs(crimes: list[dict], limit: int = 400, total: int | None = None) -> dict:
    """Per-FIR briefs for the FIRs in scope (most recent first), capped at
    ``limit`` for payload size. ``total`` reports the full in-scope count (pass
    it when ``crimes`` is already truncated) so the UI can say 'showing N of TOTAL'."""
    crimes = crimes or []
    ordered = sorted(crimes, key=lambda r: (r.get("occurred_at") or ""), reverse=True)
    items = [fir_brief(r) for r in ordered[: max(1, limit)]]
    return {"total": total if total is not None else len(crimes),
            "shown": len(items), "items": items}


def _dedup(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _headline(scope, kpis, hot, notable, anomalies) -> str:
    total = kpis.get("total") or kpis.get("crimes")
    parts = [f"Intelligence briefing -- {scope}"]
    facts = []
    if total is not None:
        facts.append(f"{total} crimes")
    if hot:
        facts.append(f"{len(hot)} active hotspot(s)")
    if notable:
        facts.append(f"{len(notable)} emerging cell(s)")
    if anomalies:
        facts.append(f"{len(anomalies)} anomaly flag(s)")
    if facts:
        parts.append(", ".join(facts))
    return ": ".join(parts) if len(parts) > 1 else parts[0]
