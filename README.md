![Veronica: burgundy circles and a flower on a dark background](assets/veronica-poster.jpg)

# Veronica, an optimized Ruflo?

**🌸 Give a long AI project a clear path forward, a place to save its progress, and a way to check the result.**

Ever returned to an AI project and spent the first hour explaining it all over again? Veronica helps your assistant keep the goal, detailed requirements, decisions, unfinished work and next steps in your workspace, ready for the next session.

**Veronica 1.2.0** is a reusable skill with lightweight local tools. Your assistant does the thinking and uses the tools available in its environment; Veronica gives that work continuity and structure.

[🚀 Get started](#-get-started) · [🌸 What's new](#-whats-new-in-120) · [📊 Measured results](#-what-we-actually-measured) · [📣 Announcement](docs/ANNOUNCEMENT.md)

## 🧭 Built for work that takes more than one sitting

Research a difficult topic. Build an app. Prepare a report with dozens of sources. Improve a project over several rounds of feedback.

Veronica helps turn that large objective into useful tasks, tracks which tasks depend on others, and records discoveries as the work evolves. It saves a handoff with what has been done, what remains uncertain and what to do next. When you return, the assistant can check the actual files and continue from that record.

Detailed inputs and original files remain available alongside shorter views. A handoff is a route back to the work, not a replacement for its full history. The model still has a finite context window, so continuity depends on preserving and consulting those records.

## 🤝 A team when the project benefits from one

When your environment supports agents and their use is authorized, Veronica guides the assistant in dividing independent work: one agent researches, another implements, another reviews.

Each assignment gets an expected deliverable, completion criteria and a declared area for writing. Cooperative reservations help avoid overlapping edits; dependencies keep unfinished work from being treated as ready. Handoffs carry relevant instructions and inputs, and the lead assistant checks the combined result.

Extra agents bring context and coordination costs. The workflow considers those costs before delegating. Its helpers track assignments and reservations; the host provides and launches the agents.

## 🧰 Choose useful tools for the actual job

Agents, other skills, MCP servers, connectors, plugins, command-line tools, libraries and direct execution can all be considered when available and authorized.

The assistant looks for a concrete advantage: faster access to a source, a reliable conversion, a reusable operation, or a better verification. It considers setup, extra calls, context, local resources and the quality of the outcome.

That can support research, coding, document production and other workflows through your environment's capabilities. Veronica provides the work ledger, artifact storage, checks and recovery; it does not install integrations or supply every tool itself.

## 💡 Efficiency that keeps room to think

The goal is to remove repeated work and unnecessary context while preserving detailed requirements and the freedom to investigate.

- 🔎 **Read what is relevant now.** Focused task views, explicit index pages and literal searches help locate material. Full originals remain accessible.
- 📚 **Load instructions when needed.** The entrypoint stays compact; deeper operation, coordination and recovery guides are consulted for their specific jobs.
- ♻️ **Reuse verified work.** Exact duplicates can share storage while keeping their separate origins. Artifact compaction is optional, reversible and checked for byte equality.
- 🧾 **Keep usage honest.** Observed token records and estimates are separate. Unknown values remain unknown; duplicate events are handled without counting them twice.

There is no imposed token quota, forced model downgrade or instruction to reduce reasoning. The workflow does not change your host's limits or subscription.

### 🎛️ How the approach adapts

| The work in front of you | A useful approach |
| --- | --- |
| A quick, self-contained request | Execute directly with minimal process. |
| A large project with lots of material | Consult relevant tasks and sources, then expand as needed. |
| Independent research or implementation | Consider parallel agents if the benefit justifies the overhead. |
| An interruption or inconsistent state | Diagnose, reconcile records and use verified recovery when needed. |

These are workflow choices made by the assistant, not fixed performance presets or an automatic model router. The approach can change as the project changes.

## 🛡️ Progress you can inspect, and recovery you can check

“Done” needs evidence tied to the task's criteria. The helpers can check whether attached files changed, whether evidence expired and whether dependencies still have current acceptance. The assistant or reviewer evaluates whether the result is actually good.

Original artifacts can be retrieved byte for byte. Recovery bundles collect the work ledger, artifact catalog and explicitly selected project files, with hashes checked before restoration into a new workspace.

If an external action has an uncertain result, the workflow records that uncertainty and calls for checking the destination before retrying. This matters for actions such as publication, where repeating an unconfirmed operation can cause confusion.

## 🌸 What's new in 1.2.0?

- 🧳 **Recovery bundles:** carry saved process state and selected deliverables into a new workspace, with verification.
- 🩺 **Deeper checks on demand:** inspect dependencies, artifacts and generated status files when troubleshooting.
- 🧩 **Reconcile interrupted captures:** saved receipts help reconnect intact artifacts with their catalog.
- 📄 **Focused navigation:** paginate the unrelated task index while retaining selected task/dependency details and global notes.
- 🔒 **Stronger concurrent work:** safer usage recording and status generation; staged file restoration avoids overwriting existing destinations.
- 🪜 **Long dependency chains:** iterative traversal avoids recursive call-stack limits.
- 🪶 **A smaller entrypoint:** detailed procedures stay in references loaded when needed.

The feature package was first published as 1.1.2. **1.2.0 corrects its semantic version:** compatible new capabilities warrant a minor release. The old tag remains in the history. See [release notes](docs/releases/1.2.0.md) and [versioning policy](docs/VERSIONING.md).

## 📊 What we actually measured

The previous runtime passed **59 regression tests** and **261 controlled local workflow executions**, checking individual modules, varied combinations and the full group. Its CI passed on Windows and Ubuntu with Python 3.10 and 3.12. The runtime implementation is retained in 1.2.0; version labels and public presentation are updated.

In the measured targeted-context comparison, shared evidence hashing went from **24 calls to 1: 95.83% fewer evidence-hash calls**, with the same **5,403 returned UTF-8 bytes**. The earlier entrypoint reduction was **9.94% in UTF-8 bytes**.

We measured the cost of enabling everything too: the full six-module combination returned **15.84% more bytes** than the targeted native approach. That supports choosing tools selectively.

**These are local measurements, not a demonstrated percentage of billed token or dollar savings.** No model/API calls were used in that workflow benchmark. See the [validation report](docs/VALIDATION-1.2.0.md) for scope and evidence.

## 🏗️ How it is built

**Instructions guide judgment. Python handles repeatable operations. SQLite keeps the process state.**

The runtime uses Python 3.10+ and its standard library, with no additional runtime dependency or resident service. Routine operations can call the helpers without loading their whole source into the model's context.

Your host controls the model, tool access and execution. Veronica does not keep a chat running after its host stops; recovery bundles do not restore apps or logins.

## 🚀 Get started

Install the [`veronica/`](veronica/SKILL.md) folder in your environment's personal skills directory, preserving its structure. Then ask:

> Use $veronica to manage this project. Preserve the detailed requirements, organize the work, record verification and keep the next step ready for our next session.

To resume:

> Use $veronica to resume this workspace and check what remains.

The assistant needs workspace access and the tools required for your objective. Public introductions are in English; the personal skill and detailed guides are in Portuguese. Browse the [examples](docs/EXEMPLOS.md), [operation guide](veronica/references/operacao.md) and [recovery guide](veronica/references/recuperacao.md).

<details>
<summary>🔧 Commands, tests and folder structure</summary>

Replace `PROJECT` and the Python executable with your actual paths. In Windows PowerShell, use `&` before a quoted executable path.

```sh
python veronica/scripts/veronica.py --workspace PROJECT status
python veronica/scripts/veronica.py --workspace PROJECT context --task TASK_ID --index-limit 20
python veronica/scripts/veronica.py --workspace PROJECT doctor --deep
python veronica/scripts/preserve.py --workspace PROJECT reconcile
python veronica/scripts/recovery.py bundle --workspace PROJECT --output outputs/recovery-001 --include outputs/deliverable
python veronica/scripts/recovery.py restore --bundle BUNDLE_PATH --workspace NEW_WORKSPACE
python -m unittest discover -s veronica/scripts -p "test_*.py" -v
```

Bundle only stable product files. Cooperating SQLite writers are coordinated; other applications' writes require separate coordination.

```text
veronica/SKILL.md              workflow entrypoint
veronica/agents/openai.yaml    skill metadata
veronica/scripts/              standard-library helpers and tests
veronica/references/           guides consulted when needed
docs/                         presentation, versioning and validation
assets/                       Veronica poster
scripts/compare_workflows.py   optional development benchmark
.github/workflows/tests.yml    regression checks
```

A project's private state lives under `work/veronica/`, outside this distribution.

</details>

## 🌱 Inspiration and participation

Veronica is an independent implementation. Its research included [Ruflo](https://github.com/ruvnet/ruflo), [Superpowers](https://github.com/obra/superpowers), GSD and other projects; see the [design references](veronica/references/origens.md).

The title remains a question: we have not demonstrated a performance or token-consumption comparison against Ruflo. Share a concrete use case, reproducible issue or measured improvement through the repository's [issues](https://github.com/joaoreislab/veronica/issues). See [CONTRIBUTING.md](CONTRIBUTING.md). A distribution license has not been selected; public availability alone does not grant an open-source license.
