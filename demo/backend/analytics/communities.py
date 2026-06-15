"""Community detection over the crime intelligence network for DRISHTI.

Builds a NetworkX graph from the supplied nodes/edges and runs **Louvain
community detection** (Blondel et al. 2008, modularity maximisation) via
``networkx.community.louvain_communities``, falling back to greedy modularity
if Louvain is unavailable. For each community we identify ``key_nodes`` by
centrality (betweenness, tie-broken by degree).

Pure function: nodes/edges in -> communities out. Robust to malformed input.
"""
from __future__ import annotations

import networkx as nx


def detect_communities(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Detect communities (size >= 4) and their key nodes.

    Args:
        nodes: ``[{id, label?, type?, meta?}]``.
        edges: ``[{source, target, label?}]``.

    Returns:
        ``[{id, members[node ids], size, key_nodes[top 3 by centrality]}]``
        sorted by size desc, restricted to communities of size >= 4.
    """
    G = nx.Graph()
    for n in nodes or []:
        nid = n.get("id") if isinstance(n, dict) else n
        if nid is None:
            continue
        G.add_node(nid)
    for e in edges or []:
        if not isinstance(e, dict):
            continue
        s, t = e.get("source"), e.get("target")
        if s is None or t is None or s == t:
            continue
        # Tolerate edges referencing nodes not in the node list.
        G.add_edge(s, t)

    if G.number_of_nodes() == 0:
        return []

    # ---- community detection --------------------------------------------
    try:
        communities = nx.community.louvain_communities(G, seed=42)
    except Exception:
        try:
            communities = list(nx.community.greedy_modularity_communities(G))
        except Exception:
            communities = list(nx.connected_components(G))

    out = []
    for i, comm in enumerate(communities):
        members = list(comm)
        if len(members) < 4:
            continue

        sub = G.subgraph(members)
        # Betweenness on the subgraph; tie-break / fallback by degree.
        try:
            bc = nx.betweenness_centrality(sub)
        except Exception:
            bc = {}
        deg = dict(sub.degree())
        key_nodes = sorted(
            members,
            key=lambda nd: (bc.get(nd, 0.0), deg.get(nd, 0)),
            reverse=True,
        )[:3]

        out.append({
            "id": i,
            "members": members,
            "size": len(members),
            "key_nodes": key_nodes,
        })

    out.sort(key=lambda c: -c["size"])
    # Re-id sequentially after sorting for stable presentation.
    for new_id, c in enumerate(out):
        c["id"] = new_id
    return out
