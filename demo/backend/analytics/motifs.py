"""Criminal Network Motif Detection for DRISHTI.

Detects structural patterns in criminal co-accusation networks:
  * Triangles — 3-cliques indicating organized crime rings / gangs
  * Stars      — high-degree hub nodes (coordinators / kingpins)
  * Chains     — sequential connections (recruitment / supply chains)

Uses a triangle census via compact adjacency sets (O(E * sqrt(E)) worst case,
fast enough for networks up to ~10 000 persons).

Academic basis:
  Milo R et al. (2002). Network Motifs: Simple Building Blocks of Complex
    Networks. Science 298:824-827.
  Sparrow MK (1991). The application of network analysis to criminal
    intelligence. Social Networks 13:251-274.
  Décary-Hétu D & Dupont B (2012). The social network of hackers.
    Global Crime 13:182-201.

Pure function: list[dict] in -> JSON-serialisable dict out. Standard lib only.
"""
from __future__ import annotations

from collections import defaultdict


def _build_adj(nodes: list[dict], edges: list[dict]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        s, t = e.get("source", ""), e.get("target", "")
        if s and t and s != t:
            adj[s].add(t)
            adj[t].add(s)
    for n in nodes:
        nid = n.get("id", "")
        if nid:
            adj.setdefault(nid, set())
    return adj


def detect_motifs(
    nodes: list[dict],
    edges: list[dict],
    *,
    max_triangles: int = 200,
    min_degree_star: int = 4,
) -> dict:
    """Detect triangles, stars, and chains in a criminal network graph.

    Args:
        nodes: ``[{id, label, type, meta}]`` (same shape as /network output).
        edges: ``[{source, target, label}]``.
        max_triangles: cap on returned triangle motifs (most significant first).
        min_degree_star: minimum degree to report a node as a star/hub.

    Returns:
        ``{triangles:[{members, labels, firs, score}],
           stars:[{node, label, degree, firs}],
           chains:[{path, labels, length}],
           summary, stats}``.
    """
    adj = _build_adj(nodes, edges)
    id_to_label = {n["id"]: n.get("label", n["id"]) for n in nodes}
    id_to_type = {n["id"]: n.get("type", "") for n in nodes}
    id_to_meta = {n["id"]: n.get("meta", {}) for n in nodes}

    # ---------------------------------------------------------------- triangles
    node_ids = sorted(adj.keys())
    # Give each node an integer rank; iterate only forward pairs to avoid dup
    rank = {nid: i for i, nid in enumerate(node_ids)}

    triangles: list[dict] = []
    for u in node_ids:
        for v in sorted(adj[u]):
            if rank[v] <= rank[u]:
                continue
            common = adj[u] & adj[v]
            for w in sorted(common):
                if rank[w] <= rank[v]:
                    continue
                # u-v-w triangle found
                members = [u, v, w]
                labels = [id_to_label.get(m, m) for m in members]
                # Significance: higher degree members = more embedded crime ring
                deg_score = (len(adj[u]) + len(adj[v]) + len(adj[w])) / 3.0
                firs = list({
                    id_to_meta.get(m, {}).get("fir") or m.replace("crime:", "")
                    for m in members if id_to_type.get(m) in ("crime", "person")
                })
                triangles.append({
                    "members": members,
                    "labels": labels,
                    "types": [id_to_type.get(m, "") for m in members],
                    "firs": firs[:6],
                    "score": round(deg_score, 2),
                })
                if len(triangles) >= max_triangles * 5:
                    break

    triangles.sort(key=lambda t: -t["score"])
    triangles = triangles[:max_triangles]

    # ---------------------------------------------------------------- stars (hubs)
    stars: list[dict] = []
    for nid, nbrs in adj.items():
        deg = len(nbrs)
        if deg >= min_degree_star:
            meta = id_to_meta.get(nid, {})
            firs = list({
                id_to_meta.get(nb, {}).get("fir") or nb.replace("crime:", "")
                for nb in nbrs if id_to_type.get(nb) in ("crime", "person")
            })[:8]
            stars.append({
                "node": nid,
                "label": id_to_label.get(nid, nid),
                "type": id_to_type.get(nid, ""),
                "degree": deg,
                "firs": firs,
                "meta": {k: v for k, v in (meta or {}).items() if k in ("role", "district", "type")},
            })
    stars.sort(key=lambda s: -s["degree"])
    stars = stars[:60]

    # ---------------------------------------------------------------- chains (simple paths len 4)
    chains: list[dict] = []
    person_nodes = [nid for nid in node_ids if id_to_type.get(nid) == "person"]
    for start in person_nodes[:80]:
        for n1 in list(adj[start])[:6]:
            if id_to_type.get(n1) != "person":
                continue
            for n2 in list(adj[n1])[:6]:
                if n2 == start or id_to_type.get(n2) != "person":
                    continue
                for n3 in list(adj[n2])[:6]:
                    if n3 in (start, n1) or id_to_type.get(n3) != "person":
                        continue
                    path = [start, n1, n2, n3]
                    labels = [id_to_label.get(p, p) for p in path]
                    chains.append({"path": path, "labels": labels, "length": 4})
                    if len(chains) >= 80:
                        break
                if len(chains) >= 80:
                    break
            if len(chains) >= 80:
                break
        if len(chains) >= 80:
            break

    # Deduplicate chains by frozen path set
    seen_chains: set[frozenset] = set()
    unique_chains: list[dict] = []
    for c in chains:
        k = frozenset(c["path"])
        if k not in seen_chains:
            seen_chains.add(k)
            unique_chains.append(c)
    chains = unique_chains[:40]

    return {
        "triangles": triangles,
        "stars": stars,
        "chains": chains,
        "stats": {
            "nodes": len(node_ids),
            "edges": sum(len(v) for v in adj.values()) // 2,
            "triangle_count": len(triangles),
            "hub_count": len(stars),
            "chain_count": len(chains),
        },
        "summary": (
            f"Found {len(triangles)} triangle motif(s) (potential crime rings), "
            f"{len(stars)} hub node(s) (coordinators/kingpins), and "
            f"{len(chains)} chain(s) (sequential associations) "
            f"in a network of {len(node_ids)} nodes."
        ),
    }
