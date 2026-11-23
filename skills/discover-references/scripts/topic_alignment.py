#!/usr/bin/env python3
"""Score how closely a candidate sits on the topic of the references already collected.

The topic is the overlap of two collections: titles and abstracts in ``references/references.json``,
and the compiled wiki under ``wiki/`` (not ``wiki/records/``, which is the session log). The word
score is the fraction of the candidate's own terms that several of those documents already share.
When dashboard search has an embedding key, a second score is the cosine between the candidate
and the centroid of the same documents, using the search embedding model. Alignment blends them
the way search does: seventy percent embedding, thirty percent words. With no key, or when the
embedding call fails, alignment is the word score.

    .venv/bin/python skills/discover-references/scripts/topic_alignment.py topic
    .venv/bin/python skills/discover-references/scripts/topic_alignment.py score --title "..." --abstract "..."
    .venv/bin/python skills/discover-references/scripts/topic_alignment.py score --topic "..." --title "..." --abstract "..."

``eval`` checks the current settings on this collection. It is not part of a discovery run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Tuned on this repository's 78 references plus 205 compiled wiki pages (2026-09-30).
# Unigrams only. A term counts when it occurs in at least five documents.
# Leave-one-out against the other references and the wiki: words median 0.77 (off-topic <= 0.40),
# embedding median 0.68 (off-topic <= 0.31), blend median 0.71 (off-topic <= 0.34).
# Calibration notes are historical; retune thresholds for EM topics as the corpus grows.
# fpga-neutral-atom-control (0.52), and latentseek (0.55).
N_MAX = 1
MIN_DF = 5
MAX_DF_FRAC = 1.0
WEIGHT = "df"
TOP_TERMS = 20
# Same split as dashboard.backend.semantic.hybrid_score: embeddings carry most of the blend.
EMBED_WEIGHT = 0.70
EMBEDDING_MODEL_DEFAULT = "text-embedding-3-small"
TEXT_LIMIT = 4000
# Tests replace this with a function (texts, *, key, model, dimensions) -> vectors.
EMBED_FETCH = None

TOKEN = re.compile(r"[a-z0-9]+")
STOP = frozenset("""
a an the of to and or for in on with from by as at is are was were be been being
this that these those it its we our their they them he she you your not no nor
into over under than then so if but about between among across per via using use used
based paper papers propose proposed method methods result results show shown showing
approach approaches novel present presented study studies work works new toward towards
improved efficient scalable can may also such which who what when where how these
however therefore thus hence within without onto onto one two three both each other
more most less least very just only also both same different various several many
any all some both into onto upon within during before after above below again further
here there out up down off do does did done have has had having will would should could
high rate time while introduce introduced achieves achieve achieved significantly
demonstrate demonstrated provide provides including compared comparison experimental
numerical simulation simulations recent existing performance various multiple enable
enables allow allows require required obtain obtained however therefore thus within
without across where which when also such than then well large small first second
order number numbers problem problems general case cases important main key full
real practical give given make makes made consider considered low
""".split())


@dataclass(frozen=True)
class Reference:
    id: str
    title: str
    abstract: str
    fetched_at: str
    kind: str = "reference"


@dataclass(frozen=True)
class EmbedConfig:
    """Search embedding settings. ``key`` is never printed."""

    enabled: bool
    key: str
    model: str
    dimensions: int
    reason: str


@dataclass(frozen=True)
class Topic:
    weights: dict[str, float]
    known: frozenset[str]
    documents: int

    @property
    def ready(self) -> bool:
        return self.documents >= 2 and bool(self.weights)


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "references" / "references.json").is_file():
            return candidate
    raise ValueError(f"no references/references.json above {here}")


def words_of(text: str) -> list[str]:
    out = []
    for word in TOKEN.findall(text.lower()):
        if word in STOP or word.isdigit() or len(word) < 3:
            continue
        out.append(word)
    return out


def terms_of(text: str, n_max: int | None = None) -> set[str]:
    n_max = N_MAX if n_max is None else n_max
    words = words_of(text)
    found = set(words)
    for n in range(2, n_max + 1):
        for index in range(len(words) - n + 1):
            found.add(" ".join(words[index : index + n]))
    return found


def load_references(root: Path) -> list[Reference]:
    catalog = json.loads((root / "references" / "references.json").read_text(encoding="utf-8"))
    rows = catalog.get("references") if isinstance(catalog, dict) else None
    if not isinstance(rows, list):
        raise ValueError("references/references.json has no references list")
    docs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = row.get("provenance")
        if not isinstance(rel, str) or not rel.endswith("provenance.json"):
            continue
        path = root / rel
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        title = str(data.get("title") or row.get("title") or "").strip()
        if not title:
            continue
        abstract = str(data.get("abstract") or "").strip()
        fetched = str(data.get("fetched_at") or "")
        docs.append(Reference(str(row.get("id") or path.parent.name), title, abstract, fetched))
    docs.sort(key=lambda doc: (doc.fetched_at or "9999", doc.id))
    return docs


_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_WIKILINK = re.compile(r"\[\[([^\[\]\n|#]+)(?:#[^\[\]\n|]*)?(?:\|([^\[\]\n]*))?\]\]")
# The schema exempts these from the compiled-page contract: the catalog, the operation log,
# this schema, and folder guides.
_SKIP_WIKI_ROOT = {"README.md", "index.md"}


def _wiki_label(match: re.Match[str]) -> str:
    label = (match.group(2) or "").strip()
    if label:
        return label
    return match.group(1).strip().rsplit("/", 1)[-1].replace("-", " ")


def _wiki_body(body: str) -> str:
    """Drop the compiled-page labels. The summary sentence stays; the label does not."""
    lines = []
    related = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## related pages"):
            related = True
            continue
        if related:
            if stripped.startswith("## "):
                related = False
            else:
                continue
        if stripped.lower().startswith("**last updated**"):
            continue
        stripped = re.sub(r"^\*\*summary\*\*:\s*", "", stripped, count=1, flags=re.I)
        stripped = re.sub(r"^\*\*sources\*\*:\s*", "", stripped, count=1, flags=re.I)
        lines.append(stripped)
    return "\n".join(lines)


def _wiki_title(header: str, body: str, path: Path) -> str:
    for line in header.splitlines():
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ")


def load_wiki(root: Path) -> list[Reference]:
    """Compiled wiki pages. ``wiki/records/`` is the session log and stays out of the topic."""
    wiki = root / "wiki"
    if not wiki.is_dir():
        return []
    pages = []
    for path in sorted(wiki.rglob("*.md")):
        relative = path.relative_to(wiki)
        if relative.parts[0] == "records" or path.name == "README.md":
            continue
        if len(relative.parts) == 1 and path.name in _SKIP_WIKI_ROOT:
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        header, body = "", raw
        match = _FRONT_MATTER.match(raw)
        if match:
            header, body = match.group(1), raw[match.end():]
        title = _wiki_title(header, body, path)
        text = _WIKILINK.sub(_wiki_label, _wiki_body(body)).strip()[:TEXT_LIMIT]
        page_id = "wiki/" + relative.with_suffix("").as_posix()
        pages.append(Reference(page_id, title, text, "", "wiki"))
    return pages


def fit(docs: list[Reference], *, n_max: int | None = None, min_df: int | None = None,
        max_df_frac: float | None = None, weight: str | None = None) -> Topic:
    n_max = N_MAX if n_max is None else n_max
    min_df = MIN_DF if min_df is None else min_df
    max_df_frac = MAX_DF_FRAC if max_df_frac is None else max_df_frac
    weight = WEIGHT if weight is None else weight
    """Term weights for the overlap of ``docs``. A term in nearly every document is dropped."""
    sets = [terms_of(f"{doc.title}\n{doc.abstract}", n_max) for doc in docs]
    documents = len(sets)
    counts: Counter[str] = Counter()
    for terms in sets:
        counts.update(terms)
    if documents < 2:
        return Topic({}, frozenset(counts), documents)
    # Five documents have to share a term once the collection is that large. A smaller
    # collection can only overlap on terms that every document contains.
    min_df = min(min_df, documents)
    ceiling = max(min_df, math.floor(max_df_frac * documents))
    weights: dict[str, float] = {}
    for term, count in counts.items():
        if count < min_df or count > ceiling:
            continue
        weights[term] = float(count) if weight == "df" else 1.0
    return Topic(weights, frozenset(counts), documents)


def alignment(text: str, topic: Topic, *, n_max: int | None = None) -> float:
    """Fraction of the candidate's terms that the references and wiki pages already share."""
    n_max = N_MAX if n_max is None else n_max
    terms = terms_of(text, n_max)
    if not terms or not topic.weights:
        return 0.0
    return len(terms & topic.weights.keys()) / len(terms)


def shared_terms(text: str, topic: Topic, *, n_max: int | None = None, limit: int = 12) -> list[str]:
    n_max = N_MAX if n_max is None else n_max
    present = terms_of(text, n_max) & topic.weights.keys()
    return sorted(present, key=lambda term: (-topic.weights[term], term))[:limit]


def novel_terms(text: str, topic: Topic, *, limit: int = 8) -> list[str]:
    fresh = [word for word in words_of(text) if word not in topic.known]
    # Keep first occurrence order, which follows the candidate, and cap the list.
    seen: list[str] = []
    for word in fresh:
        if word not in seen:
            seen.append(word)
        if len(seen) >= limit:
            break
    return seen


def ranked_terms(topic: Topic, limit: int = TOP_TERMS) -> list[tuple[str, float]]:
    return sorted(topic.weights.items(), key=lambda item: (-item[1], item[0]))[:limit]


def document_text(title: str, abstract: str) -> str:
    return f"{title}\n{abstract}".strip()[:TEXT_LIMIT]


def load_embed_config(root: Path) -> EmbedConfig:
    """Read the same search key and embedding model the dashboard uses.

    ``dashboard/frontend/site.json`` wins. An empty key there leaves ``OPENAI_API_KEY`` and
    ``OPENAI_CATALOG_SEARCH_ENABLED`` as the default, matching ``search_runtime``.
    """
    path = root / "dashboard" / "frontend" / "site.json"
    document: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            document = loaded
    search = document.get("search") if isinstance(document.get("search"), dict) else {}
    site_key = search.get("api_key")
    site_key = site_key.strip() if isinstance(site_key, str) else ""
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    key = site_key or env_key
    if isinstance(search.get("enabled"), bool):
        flag = search["enabled"]
    elif site_key:
        flag = True
    else:
        flag = os.environ.get("OPENAI_CATALOG_SEARCH_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    model = search.get("embedding_model")
    if not isinstance(model, str) or not model.strip():
        model = os.environ.get("OPENAI_SEARCH_EMBEDDING_MODEL", "").strip() or EMBEDDING_MODEL_DEFAULT
    else:
        model = model.strip()
    raw = os.environ.get("OPENAI_SEARCH_EMBEDDING_DIMENSIONS", "512")
    try:
        dimensions = int(raw)
    except ValueError:
        dimensions = 512
    dimensions = min(max(dimensions, 64), 3072)
    if not key:
        reason = "no search key"
    elif not flag:
        reason = "search embeddings disabled"
    else:
        reason = ""
    return EmbedConfig(bool(flag and key), key, model, dimensions, reason)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    value = sum(a * b for a, b in zip(left, right))
    return max(0.0, min(1.0, value))


def centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    total = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            total[index] += value
    return _normalize(total)


def blend(words: float, embedding: float | None) -> float:
    """Seventy percent embedding and thirty percent words, or the word score alone."""
    if embedding is None:
        return words
    return EMBED_WEIGHT * embedding + (1.0 - EMBED_WEIGHT) * words


def _cache_path(root: Path) -> Path:
    return root / ".cache" / "topic-alignment" / "embeddings.json"


def _cache_key(model: str, dimensions: int, text: str) -> str:
    payload = f"{model}\n{dimensions}\n{text}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _read_cache(path: Path) -> dict[str, list[float]]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = loaded.get("entries") if isinstance(loaded, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {key: value for key, value in entries.items() if isinstance(key, str) and isinstance(value, list)}


def _write_cache(path: Path, entries: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"entries": entries}, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _post_embeddings(texts: list[str], *, key: str, model: str, dimensions: int) -> list[list[float]]:
    """One embeddings call. The dashboard search index uses this same endpoint and model."""
    body = json.dumps({"model": model, "input": texts, "dimensions": dimensions}).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/embeddings", data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"embedding request failed ({exc.code})") from None
    except urllib.error.URLError:
        raise RuntimeError("embedding request failed") from None
    vectors: list[list[float] | None] = [None] * len(texts)
    for row in payload.get("data", []):
        vectors[int(row["index"])] = _normalize([float(value) for value in row["embedding"]])
    if any(vector is None for vector in vectors):
        raise RuntimeError("embedding response did not cover every text")
    return vectors  # type: ignore[return-value]


def embed_texts(texts: list[str], config: EmbedConfig, cache_path: Path) -> list[list[float]] | None:
    """Vectors for ``texts``, reused from ``.cache/topic-alignment``. None when embeddings are off or fail."""
    if not config.enabled or not texts:
        return None
    entries = _read_cache(cache_path)
    missing: list[str] = []
    order: list[str] = []
    for text in texts:
        key = _cache_key(config.model, config.dimensions, text)
        order.append(key)
        if key not in entries and key not in missing:
            missing.append(key)
    if missing:
        by_key = {_cache_key(config.model, config.dimensions, text): text for text in texts}
        fetch = EMBED_FETCH or _post_embeddings
        pending = [by_key[key] for key in missing]
        try:
            for start in range(0, len(pending), 64):
                batch = pending[start:start + 64]
                vectors = fetch(batch, key=config.key, model=config.model, dimensions=config.dimensions)
                if len(vectors) != len(batch):
                    raise RuntimeError("embedding response did not cover every text")
                for text, vector in zip(batch, vectors):
                    entries[_cache_key(config.model, config.dimensions, text)] = _normalize(vector)
                _write_cache(cache_path, entries)
        except (RuntimeError, OSError, urllib.error.URLError, KeyError, TypeError, ValueError):
            return None
    return [entries[key] for key in order]


def embedding_alignment(candidate: list[float], references: list[list[float]]) -> float:
    """Cosine of the candidate to the centroid of the references and wiki pages."""
    if len(references) < 2 or not candidate:
        return 0.0
    return cosine(candidate, centroid(references))


def leave_one_out(docs: list[Reference]) -> list[tuple[Reference, float]]:
    scored = []
    for index, doc in enumerate(docs):
        topic = fit(docs[:index] + docs[index + 1 :])
        scored.append((doc, alignment(f"{doc.title}\n{doc.abstract}", topic)))
    return scored


def embedding_status(config: EmbedConfig) -> str:
    if config.enabled:
        return f"embedding  {config.model}, {config.dimensions} dimensions"
    return f"embedding  off ({config.reason})"


def format_topic(topic: Topic, config: EmbedConfig, *, references: int, wiki_pages: int) -> str:
    lines = [
        f"{references} references, {wiki_pages} wiki pages, {len(topic.weights)} topic terms "
        f"(a term shared by at least {min(MIN_DF, topic.documents)} documents)",
        embedding_status(config),
    ]
    if not topic.ready:
        lines.append("No standing topic yet. Two documents have to share a term before one exists.")
        return "\n".join(lines)
    width = max(len(term) for term, _ in ranked_terms(topic))
    lines.append(f"{'term'.ljust(width)}  documents")
    for term, weight in ranked_terms(topic):
        lines.append(f"{term.ljust(width)}  {int(weight)}")
    return "\n".join(lines)


def request_match(subject: str, candidate: str, config: EmbedConfig, cache_path: Path) -> tuple[float, float | None]:
    """How much of an explicit subject the candidate covers.

    The word part is the fraction of the subject's own terms that appear in the candidate.
    The embedding, when the search key is available, is the cosine between the subject and
    the candidate. The blend matches standing alignment: seventy percent embedding.
    """
    asked = terms_of(subject)
    covered = (len(asked & terms_of(candidate)) / len(asked)) if asked else 0.0
    if not config.enabled:
        return covered, None
    vectors = embed_texts([subject.strip()[:TEXT_LIMIT], candidate[:TEXT_LIMIT]], config, cache_path)
    if vectors is None:
        return covered, None
    return blend(covered, cosine(vectors[0], vectors[1])), cosine(vectors[0], vectors[1])


def format_score(text: str, topic: Topic, words: float, embedding: float | None, note: str,
                 request: float | None = None) -> str:
    shared = ", ".join(shared_terms(text, topic)) or "(none)"
    novel = ", ".join(novel_terms(text, topic)) or "(none)"
    embedded = f"{embedding:.3f}" if embedding is not None else f"unavailable ({note})"
    lines = []
    if request is not None:
        lines.append(f"request    {request:.3f}")
    lines.extend([
        f"alignment  {blend(words, embedding):.3f}",
        f"words      {words:.3f}",
        f"embedding  {embedded}",
        f"shared     {shared}",
        f"novel      {novel}",
    ])
    return "\n".join(lines)


def score_text(text: str, docs: list[Reference], config: EmbedConfig, cache_path: Path,
               reference_vectors: list[list[float]] | None = None) -> tuple[float, float | None, str]:
    """Word score, embedding cosine, and a note when the embedding is absent."""
    words = alignment(text, fit(docs))
    if len(docs) < 2:
        return words, None, "fewer than two documents"
    if not config.enabled:
        return words, None, config.reason
    if reference_vectors is None:
        vectors = embed_texts([document_text(doc.title, doc.abstract) for doc in docs] + [text], config, cache_path)
        if vectors is None:
            return words, None, "embedding request failed"
        return words, embedding_alignment(vectors[-1], vectors[:-1]), ""
    candidate = embed_texts([text], config, cache_path)
    if candidate is None:
        return words, None, "embedding request failed"
    return words, embedding_alignment(candidate[0], reference_vectors), ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, help="repository root (default: discovered from this file)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("topic", help="print the standing topic of the references and compiled wiki")

    score = sub.add_parser("score", help="score one candidate against the references and compiled wiki")
    score.add_argument("--topic", default="", help="explicit subject; request is then the score to prefer")
    score.add_argument("--title", default="", help="candidate title")
    score.add_argument("--abstract", default="", help="candidate abstract or repository description")
    score.add_argument("text", nargs="*", help="extra candidate text")

    sub.add_parser("eval", help="leave-one-out check of the current settings on this collection")
    sub.add_parser("rank", help="score each reference against the other references and the wiki")

    args = parser.parse_args(argv)
    root = (args.root or find_repo_root()).resolve()
    references = load_references(root)
    wiki = load_wiki(root)
    corpus = references + wiki
    topic = fit(corpus)
    config = load_embed_config(root)
    cache = _cache_path(root)
    if args.command == "topic":
        print(format_topic(topic, config, references=len(references), wiki_pages=len(wiki)))
        return 0
    if args.command == "score":
        text = "\n".join(part for part in (args.title, args.abstract, " ".join(args.text)) if part.strip())
        if not text.strip():
            parser.error("score needs --title, --abstract, or text")
        words, embedded, note = score_text(text, corpus, config, cache)
        request = None
        if args.topic.strip():
            request, _embedded = request_match(args.topic, text, config, cache)
        print(format_score(text, topic, words, embedded, note, request))
        return 0
    if args.command == "rank":
        print(format_rank(rank_references(references, wiki, config, cache)))
        return 0
    print(evaluate(references, wiki, config, cache))
    return 0


# Off-topic controls for eval. They are not part of scoring a real candidate.
OFF_TOPIC = (
    "A survey of sourdough fermentation in home kitchens, covering starter hydration, crumb structure, and baking schedules for wheat and rye loaves.",
    "We present a buffer pool replacement policy for relational databases that reduces cache misses on join-heavy analytical queries over columnar storage.",
    "This essay reconstructs the grain trade between Mediterranean ports in the twelfth century from notarial registers and customs accounts.",
    "A convolutional network for classifying bird species in camera-trap photographs, trained on bounding boxes of plumage and beak shape.",
)


def rank_references(references: list[Reference], wiki: list[Reference], config: EmbedConfig,
                    cache_path: Path) -> list[tuple[Reference, float, float, float | None]]:
    """Each reference against the other references plus every compiled wiki page."""
    texts = [document_text(doc.title, doc.abstract) for doc in references + wiki]
    vectors = embed_texts(texts, config, cache_path) if config.enabled else None
    if vectors is not None and len(vectors) != len(texts):
        vectors = None
    ref_vectors = vectors[:len(references)] if vectors is not None else None
    wiki_vectors = vectors[len(references):] if vectors is not None else []
    ranked = []
    for index, doc in enumerate(references):
        others = references[:index] + references[index + 1:] + wiki
        words = alignment(f"{doc.title}\n{doc.abstract}", fit(others))
        embedded = None
        if ref_vectors is not None:
            neighbors = ref_vectors[:index] + ref_vectors[index + 1:] + wiki_vectors
            embedded = embedding_alignment(ref_vectors[index], neighbors)
        ranked.append((doc, blend(words, embedded), words, embedded))
    ranked.sort(key=lambda item: (-item[1], item[0].id))
    return ranked


def format_rank(ranked: list[tuple[Reference, float, float, float | None]]) -> str:
    lines = [f"{'alignment':>9}  {'words':>6}  {'embedding':>9}  id"]
    for doc, score, words, embedded in ranked:
        embedded_text = f"{embedded:.3f}" if embedded is not None else "off"
        lines.append(f"{score:9.3f}  {words:6.3f}  {embedded_text:>9}  {doc.id}")
    return "\n".join(lines)


def evaluate(references: list[Reference], wiki: list[Reference], config: EmbedConfig, cache_path: Path) -> str:
    ranked = rank_references(references, wiki, config, cache_path)
    word_scores = [words for _, _, words, _ in ranked]
    blend_scores = [score for _, score, _, _ in ranked]
    embed_scores = [embedded for _, _, _, embedded in ranked if embedded is not None]
    corpus = references + wiki
    full = fit(corpus)
    off_words = [alignment(text, full) for text in OFF_TOPIC]
    texts = [document_text(doc.title, doc.abstract) for doc in corpus]
    vectors = embed_texts(texts, config, cache_path) if config.enabled else None
    off_embed: list[float] = []
    if vectors is not None and len(vectors) == len(texts):
        extra = embed_texts(list(OFF_TOPIC), config, cache_path)
        if extra is not None:
            center = centroid(vectors)
            off_embed = [cosine(vector, center) for vector in extra]
    lines = [_eval_line("words", word_scores, off_words)]
    if embed_scores and off_embed:
        lines.append(_eval_line("embedding", embed_scores, off_embed))
        off_blend = [blend(words, embedded) for words, embedded in zip(off_words, off_embed)]
        lines.append(_eval_line("alignment", blend_scores, off_blend))
    else:
        note = "embedding request failed" if config.enabled else config.reason
        lines.append(f"embedding   off ({note})")
        lines.append(_eval_line("alignment", blend_scores, off_words))
    lines.append("lowest held-out references:")
    for doc, score, words, embedded in sorted(ranked, key=lambda item: item[1])[:8]:
        embedded_text = f"{embedded:.3f}" if embedded is not None else "off"
        lines.append(f"  {score:.3f}  {doc.id}  words={words:.3f}  embedding={embedded_text}")
    growth = []
    ordered = list(references)
    wiki_texts = [document_text(doc.title, doc.abstract) for doc in wiki]
    wiki_vectors = vectors[len(references):] if vectors is not None and len(vectors) == len(texts) else None
    for size in (8, 16, 32):
        if len(ordered) <= size:
            continue
        topic = fit(ordered[:size] + wiki)
        later_words = [alignment(f"{doc.title}\n{doc.abstract}", topic) for doc in ordered[size:]]
        off = max(alignment(text, topic) for text in OFF_TOPIC)
        piece = f"k={size} words={_median(later_words):.3f} off={off:.3f}"
        if wiki_vectors is not None:
            center = centroid(vectors[:size] + wiki_vectors)
            later_embed = [cosine(vector, center) for vector in vectors[size:len(references)]]
            piece += f" embedding={_median(later_embed):.3f}"
        growth.append(piece)
    if growth:
        lines.append("as the collection grows (earliest references first, wiki held fixed): " + "; ".join(growth))
    return "\n".join(lines)


def _eval_line(label: str, scores: list[float], off: list[float]) -> str:
    ordered = sorted(scores)
    return (
        f"{label.ljust(11)} leave-one-out n={len(ordered)}  median={_median(ordered):.3f}  "
        f"p10={_percentile(ordered, 10):.3f}  min={ordered[0] if ordered else 0:.3f}  "
        f"off-max={max(off) if off else 0:.3f}"
    )


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[index]


if __name__ == "__main__":
    raise SystemExit(main())
