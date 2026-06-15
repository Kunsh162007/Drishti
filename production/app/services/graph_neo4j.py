"""Neo4j graph adapter for production network/link analysis.

`neo4j` is imported lazily so the app boots without the driver installed or the
DB reachable. Returns the SAME {nodes, edges} shape as the demo /network endpoint
so the identical frontend works unchanged.
"""
from __future__ import annotations

from ..config import settings

_driver = None


class GraphUnavailable(RuntimeError):
    pass


def _get_driver():
    global _driver
    if _driver is not None:
        return _driver
    try:
        import neo4j  # lazy
    except Exception as e:  # pragma: no cover
        raise GraphUnavailable(f"neo4j driver not installed: {e}")
    try:
        _driver = neo4j.GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
        _driver.verify_connectivity()
    except Exception as e:
        _driver = None
        raise GraphUnavailable(f"cannot connect to Neo4j at {settings.NEO4J_URI}: {e}")
    return _driver


def sync_crimes(crimes: list[dict], persons: list[dict], vehicles: list[dict]) -> dict:
    """Upsert crime/person/vehicle nodes and relationships into Neo4j."""
    drv = _get_driver()
    cypher_nodes = """
    UNWIND $crimes AS c MERGE (x:Crime {fir:c.fir_number})
      SET x.type=c.crime_type, x.district=c.district, x.date=c.occurred_at
    """
    cypher_persons = """
    UNWIND $persons AS p
      MERGE (id:Identity {tid:p.true_identity_id}) SET id.name=p.full_name
      MERGE (c:Crime {fir:p.fir_number})
      MERGE (id)-[:INVOLVED_IN {role:p.role}]->(c)
    """
    cypher_vehicles = """
    UNWIND $vehicles AS v
      MERGE (veh:Vehicle {reg:v.reg_number}) SET veh.vtype=v.vehicle_type
      MERGE (c:Crime {fir:v.fir_number})
      MERGE (veh)-[:LINKED_TO]->(c)
    """
    with drv.session() as s:
        s.run(cypher_nodes, crimes=crimes)
        s.run(cypher_persons, persons=persons)
        s.run(cypher_vehicles, vehicles=vehicles)
    return {"crimes": len(crimes), "persons": len(persons), "vehicles": len(vehicles)}


def network(focus_fir: str | None = None, focus_identity: str | None = None,
            depth: int = 1, limit: int = 400) -> dict:
    """Return an ego graph around a FIR or identity as {nodes, edges}."""
    drv = _get_driver()
    if focus_identity:
        seed = "MATCH (s:Identity {tid:$key})"
        key = focus_identity
    elif focus_fir:
        seed = "MATCH (s:Crime {fir:$key})"
        key = focus_fir
    else:
        seed = "MATCH (s:Crime)"
        key = None
    query = f"""
    {seed}
    CALL apoc.path.subgraphAll(s, {{maxLevel:$depth, limit:$limit}}) YIELD nodes, relationships
    RETURN nodes, relationships
    """
    nodes, edges = [], []
    try:
        with drv.session() as s:
            rec = s.run(query, key=key, depth=depth, limit=limit).single()
            if rec:
                for n in rec["nodes"]:
                    labels = list(n.labels)
                    ntype = ("crime" if "Crime" in labels else "person" if "Identity" in labels
                             else "vehicle" if "Vehicle" in labels else "node")
                    nid = n.get("fir") or n.get("tid") or n.get("reg")
                    nodes.append({"id": f"{ntype}:{nid}", "label": n.get("name") or nid,
                                  "type": ntype, "meta": dict(n)})
                for r in rec["relationships"]:
                    edges.append({"source": str(r.start_node.element_id),
                                  "target": str(r.end_node.element_id), "label": r.type})
    except Exception as e:
        raise GraphUnavailable(f"graph query failed (is APOC installed?): {e}")
    return {"nodes": nodes, "edges": edges}
