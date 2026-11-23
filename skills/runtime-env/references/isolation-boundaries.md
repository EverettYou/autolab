# Isolation boundaries

Policy enums come from `resolve_policy` (facts → decisions). Do not invent a second rule from
hostname or vendor brand.

| `POLICY_ISOLATION` | Meaning |
|--------------------|---------|
| `host-control-plane` | Bare host (no container, no docker for attempts). Trusted first-party only. |
| `this-container` | Current container **is** the isolation boundary. |
| `docker-attempt` | Host has Docker/Podman; untrusted work runs in an attempt image, not on the host. |

| `POLICY_UNTRUSTED_CODE` | Meaning |
|-------------------------|---------|
| `forbid` | Do not execute untrusted third-party reproduction code here. Stage attempts for a machine with a real boundary. |
| `allow-in-attempt-workspace` | Run untrusted code only under `references/<id>/attempts/<slug>/` (per-attempt venv, smoke cap). |
| `only-in-container` | Build/run attempt containers; never bind-mount host secrets or the Docker socket into them. |

## Docker attempt assets (host + Docker)

Templates live under `skills/runtime-env/assets/docker/`:

```bash
docker build -f skills/runtime-env/assets/docker/Dockerfile.base -t lab-base:latest .
# then attempt Dockerfile from Dockerfile.attempt.template
```

Network: available during `docker build`; disable at run (`--network none`) for untrusted smoke.
Mount only designated output dirs. See `assets/docker/README.md`.

## Conflict with human instruction

If policy conflicts with an explicit researcher instruction, record it in a discussion thread
(`thread-interaction`) and continue with work that does not depend on the disputed path.
