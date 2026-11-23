# Docker Images

## Base image (`Dockerfile.base`)

Shared foundation for the per-attempt Dockerfiles in `references/<id>/attempts/<slug>/`.

```bash
docker build -f skills/runtime-env/assets/docker/Dockerfile.base -t lab-base:latest .
```

Per-attempt Dockerfiles start from `Dockerfile.attempt.template`:

```dockerfile
FROM lab-base:latest
# ... attempt-specific setup
```

See `skills/runtime-env/references/isolation-boundaries.md` for when to use docker-attempt isolation.
