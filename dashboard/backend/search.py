"""Global search over references, labs, wiki pages, threads and notes.

A query is a handful of words, including a Chinese phrase. Words that are all labels keep the records
carrying every one of those labels. Any other query has to occur in the record: a title match ranks
above the same word found only in a summary or abstract.
"""

from __future__ import annotations

import re

from .repo import BadRequest, string_list
from .notes import projects
from urllib.parse import quote
from .sections import (_lab_item, _lab_record, _labs_index, _provenance, _registry, _text, _threads,
                       reference_kinds)

GROUP_LIMIT = 12
SCOPES = ("all", "labs", "references", "wiki", "threads", "notes")
CATALOG = ("references", "labs", "wiki", "threads", "notes")
LABELS = {"references": "References", "labs": "Labs", "wiki": "Wiki", "threads": "Threads", "notes": "Notes"}
TERM = re.compile(r"[a-z0-9][a-z0-9._+-]*|[\u3400-\u9fff]{2,}")


def score(terms: list[str], fields: list[tuple[str, int]]) -> int:
    """Every term must occur in some field; exact and prefix matches of heavier fields rank first."""
    lowered = [(text.lower(), weight) for text, weight in fields if text]
    total = 0
    for term in terms:
        best = 0
        for text, weight in lowered:
            if term in text:
                factor = 3 if text == term else 2 if text.startswith(term) else 1
                best = max(best, weight * factor)
        if not best:
            return 0
        total += best
    return total


def _top(scored: list[tuple[int, str, dict]], limit: int) -> dict:
    scored.sort(key=lambda row: (-row[0], row[1]))
    return {"total": len(scored), "items": [row[2] for row in scored[:limit]]}


def terms_of(query: str) -> list[str]:
    """Words and Chinese phrases. A phrase with no spaces stays one term, so it matches as written."""
    found = TERM.findall((query or "").lower())
    if found:
        return found[:12]
    return [term for term in (query or "").lower().split() if term][:12]


def _norm(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _public(record: dict) -> dict:
    return {"id": record["id"], "title": record["title"], "subtitle": record["subtitle"],
            "badge": record["badge"], "route": record["route"]}


def _records(app) -> list[dict]:
    """One catalog row per reference, lab, wiki page and thread, with the labels that select it."""
    records = []
    registry, _, _ = _registry(app)
    for rid in sorted(app.repo.reference_ids() | set(registry)):
        entry = registry.get(rid, {})
        prov, _ = _provenance(app, rid)
        title = _text(entry.get("title")) or _text(prov.get("title")) or rid
        status = _text(entry.get("status")) or _text(prov.get("status"))
        kinds = reference_kinds(prov, entry)
        aliases = string_list(entry.get("aliases") or prov.get("aliases"))
        fields = [(rid, 5), (title, 4), (_text(entry.get("arxiv_id")), 5), (_text(prov.get("abstract"))[:500], 1)]
        fields += [(alias, 3) for alias in aliases]
        fields += [(author, 1) for author in string_list(prov.get("authors"))]
        records.append({"group": "references", "id": rid, "title": title, "subtitle": rid, "badge": status,
                        "route": f"/references/{rid}", "tags": [status, *kinds], "fields": fields})
    index, _, _ = _labs_index(app)
    for lab_id in sorted(app.repo.lab_ids() | set(index)):
        record, _ = _lab_record(app, lab_id, index)
        item = _lab_item(record)
        records.append({
            "group": "labs", "id": lab_id, "title": item["title"], "subtitle": lab_id, "badge": item["stage"],
            "route": f"/labs/{lab_id}", "tags": [item["stage"]],
            "fields": [(lab_id, 4), (item["title"], 4), (item["summary"], 2), (item["current_focus"], 1)],
        })
    for page in app.wiki.index().pages.values():
        folder = page.id.split("/", 1)[0] if "/" in page.id else ""
        records.append({
            "group": "wiki", "id": page.id, "title": page.title, "subtitle": page.path,
            "badge": page.page_type or "", "route": f"/wiki/{page.id}",
            "tags": [page.page_type or "", page.status or "", folder],
            "fields": [(page.title, 4), (page.id, 3), (page.excerpt, 1)],
        })
    threads, _, _ = _threads(app)
    for thread in threads:
        title = _text(thread.get("title")) or thread["id"]
        status = _text(thread.get("status"))
        records.append({
            "group": "threads", "id": thread["id"], "title": title, "subtitle": thread["id"],
            "badge": status, "route": f"/threads/{thread['id']}",
            "tags": [status, _text(thread.get("category")), _text(thread.get("priority"))],
            "fields": [(thread["id"], 5), (title, 4)],
        })
    for note in projects():
        records.append({"group": "notes", "id": note["id"], "title": note["title"],
                        "subtitle": "Note project", "badge": "", "tags": [],
                        "route": "/notes/" + quote(note["id"], safe=""),
                        "fields": [(note["title"], 8), ("LaTeX PDF", 1)]})
    return records


def _groups(records: list[dict], scope: str, limit: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {key: [] for key in CATALOG}
    for record in records:
        grouped[record["group"]].append(record)
    groups = []
    for key in CATALOG:
        if scope != "all" and key != scope:
            continue
        items = grouped[key]
        if scope == "all" and not items:
            continue
        groups.append({"key": key, "label": LABELS[key], "total": len(items),
                       "items": [_public(record) for record in items[:limit]]})
    return groups


def _tag_needles(query: str) -> list[str]:
    return [_norm(part) for part in (query or "").split() if part.strip()]


def _by_tag(records: list[dict], query: str, scope: str, limit: int) -> list[dict] | None:
    """Every word is a label: keep records that carry all of them. Otherwise this is not a tag query."""
    needles = _tag_needles(query)
    if not needles:
        return None
    pool = [record for record in records if scope == "all" or record["group"] == scope]
    known = {_norm(tag) for record in pool for tag in record["tags"] if tag}
    if any(needle not in known for needle in needles):
        return None
    chosen = [record for record in pool
              if all(needle in {_norm(tag) for tag in record["tags"] if tag} for needle in needles)]
    chosen.sort(key=lambda record: (record["group"], record["title"].casefold(), record["id"]))
    return _groups(chosen, scope, limit)


def _lexical(records: list[dict], terms: list[str], scope: str, limit: int) -> list[dict]:
    grouped: dict[str, list[tuple[int, str, dict]]] = {key: [] for key in CATALOG}
    for record in records:
        if scope != "all" and record["group"] != scope:
            continue
        value = score(terms, record["fields"])
        if value:
            grouped[record["group"]].append((value, record["id"], _public(record)))
    groups = []
    for key in CATALOG:
        if scope != "all" and key != scope:
            continue
        groups.append({"key": key, "label": LABELS[key], **_top(grouped[key], limit)})
    return groups


def search(app, query: str, limit: int = GROUP_LIMIT, include_private: bool = False, refine: bool = False,
           scope: str = "all", stage: str = "lexical") -> dict:
    if scope not in SCOPES:
        raise BadRequest("unknown scope")
    records = _records(app)
    tagged = _by_tag(records, query, scope, limit) if _norm(query) else None
    if tagged is not None:
        return {"query": query, "scope": scope, "mode": "tag", "complex_query": False,
                "groups": tagged, "total": sum(group["total"] for group in tagged)}

    terms = terms_of(query)
    groups = [] if not terms else _lexical(records, terms, scope, limit)
    if scope == "all" and terms and hasattr(app, "apidocs"):
        try:
            results = app.apidocs.search(query, include_private=include_private, limit=200)
            api_items = [{"title": item["qualname"], "subtitle": item["summary"], "badge": item["kind"],
                          "route": item["route"]} for item in results if item.get("route")]
            groups.append({"key": "api", "label": "API", "total": len(api_items), "items": api_items[:limit]})
        except Exception:
            pass

    from .semantic import STAGES, finish
    if stage not in STAGES:
        raise BadRequest("unknown stage")
    if refine and stage == "lexical":
        stage = "refine"
    return finish(app, query or "", {"query": query or "", "scope": scope, "groups": groups,
                                    "total": sum(group["total"] for group in groups)},
                  limit, include_private, stage, scope)
