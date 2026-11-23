# Discovery modes and selection lenses

## Modes

| Mode | When | Success means |
|------|------|---------------|
| `directed` | A request, thread, or task names a target | The target is found and dispositioned |
| `freshness` | Synthesis asks to broaden, or a periodic new-paper window | New candidates since the last discovery record |
| `coverage-gap` | The roster, a task, or an evaluation grid names an open cell | The gap is confirmed, narrowed, or closed |
| `released-assets` | A study-only candidate has a revisit trigger (code, weights) | New code, weights, or repository activity found or ruled out |
| `theory-codes` | The request or the overlap is about constructions rather than a runnable method | The construction is captured; runnable ones are proposed for reproduction |
| `negative-confirm` | The same gap was searched recently | Axes searched again with no new candidates, and no churn |

For `freshness` and `coverage-gap`, the query axes are the explicit subject when the scope names
one, and otherwise the highest-ranked terms from `scripts/topic_alignment.py topic`. A coverage
gap is a term the request or a wiki coverage page names that is missing or rare in the catalog.
A freshness window is those same terms restricted to work newer than the last discovery record.
With no subject and no standing topic, do not run either mode.

## Lenses

No single lens is a hard gate; be selective, not aggressive.

| Lens | Pass signals | Reject or deprioritize |
|------|--------------|------------------------|
| Topic relevance | Matches the search topic: the explicit subject when the scope names one, otherwise the standing overlap. Also fills a gap the catalog does not already cover; a runnable method, a substantive construction, or tooling whose design the project can learn from | Shares none of that search topic; repeats a cluster the catalog already covers |
| Research quality | Clear method and quantitative results on the collection's measures; honest scope; code, data, weights, or enough detail to reproduce; peer-reviewed or substantial preprint | Position papers; no numbers; vague method; no baselines; a setup that does not match the collection |
| Author credibility | Prior work in the same vein, or a known group; a repository with real commits or releases | Untraceable one-offs; empty or fork-only repositories; sensational titles with thin substance |

## Dispositions

- `pass`: strong relevance, adequate quality and credibility. Eligible for `fetch-reference`.
- `study-only`: relevant and worth knowing, but no runnable asset or not worth the fetch. Listed
  only; `wiki-ingest` may record it.
- `reject`: fails relevance, quality, or credibility. One-line reason.

Prefer a candidate that matches the search topic and adds a setting, method, or asset the
collection does not already have, over another item that repeats a cluster the catalog already
covers. The search topic is the explicit subject when the scope names one, and the standing
overlap otherwise.

## Asset classes

| Class | What to fetch | Example |
|-------|---------------|---------|
| paper-primary | The PDF is required (the reproduction builds from the paper) | a method without released code |
| repo-primary | The repository is the target; the PDF is strongly recommended | a method with released code or weights |
| study-only | Nothing | theory without code |

When a method ships artifacts, state whether the release is code, data, weights, or inference-only.
