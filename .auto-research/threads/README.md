# Thread Messages

Each `thread-NNN.json` holds one Thread’s messages. Meta stays in `../state.json` → `threads[]`.
Parent contract: `../README.md`.

```json
{
  "messages": [
    {
      "id": "msg-001",
      "author": "agent",
      "type": "question",
      "created": "2026-11-20T09:41:22Z",
      "content": "…"
    }
  ]
}
```

Only top-level key: `messages` (non-empty). Ids are sequential (`msg-001`, `msg-002`, …). Append
only via `skills/research-threads/scripts/research_threads.py`.

## Message fields

Exact keys (no extras):

| Field | Type | Rules |
| --- | --- | --- |
| `id` | string | `msg-NNN`; `messages[0]` → `msg-001` |
| `author` | string | `user` \| `agent` |
| `type` | string | `instruction` \| `question` \| `decision` \| `reply` \| `resolution` |
| `created` | string | ISO-8601 UTC (`…Z`); must not go backwards in the list |
| `content` | string | Non-empty markdown |

Author locks: `instruction` and `decision` → `user` only; `question` → `agent` only;
`reply` and `resolution` → either.

First message must be `instruction` or `question`. A closed thread’s last message must be
`resolution`. `state.threads[].created` equals `messages[0].created`; `updated` ≥ last
`created`.

```bash
.venv/bin/python skills/auto-research/scripts/auto_research_lint.py
```
