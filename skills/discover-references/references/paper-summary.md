# Paper summary checklist

Use when an abstract cannot settle a disposition, when a fetched paper needs triage before a
reproduction, or when a lab needs the paper's claims in one place. Read one paper at a time:
`references/<id>/paper.pdf` when it is archived, otherwise the arXiv HTML or PDF online without
saving it. Return only the structure below, not the paper's text.

```markdown
## Paper summary: <title> (arXiv:<id>)

Authors: ...
Year: ...

### Method
<3 to 6 bullets: the method, and the data or objective when the method is learned>

### Claimed performance
<key numbers with the setting, the measure, and the baselines>

### Reproduction requirements
- Dependencies:
- Code, weights, and data availability:
- Estimated effort: low | medium | high
- Blockers:

### Relevance
<one paragraph: which gap, regime, or question it serves, and which lens is weakest>

### Suggested id
<kebab-case; the existing reference id when already archived>
```

Rules:

- Flag missing sections instead of inventing numbers. Quote figures only as the paper states them.
- If a claim depends on an algorithm defined elsewhere, name the defining paper.
- If the PDF cannot be read, say so; do not substitute the abstract for a full read.
- Do not write files; the caller decides what to keep.
