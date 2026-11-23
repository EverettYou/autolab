"""Lexical search plus optional embedding rank and a bounded language-model refine.

The dashboard stays usable with no network and no API key. A key in ``frontend/site.json``
is used when that field is filled in. While it is empty, ``OPENAI_CATALOG_SEARCH_ENABLED`` and
``OPENAI_API_KEY`` from the environment are the default. A failure at any step returns the
lexical groups unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .sections import _lab_item, _lab_record, _labs_index, _provenance, _registry, _text, _threads
from .site import search_runtime

PROMPT_VERSION = "lab-unified-search-refine-v1"
GROUP_KEYS = ("references", "labs", "wiki", "threads", "notes")
STAGES = ("lexical", "hybrid", "refine")
_LOCK = threading.Lock()
_BUILD: dict[str, threading.Event] = {}
_MEMORY: dict | None = None
_SCHEDULED = False


def embedding_dimensions() -> int:
    raw = os.environ.get("OPENAI_SEARCH_EMBEDDING_DIMENSIONS", "512")
    try:
        value = int(raw)
    except ValueError:
        value = 512
    return min(max(value, 64), 3072)


def is_complex_query(query: str) -> bool:
    """A question long enough, and relational enough, to be worth a second ranking pass."""
    text = " ".join(query.split())
    contains_cjk = bool(re.search(r"[\u3400-\u9fff]", text))
    long_enough = len(text.split()) >= 6 or (contains_cjk and len(text) >= 18)
    if not long_enough:
        return False
    lowered = text.casefold()
    markers = (
        "which", "what", "where", "when", "why", "how", "compare", "versus", "vs", "without",
        "except", "only", "must", "should", "evidence", "result", "适合", "不要",
        "排除", "只要", "必须", "验证", "比较", "证据", "结果", "但是", "而且",
    )
    return any(marker in lowered for marker in markers)


def lexical_score(query: str, *fields: str) -> float:
    terms = [term for term in query.casefold().split() if term]
    if not terms:
        return 0.0
    haystack = " ".join(field for field in fields if field).casefold()
    if not haystack:
        return 0.0
    hits = sum(1 for term in terms if term in haystack)
    score = 12.0 * hits / len(terms)
    if query.casefold() in haystack:
        score += 8.0
    return score


def hybrid_score(semantic: float, lexical: float) -> float:
    """Blend cosine similarity with a keyword score. Conceptual matches can outrank a weak keyword."""
    semantic = max(0.0, min(1.0, semantic))
    lexical = max(0.0, lexical)
    return round(70.0 * semantic + min(30.0, lexical), 4)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _documents(app, include_private: bool) -> list[dict]:
    del include_private  # catalog documents follow the same public set as keyword search
    documents = []
    registry, _, _ = _registry(app)
    for rid in sorted(app.repo.reference_ids() | set(registry)):
        entry = registry.get(rid, {})
        provenance, _ = _provenance(app, rid)
        title = _text(entry.get("title")) or _text(provenance.get("title")) or rid
        abstract = _text(provenance.get("abstract"))[:800]
        documents.append({
            "group": "references", "id": rid, "title": title, "subtitle": rid,
            "badge": _text(entry.get("status")) or _text(provenance.get("status")),
            "route": f"/references/{rid}",
            "text": " ".join(part for part in (title, rid, abstract) if part),
        })
    index, _, _ = _labs_index(app)
    for lab_id in sorted(app.repo.lab_ids() | set(index)):
        record, _ = _lab_record(app, lab_id, index)
        item = _lab_item(record)
        documents.append({
            "group": "labs", "id": lab_id, "title": item["title"], "subtitle": lab_id,
            "badge": item["stage"], "route": f"/labs/{lab_id}",
            "text": " ".join(part for part in (
                item["title"], lab_id, item["summary"], item["current_focus"]) if part),
        })
    for page in app.wiki.index().pages.values():
        documents.append({
            "group": "wiki", "id": page.id, "title": page.title, "subtitle": page.path,
            "badge": page.page_type or "", "route": f"/wiki/{page.id}",
            "text": " ".join(part for part in (page.title, page.id, page.excerpt) if part),
        })
    threads, _, _ = _threads(app)
    for thread in threads:
        title = _text(thread.get("title")) or thread["id"]
        messages = thread.get("messages") if isinstance(thread.get("messages"), list) else []
        excerpt = _text(messages[0].get("content"))[:400] if messages and isinstance(messages[0], dict) else ""
        documents.append({
            "group": "threads", "id": thread["id"], "title": title, "subtitle": thread["id"],
            "badge": _text(thread.get("status")), "route": f"/threads/{thread['id']}",
            "text": " ".join(part for part in (title, excerpt) if part),
        })
    try:
        from .notes import projects
        for row in projects():
            title = row["title"]
            note_id = row["id"]
            documents.append({
                "group": "notes", "id": note_id, "title": title, "subtitle": note_id,
                "badge": "editable" if row.get("source") else "pdf",
                "route": f"/notes/{note_id}",
                "text": " ".join(part for part in (title, note_id, row.get("source") or "") if part),
            })
    except Exception:
        pass
    return documents


def cache_dir() -> Path:
    """Page index for the search engine. Gitignored; the server rebuilds it."""
    return Path(__file__).resolve().parents[1] / "data"


def _cache_path(_app) -> Path:
    return cache_dir() / "search-index.json"


def _fingerprint(documents: list[dict], model: str, dimensions: int) -> str:
    payload = json.dumps(
        {"model": model, "dimensions": dimensions, "documents": [
            {"id": item["id"], "group": item["group"], "text": item["text"][:4000]} for item in documents]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def schedule_index(app) -> None:
    """Build or reload the page index off the request path. A later search reuses it."""
    global _SCHEDULED
    with _LOCK:
        if _SCHEDULED:
            return
        runtime = search_runtime(app)
        if not runtime.enabled:
            return
        _SCHEDULED = True

    def run() -> None:
        try:
            _vectors(app, _documents(app, False), search_runtime(app))
        except Exception:
            return

    threading.Thread(target=run, name="dashboard-search-index", daemon=True).start()


def _embed_texts(texts: list[str], *, key: str, model: str) -> list[list[float]]:
    dimensions = embedding_dimensions()
    vectors: list[list[float] | None] = [None] * len(texts)
    for start in range(0, len(texts), 64):
        batch = texts[start:start + 64]
        body = json.dumps({"model": model, "input": batch, "dimensions": dimensions}).encode()
        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings", data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"embedding request failed ({exc.code})") from RuntimeError(detail)
        for row in payload.get("data", []):
            vectors[start + int(row["index"])] = _normalize([float(value) for value in row["embedding"]])
    if any(vector is None for vector in vectors):
        raise RuntimeError("embedding response did not cover every document")
    return vectors  # type: ignore[return-value]


def _remember(fingerprint: str, vectors: list[list[float]]) -> list[list[float]]:
    global _MEMORY
    _MEMORY = {"fingerprint": fingerprint, "vectors": vectors}
    return vectors


def _stored_vectors(path: Path, fingerprint: str, dimensions: int) -> list[list[float]] | None:
    global _MEMORY
    if _MEMORY and _MEMORY.get("fingerprint") == fingerprint and len(_MEMORY.get("vectors", [])) > 0:
        return _MEMORY["vectors"]
    if not path.is_file():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    vectors = cached.get("vectors")
    if (cached.get("fingerprint") == fingerprint and cached.get("dimensions") == dimensions
            and isinstance(vectors, list) and vectors):
        return _remember(fingerprint, vectors)
    return None


def _write_vectors(path: Path, fingerprint: str, dimensions: int, model: str, vectors: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({
        "fingerprint": fingerprint, "model": model, "dimensions": dimensions, "vectors": vectors,
    }), encoding="utf-8")
    temporary.replace(path)
    _remember(fingerprint, vectors)


def _vectors(app, documents: list[dict], runtime) -> list[list[float]]:
    """Vectors for every catalog page. One builder runs at a time; everyone else waits for it."""
    if not documents:
        return []
    path = _cache_path(app)
    dimensions = embedding_dimensions()
    model = runtime.embedding_model
    fingerprint = _fingerprint(documents, model, dimensions)
    stored = _stored_vectors(path, fingerprint, dimensions)
    if stored is not None and len(stored) == len(documents):
        return stored
    with _LOCK:
        stored = _stored_vectors(path, fingerprint, dimensions)
        if stored is not None and len(stored) == len(documents):
            return stored
        building = _BUILD.get(fingerprint)
        if building is None:
            building = threading.Event()
            _BUILD[fingerprint] = building
            owner = True
        else:
            owner = False
    if not owner:
        building.wait(timeout=120)
        stored = _stored_vectors(path, fingerprint, dimensions)
        if stored is not None and len(stored) == len(documents):
            return stored
        raise RuntimeError("search index was not ready")
    try:
        vectors = _embed_texts(
            [item["text"][:4000] or item["title"] for item in documents], key=runtime.key, model=model)
        if len(vectors) != len(documents):
            raise RuntimeError("search index did not cover every page")
        with _LOCK:
            _write_vectors(path, fingerprint, dimensions, model, vectors)
        return vectors
    finally:
        with _LOCK:
            _BUILD.pop(fingerprint, None)
        building.set()


def _match_type(semantic: float, lexical: float) -> str:
    if lexical >= 12 and semantic >= 0.45:
        return "exact"
    if lexical >= 4:
        return "direct"
    return "conceptual"


def _ranked(app, query: str, include_private: bool, limit: int, runtime) -> dict[str, list[dict]]:
    documents = _documents(app, include_private)
    if not documents:
        return {key: [] for key in GROUP_KEYS}
    query_vector = _embed_texts([query], key=runtime.key, model=runtime.embedding_model)[0]
    vectors = _vectors(app, documents, runtime)
    grouped: dict[str, list[tuple[float, dict]]] = {key: [] for key in GROUP_KEYS}
    for document, vector in zip(documents, vectors):
        semantic = _dot(query_vector, vector)
        lexical = lexical_score(query, document["title"], document["subtitle"], document["text"])
        if semantic < 0.18 and lexical < 4:
            continue
        score = hybrid_score(semantic, lexical)
        item = {
            "id": document["id"], "title": document["title"], "subtitle": document["subtitle"],
            "badge": document["badge"], "route": document["route"], "reason": "",
            "match_type": _match_type(semantic, lexical), "score": score,
        }
        grouped[document["group"]].append((score, item))
    out = {}
    for key, rows in grouped.items():
        rows.sort(key=lambda row: (-row[0], row[1]["title"].casefold()))
        out[key] = [item for _score, item in rows[:limit]]
    return out


def _groups_from(ranked: dict[str, list[dict]], lexical_groups: list[dict], limit: int, scope: str = "all") -> list[dict]:
    labels = {group["key"]: group["label"] for group in lexical_groups}
    keys = GROUP_KEYS if scope == "all" else (scope,)
    groups = []
    for key in keys:
        items = ranked.get(key, [])[:limit]
        groups.append({"key": key, "label": labels.get(key, key), "total": len(items), "items": items})
    if scope == "all":
        api = next((group for group in lexical_groups if group["key"] == "api"), None)
        if api is not None:
            groups.append(api)
    return groups


class _ModelReply:
    def __init__(self, payload: dict):
        texts = []
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    texts.append(part.get("text") or "")
        self.output_text = "".join(texts)
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        self.usage = type("Usage", (), {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        })()
        self._request_id = None


class _Responses:
    def __init__(self, api_key: str, timeout: float, max_retries: int):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def create(self, **body):
        data = json.dumps(body).encode()
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses", data=data, method="POST",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return _ModelReply(json.loads(response.read().decode()))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                last = RuntimeError(f"refine request failed ({exc.code})")
                if exc.code != 429 and exc.code < 500:
                    raise last from RuntimeError(detail)
            except urllib.error.URLError as exc:
                last = RuntimeError("refine request failed")
            if attempt < self.max_retries:
                continue
        raise last or RuntimeError("refine request failed")


class _OpenAIClient:
    """The responses call the refine step needs. The dashboard does not import the openai package."""

    def __init__(self, *, api_key: str, timeout: float, max_retries: int):
        self.responses = _Responses(api_key, timeout, max_retries)


def _refine(app, query: str, groups: list[dict], runtime) -> list[dict]:
    """Ask the model to keep, drop, or rephrase reasons. The candidate list is the only evidence."""
    import importlib.util
    candidates = []
    for group in groups:
        if group["key"] == "api":
            continue
        for item in group["items"][:8]:
            candidates.append({"search_id": f"{group['key']}:{item['route']}", "title": item["title"],
                               "group": group["key"], "match_type": item.get("match_type", ""),
                               "route": item["route"]})
    if not candidates:
        return groups
    path = app.root / "skills" / "wiki-lint" / "scripts" / "llm.py"
    spec = importlib.util.spec_from_file_location("qmllab_wiki_lint_llm", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("language-model helper is missing")
    import sys
    module = importlib.util.module_from_spec(spec)
    # dataclasses looks the class's module up in sys.modules while the file is executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    settings = module.LLMSettings(api_key=runtime.key, model=runtime.search_model, timeout_seconds=60)
    cache = cache_dir() / "search-refine.json"
    client = module.StructuredLLM(settings, cache_path=cache, client_factory=_OpenAIClient)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["results"],
        "properties": {"results": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["search_id", "relevance", "reason"],
            "properties": {
                "search_id": {"type": "string"},
                "relevance": {"type": "number"},
                "reason": {"type": "string"},
            },
        }}},
    }
    instructions = (
        "Rank these catalog matches for the researcher's question. Use only the candidate titles. "
        "Drop a candidate that does not answer the question. relevance is 0 to 1. "
        "reason is one sentence a researcher can read."
    )
    result = client.run(
        task="search-refine", prompt_version=PROMPT_VERSION, instructions=instructions,
        input_text=json.dumps({"query": query, "candidates": candidates}, ensure_ascii=False),
        schema=schema, schema_name="search_refine", max_output_tokens=1200)
    payload = result.data
    by_id = {f"{group['key']}:{item['route']}": item for group in groups for item in group["items"]}
    chosen: dict[str, list[tuple[float, dict]]] = {key: [] for key in GROUP_KEYS}
    for row in payload.get("results", []):
        item = by_id.get(row.get("search_id", ""))
        if item is None:
            continue
        group = row["search_id"].split(":", 1)[0]
        updated = dict(item)
        updated["reason"] = str(row.get("reason", "")).strip()
        try:
            relevance = float(row.get("relevance", 0))
        except (TypeError, ValueError):
            relevance = 0.0
        chosen[group].append((relevance, updated))
    if not any(chosen.values()):
        return groups
    refined = []
    for group in groups:
        if group["key"] == "api":
            refined.append(group)
            continue
        rows = chosen[group["key"]]
        rows.sort(key=lambda row: -row[0])
        items = [item for _score, item in rows]
        refined.append({**group, "total": len(items), "items": items})
    return refined


def finish(app, query: str, payload: dict, limit: int, include_private: bool, stage: str = "lexical",
           scope: str = "all") -> dict:
    """Word matches return immediately. Hybrid and refine are separate, later requests."""
    if stage not in STAGES:
        raise ValueError(stage)
    runtime = search_runtime(app)
    complex_query = is_complex_query(query)
    enabled = bool(query.strip() and runtime.enabled)
    pending: list[str] = []
    if enabled and stage == "lexical":
        pending.append("hybrid")
        if complex_query:
            pending.append("refine")
    result = {**payload, "mode": "local", "complex_query": complex_query,
              "semantic_enabled": enabled, "pending": pending}
    if stage == "lexical" or not enabled:
        return result
    try:
        ranked = _ranked(app, query, include_private, limit, runtime)
        result = {**result, "mode": "hybrid", "pending": ["refine"] if stage == "hybrid" and complex_query else [],
                  "groups": _groups_from(ranked, payload["groups"], limit, scope)}
        result["total"] = sum(group["total"] for group in result["groups"])
    except Exception:
        return {**payload, "mode": "local", "complex_query": complex_query,
                "semantic_enabled": enabled, "pending": []}
    if stage == "refine" and complex_query:
        try:
            result = {**result, "mode": "llm-refined", "pending": [],
                      "groups": _refine(app, query, result["groups"], runtime)}
            result["total"] = sum(group["total"] for group in result["groups"])
        except Exception:
            return result
    return result
