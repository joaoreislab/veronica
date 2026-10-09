# Veronica, an optimized Ruflo?

**An agent skill for long-running AI projects, with persistent state, resumable work and verifiable completion.**

**Version 1.1.2** strengthens recovery and concurrency while keeping the skill entrypoint smaller. Python 3.10+ and the standard library are sufficient for its runtime. No resident service, model router or mandatory agent swarm is required.

When work spans several sessions, Veronica keeps the goal, dependencies, decisions, next steps and evidence in the workspace. The assistant performs the work with the host's tools; the local helpers preserve and validate the process records.

## Capabilities

| Capability | What it provides |
| --- | --- |
| Persistent work ledger | Goals, tasks, dependencies, attempts, decisions and events in SQLite. |
| Resumption | `RETOMAR.md`, complete structured context and next actions. |
| Current completion evidence | Per-criterion evidence with attachment hashes, expiry and dependency acceptance. Semantic judgment stays with the executor. |
| Cooperative coordination | Executor leases and declared write areas; available agents are used when authorized and useful. |
| Exact artifacts | SHA256 snapshots, separate provenance, byte-exact recovery and literal search. |
| Optional context views | Complete originals remain available. Task views and explicit index pages help navigate larger projects. |
| Observed usage accounting | Idempotent event records, explicit unknown values and separate estimates. No forced model downgrade or budget cap. |
| Recovery bundles | Ledger, artifact catalog, blobs, receipts and explicitly selected product files, verified before restoration into a new workspace. |
| Deep diagnostics | Logical state, dependency cycles, artifact consistency and projection generation checks, on demand. |
| Uncertain external effects | Preserve uncertainty and require destination reconciliation before retrying an action. |

## What changed in 1.1.2

- Reject malformed task/evidence fields before committing unusable state.
- Validate usage identities and handle invalid legacy records without silently counting them as complete.
- Serialize duplicate usage writes, including concurrent callers.
- Stage and verify restored files before atomic promotion without overwriting an existing destination.
- Serialize dashboard generation with ledger writers and mark each generation with revision and hashes.
- Traverse long dependency chains iteratively.
- Preserve capture receipts so an interrupted catalog commit can be reconciled explicitly.
- Add `doctor --deep`, artifact reconciliation and recovery bundles without making them a startup ritual.
- Shorten the skill entrypoint and keep detailed procedures in references loaded when needed.

See [release notes](docs/releases/1.1.2.md) and the [validation report](docs/VALIDATION-1.1.2.md).

## Get started

Install the [`veronica/`](veronica/SKILL.md) folder into your environment's personal skills directory. Keep its name and internal structure. In a conversation that loads the skill, ask:

> Use $veronica to manage this project, preserve the detailed requirements, record verification and keep the next step.

To continue:

> Use $veronica to resume this workspace and check what remains.

Small tasks can proceed directly. The assistant needs workspace access and the tools required for the actual objective. See the [operation guide](veronica/references/operacao.md), [recovery guide](veronica/references/recuperacao.md) and [examples](docs/EXEMPLOS.md).

Public introductions and release notes are in English. The personal skill instructions and reference guides are in Portuguese.

## Example commands

Replace `PROJECT` and the Python executable with your actual paths. On Windows PowerShell, invoke a quoted executable path with `&`.

```sh
python veronica/scripts/veronica.py --workspace PROJECT status
python veronica/scripts/veronica.py --workspace PROJECT context --task TASK_ID --index-limit 20
python veronica/scripts/veronica.py --workspace PROJECT doctor --deep
python veronica/scripts/preserve.py --workspace PROJECT reconcile
python veronica/scripts/recovery.py bundle --workspace PROJECT --output outputs/recovery-001 --include outputs/deliverable
python veronica/scripts/recovery.py restore --bundle BUNDLE_PATH --workspace NEW_WORKSPACE
```

Recovery bundles include product files only when explicitly selected. They do not restore applications, services, credentials or external resources. Stabilize product writers before bundling; SQLite locks coordinate cooperating ledger/catalog writers, not other applications.

## Validation

Run the regression suite from the repository root:

```sh
python -m unittest discover -s veronica/scripts -p "test_*.py" -v
```

The suite covers persistence, reservations, concurrent writes, stale evidence, Unicode/CRLF preservation, injected interruptions, artifact reconciliation, projection consistency, deep dependencies and restoration into a new process. The release report distinguishes these tests from workflow comparisons and model/API measurements.

Local bytes, hashing and timing measurements do not establish billed token savings or general model quality. Synthetic usage records test accounting, not actual provider charges. Checkpoints of the ledger remain available with their original scope; recovery bundles are a separate operation.

## Structure

```text
veronica/SKILL.md              concise workflow entrypoint
veronica/agents/openai.yaml    skill metadata
veronica/scripts/              standard-library runtime and tests
veronica/references/           guides consulted when needed
docs/                         English presentation and release evidence
scripts/compare_workflows.py   optional development benchmark
.github/workflows/tests.yml    regression checks
```

During use, the project's private state lives under `work/veronica/`. It is excluded from this distribution. Scripts can be executed through their documented interface; their full implementation does not have to be loaded into the model's context for routine use.

## Veronica and Ruflo

Veronica is an independent implementation. Its design research included [Ruflo](https://github.com/ruvnet/ruflo), [Superpowers](https://github.com/obra/superpowers), GSD and other projects. Attribution and design references are in [origens.md](veronica/references/origens.md).

The question in the title remains open: no performance, token-consumption or productivity comparison against Ruflo has been demonstrated. Veronica focuses on workflow instructions and a local work ledger; its helpers do not launch agents or MCP servers and do not keep a chat running after its host stops.

## Contribute and license

See [CONTRIBUTING.md](CONTRIBUTING.md). Start with a concrete case, reproducible failure or measured comparison. A distribution license has not been selected; public availability alone does not grant an open-source license.
