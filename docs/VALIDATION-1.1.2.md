# Validation — Veronica 1.1.2

Local validation on Windows, Python 3.12.14. This is finite regression and fixture evidence, not a model-quality or provider-billing benchmark.

## Regression suite

**59 tests passed:** 34 existing tests and 25 added tests. The added suite covers malformed fields and atomic rollback, invalid legacy usage, interrupted restore/retry, competing destinations, temporary corruption, two real usage-writing processes, conflicting usage, capture-commit interruption and idempotent reconciliation, unknown-provenance blobs, corrupt artifacts, interleaved projection writers, partial generation detection, a 1,201-task accepted dependency chain, explicit index pages, deep logical diagnostics, read-only inspection, bundle restoration, uncertain external effects, expired leases and new-process resumption.

```sh
python -m unittest discover -s veronica/scripts -p "test_*.py" -v
```

The workflow test uses synthetic usage fields. No real external effect is performed in its fixtures. Readiness, semantic correctness and credentials of real applications are outside these tests.

## Component combinations

**261 controlled workflows passed:** 29 conditions × 3 fixture types × 3 repetitions. Conditions include 6 individual modules, all 15 pairs, 4 triples, all 6 modules together, 2 controls and an adaptive strategy. Fixture types are repetitive, unique and Unicode text, with rare errors and an old decisive constraint. Expected answers, original bytes and accounting invariants are checked before comparing sizes or local timing.

Modules: shared snapshots, reversible codec, literal queries, per-call hash reuse, task context and idempotent usage. New recovery/diagnostic operations are covered by the regression suite, including combined ledger/artifact/usage/effect restoration; the matrix does not claim exhaustive combinations of all possible integrations.

| Fixture | Targeted control bytes | Adaptive bytes | All six modules bytes | Median local ms: control / adaptive / all |
| --- | ---: | ---: | ---: | ---: |
| repetitive | 5,403 | 5,403 | 6,259 | 63.56 / 51.52 / 140.82 |
| unique | 5,403 | 5,403 | 6,259 | 79.33 / 56.59 / 139.69 |
| unicode | 5,403 | 5,403 | 6,259 | 74.55 / 47.30 / 143.55 |

The adaptive strategy returned the same 5,403 bytes as targeted native selection in these fixtures, with evidence hashing reduced from 24 operations to 1 (**95.83% fewer evidence hash operations**). This counts hashes inside the measured state query, not every hash used by the full application.

All six modules returned 6,259 bytes: **15.84% more than the targeted control**, and they added local work in this pilot. Capture receipts and explicit accounting status are useful reliability data with a cost. This is why optional mechanisms are selected for a task rather than all enabled as a default workflow.

The full-content control returned 39,803–67,175 bytes. Both targeted native selection and the adaptive strategy avoid that inefficient reading pattern. Their reduction against it is not uniquely attributable to Veronica. Timings include local storage/hash/codec work; filesystem cache, system load and three repetitions limit generalization.

## Context and runtime footprint

The skill entrypoint changed from **5,522 to 4,973 UTF-8 bytes**, a **9.94% reduction**. This is a file-size measurement, not a model token count. Detailed recovery guidance is a separate reference; diagnostic/recovery scripts execute through their interface when needed.

The runtime still uses Python's standard library and SQLite. PyYAML was used only in an isolated development folder to run the skill validator; it is not a runtime dependency or included in the skill package.

## Recovery boundaries and remaining work

- File restore was tested on local NTFS using hard-link promotion; other filesystems may refuse it.
- A bundle includes the ledger, an existing artifact store and explicitly selected product files. Unselected files, applications and external resources are not restored.
- Cooperating ledger/catalog writers are serialized. Product writers must be stable; this is not a distributed snapshot protocol.
- Old leases expire on import. Unknown external effects stay unknown; the executor must reconcile their destination.
- Invalid legacy data is preserved and reported. An old orphan without a valid receipt is not assigned invented provenance.
- Logical diagnostics validate the implemented shapes/references, not every possible semantic defect. Hashes cover declared data only.
- No provider API tokens, dollars, general productivity gains, long-duration stability or performance against Ruflo were measured.

Full comparison data: [benchmark.json](benchmarks/benchmark-1.1.2.json) and [benchmark.csv](benchmarks/benchmark-1.1.2.csv). Regression log: [tests-1.1.2.log](benchmarks/tests-1.1.2.log).

Reproduce the comparison from the repository root:

```sh
python scripts/compare_workflows.py --baseline docs/benchmarks/baseline-veronica-1.0.py --output benchmark-results --repeats 3
```

The GitHub Actions matrix is configured for Windows/Ubuntu and Python 3.10/3.12. Its remote result must be read separately; the local pass alone does not confirm those environments.
