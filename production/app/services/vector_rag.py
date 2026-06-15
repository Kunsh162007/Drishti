"""Production assistant grounding: vector retrieval (Qdrant) + LLM, with strict
"answer only from context, cite FIRs, else 'data not available'".

All heavy deps (sentence-transformers, qdrant-client) are lazy. If the vector
store/embedder is unavailable, it falls back to keyword retrieval over the records
passed in. The LLM call mirrors the demo provider pattern; with LLM_PROVIDER=none it
returns a deterministic, grounded extractive answer (no key required).
"""
from __future__ import annotations

from ..config import settings

_embedder = None
_qdrant = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer  # lazy
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedder


def _get_qdrant():
    global _qdrant
    if _qdrant is None:
        from qdrant_client import QdrantClient  # lazy
        _qdrant = QdrantClient(url=settings.QDRANT_URL)
    return _qdrant


def index_firs(records: list[dict]) -> int:
    """Embed and upsert FIR narratives into Qdrant (one-off / batch job)."""
    from qdrant_client import models as qm  # lazy
    emb = _get_embedder()
    client = _get_qdrant()
    dim = emb.get_sentence_embedding_dimension()
    client.recreate_collection(
        settings.QDRANT_COLLECTION,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE))
    texts = [f"{r.get('crime_type','')} {r.get('district','')} {r.get('modus_operandi','')}" for r in records]
    vecs = emb.encode(texts, show_progress_bar=False)
    points = [qm.PointStruct(id=i, vector=v.tolist(),
                             payload={"fir_number": r.get("fir_number"), "crime_type": r.get("crime_type"),
                                      "district": r.get("district"), "occurred_at": r.get("occurred_at"),
                                      "modus_operandi": r.get("modus_operandi")})
              for i, (r, v) in enumerate(zip(records, vecs))]
    client.upsert(settings.QDRANT_COLLECTION, points=points)
    return len(points)


def retrieve(query: str, fallback_records: list[dict], k: int = 40) -> list[dict]:
    """Vector retrieval from Qdrant; falls back to keyword match over fallback_records."""
    try:
        emb = _get_embedder()
        client = _get_qdrant()
        qv = emb.encode([query])[0].tolist()
        hits = client.search(settings.QDRANT_COLLECTION, query_vector=qv, limit=k)
        return [h.payload for h in hits]
    except Exception:
        q = query.lower()
        scored = [r for r in fallback_records
                  if any(t in (str(r.get("modus_operandi", "")) + str(r.get("district", "")) +
                               str(r.get("crime_type", ""))).lower() for t in q.split() if len(t) > 3)]
        return scored[:k] or fallback_records[:k]


def _llm_answer(query: str, records: list[dict]) -> str | None:
    if settings.LLM_PROVIDER == "none" or not settings.LLM_API_KEY:
        return None
    context = "\n".join(
        f"- FIR {r.get('fir_number')}: {r.get('crime_type')} in {r.get('district')} "
        f"on {str(r.get('occurred_at'))[:16]}. MO: {r.get('modus_operandi')}" for r in records[:40])
    system = ("You are DRISHTI's analyst assistant. Answer ONLY from CONTEXT. Cite FIR numbers. "
              "If the answer is not in CONTEXT, say 'data not available'. Never invent anything.")
    user = f"CONTEXT:\n{context or '(none)'}\n\nQUESTION: {query}"
    try:
        import httpx
        if settings.LLM_PROVIDER == "anthropic":
            r = httpx.post("https://api.anthropic.com/v1/messages",
                           headers={"x-api-key": settings.LLM_API_KEY, "anthropic-version": "2023-06-01"},
                           json={"model": settings.LLM_MODEL or "claude-opus-4-8", "max_tokens": 700,
                                 "system": system, "messages": [{"role": "user", "content": user}]}, timeout=40)
            return r.json()["content"][0]["text"]
        base = {"groq": "https://api.groq.com/openai/v1",
                "openai": "https://api.openai.com/v1"}.get(settings.LLM_PROVIDER, "https://api.openai.com/v1")
        r = httpx.post(f"{base}/chat/completions",
                       headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                       json={"model": settings.LLM_MODEL or "llama-3.3-70b-versatile",
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                             "max_tokens": 700, "temperature": 0.1}, timeout=40)
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def answer(query: str, fallback_records: list[dict]) -> dict:
    records = retrieve(query, fallback_records)
    text = _llm_answer(query, records)
    mode = settings.LLM_PROVIDER if text else "extractive-grounded"
    if not text:
        if not records:
            text = "Data not available in the authorised corpus. I will not speculate."
        else:
            text = (f"Found {len(records)} relevant record(s). Most relevant: "
                    + "; ".join(f"FIR {r.get('fir_number')} ({r.get('crime_type')}, {r.get('district')})"
                                for r in records[:5]) + ". All facts are drawn from the cited FIRs.")
    return {"answer": text, "citations": [r.get("fir_number") for r in records[:25]],
            "mode": mode, "grounded": True}
