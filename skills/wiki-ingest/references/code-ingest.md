# Code-source ingest

Use for repository snapshots under `references/<id>/repos/<name>/`, reproduction code under
`references/<id>/reproduce/`, the lab package under `lib/src/<package>/` (when configured), code cited by completed labs,
and other code explicitly selected for project knowledge.

## Read order

1. The reference's `provenance.json` and the repository license.
2. README, documentation, manifests, lockfiles, and environment definitions.
3. Entry points, public APIs, core modules, configurations, and data-flow boundaries.
4. Tests, examples, numerical checks, and error handling.
5. Only then, supporting modules needed to verify architecture or algorithm details.

Ignore vendored dependencies, generated files, caches, binaries, and bulk data unless they are
scientifically consequential. Code from `references/` is read, not run, during an ingest; running it
belongs to a reproduction inside an isolated runtime (`skills/runtime-env`).

## Compile into the wiki

Extract architecture, interfaces, algorithms, dependency assumptions, numerical conventions, defaults,
supported regimes, tests, known gaps, and failure modes. Create `implementations/` pages for durable
components or end-to-end systems and use `methods/` for the underlying scientific or computational method;
link them both ways. When package code changes what a user of the package sees, also update the matching
page of the package manual in `wiki/package/` (plain Markdown; see `wiki/README.md`).

Register the repository or file in `sources.yml`, then cite exact files with a symbol, class or function,
configuration key, test name, commit, or stable line locator, for example
``[Lib, `<package>/module.py`, SomeSymbol](../../lib/src/<package>/module.py)``.
Do not paste large code blocks into the wiki; summarize behavior and link to the file.

Static inspection establishes what code appears to do, not that it is correct. Mark runtime or scientific
behavior as unverified until tests or a lab support it, and record mismatches between paper descriptions,
code defaults, and tested behavior.
