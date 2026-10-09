# Validation — Veronica 1.2.0

## Current package check

All 59 regression tests passed locally on Windows with Python 3.12.14. The [current regression log](benchmarks/tests-1.2.0.log) records this run.

Every skill file was compared with the previously released 1.1.2 package. Only the version identifiers in `SKILL.md` and `scripts/veronica.py` changed. Runtime behavior and other skill files are retained. The package manifest contains current SHA256 hashes. The repository cover is a byte-identical copy of the provided original JPEG.

## Retained workflow measurements

The [1.1.2 validation report](VALIDATION-1.1.2.md) records 261 local workflow executions: individual modules, varied pairs, triples, the full six-module group, controls and the adaptive/native approach. Those measurements are retained evidence for the unchanged implementation; the workflow benchmark was not rerun merely to relabel the version.

The targeted-context comparison returned the same 5,403 UTF-8 bytes while evidence-hash calls went from 24 to 1 (95.83% fewer). The six-module group returned 6,259 bytes, 15.84% more than native. The earlier skill entrypoint reduction was from 5,522 to 4,973 UTF-8 bytes (9.94%). The 1.2.0 label has the same length, so the current entrypoint remains 4,973 bytes.

These are byte, operation and local workflow measurements. The benchmark used no model/API calls, and synthetic token events tested accounting only. Billed token/dollar savings, model-quality equivalence, indefinite stability and superiority over Ruflo have not been established.

## CI and scope

The prior release's [CI run](https://github.com/joaoreislab/veronica/actions/runs/37888471942) passed on Windows and Ubuntu with Python 3.10 and 3.12. The same matrix runs for the new commit and tag; consult the [Actions page](https://github.com/joaoreislab/veronica/actions) for its current status.

Finite tests check the documented cases and mechanical properties. Semantic quality still requires review of the actual deliverable. Recovery bundles include explicitly selected product files and do not restore applications, credentials or external resources.
