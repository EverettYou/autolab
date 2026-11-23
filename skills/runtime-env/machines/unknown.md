# Machine profile — unknown / unresolved

The fingerprint didn't clearly match a known profile. **Be conservative: do not run untrusted
reproduction code until the runtime is resolved.** The trust-zone rule (external code only inside
an isolated runtime, `wiki/project/distillation-tower.md`) still binds.

## What to do

1. Re-run `bash skills/runtime-env/scripts/detect.sh` and read every line.
2. Decide the two questions that determine strategy:
   - **Am I isolated?** In a container, or on a host I'm willing to treat as disposable? If on a
     shared host control plane → do NOT execute external code; open a discussion thread for the
     human (`research-threads`) and switch to read-only or non-reproduction work in the meantime.
   - **Can I get isolation?** Is there `docker`/`podman` (→ `generic-host-with-docker.md`), or am
     I already in a container that can serve as the isolation boundary (→ `generic-container.md`)?
3. If it matches an existing profile after inspection, use that profile and consider adding a
   fingerprint note there.
4. If it's a genuinely new environment, **write a new `machines/<id>.md`** capturing its
   fingerprint + isolation + Python-env strategy, add a row to `SKILL.md`'s match table, then
   follow it.

## Safe defaults while unresolved

- Read-only analysis (mapping a repository with the code-map checklist, reading papers) is always
  fine.
- Trusted, first-party code (the lab package under `lib/`, its tests) may run in a fresh venv.
- **Untrusted third-party reproduction code:** blocked until isolation is confirmed. Stage the
  attempt (Dockerfile, `run.sh`, README in `references/<id>/attempts/<slug>/`) so it is ready to
  RUN when the profile resolves.
- Keep working on other things (discovery, promotion coding, refactors, wiki, documentation) until
  the profile is resolved; an unresolved runtime blocks only external code execution.
