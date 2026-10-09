#!/usr/bin/env python3
"""Reproducible local workflow comparisons, not a model/API-cost benchmark."""
import argparse
import csv
import importlib.util
import itertools
import json
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time
from unittest.mock import patch


ROOT = Path(__file__).parent


FEATURES = ("S", "C", "Q", "H", "R", "U")
NAMES = {"S": "Snapshots compartilhados", "C": "Codec reversível", "Q": "Consulta literal", "H": "Hash por consulta", "R": "Visão da tarefa", "U": "Medição idempotente"}


def scoped(state):
    all_tasks = state["tasks"]
    state = json.loads(p.wire(state))
    state["tasks"] = {k: state["tasks"][k] for k in ("dependency", "target")}
    state["task_index"] = [{"id": k, "title": x["title"], "state": x["effective_state"], "detail": f"context --task {k}"} for k, x in all_tasks.items() if k not in state["tasks"]]
    state.update(view_scope="explicit_task_and_dependencies", complete_project_view=False, full_project_command="context")
    return state


def seed(root, case):
    root.mkdir()
    rare = "ERROR_RARE id=000007 value=null empty=\"\" anchor=🙂\t  \r\n"
    if case == "repetitive": lines = ["INFO same completed event\r\n"] * 1000
    elif case == "unique": lines = [f"ITEM {i:06} payload={i*i} owner=account-{i} status=ok\n" for i in range(1000)]
    else: lines = [f"文書 {i} ação=preservar emoji=🙂 campo={i%13}\r\n" for i in range(1000)]
    lines[113] = rare; lines[891] = rare.replace("000007", "000008")
    raw = "".join(lines).encode("utf-8")
    (root / "input.txt").write_bytes(raw)
    store = v.Store(root); store.apply({"op": "init", "goal": "Find both rare errors, preserve exact anchors and old constraints"})
    store.apply({"op": "note", "kind": "decision", "text": "Old critical constraint: preserve ordering, zeros, whitespace, null and empty strings."})
    for i in range(10): store.apply({"op": "note", "kind": "finding", "text": f"Background finding {i}"})
    for i, tid in enumerate(["dependency", "target"] + [f"other-{i}" for i in range(6)]):
        store.apply({"op": "task.add", "id": tid, "title": tid, "depends": ["dependency"] if tid == "target" else [], "criteria": [{"id": "exact", "title": "Full evidence data retained", "kind": "file"}]})
        token = store.apply({"op": "task.claim", "id": tid, "owner": "fixture"})["token"]
        store.apply({"op": "evidence.add", "id": tid, "token": token, "criterion": "exact", "kind": "file", "files": ["input.txt"], "method": "Controlled fixture", "result": "Input stable and readable", "limitations": f"Metadata-{i}: " + "reference detail; " * 30})
        store.apply({"op": "task.complete", "id": tid, "token": token})
    return raw


def workflow(root, enabled, baseline, raw, targeted=False):
    start = time.perf_counter()
    responses = []; artifacts = None
    if enabled & {"S", "C", "Q", "U"}: artifacts = p.Artifacts(root)
    hash_calls = 0; hash_bytes = 0
    def measured_digest(path):
        nonlocal hash_calls, hash_bytes
        hash_calls += 1; hash_bytes += Path(path).stat().st_size
        return original_digest(path)
    cls = v.Store if enabled & {"H", "R"} else baseline.Store
    module = v if cls is v.Store else baseline
    original_digest = module.digest
    store = cls(root)
    if "R" in enabled and "H" not in enabled: store.status = store._status
    with patch.object(module, "digest", side_effect=measured_digest):
        if "R" in enabled: state = store.context("target")
        else:
            state = store.status()
            if targeted: state = scoped(state)
    assert state["tasks"]["target"]["accepted_current"]
    assert "Old critical constraint" in state["notes"][0]["text"]
    if "R" in enabled or targeted:
        assert state["tasks"]["target"]["depends"] == ["dependency"]
        assert len(state["task_index"]) == 6
    else: assert len(state["tasks"]) == 8
    responses.append(p.wire(state))
    receipt_ids = []
    for i in range(3):
        if "S" in enabled:
            receipt = artifacts.capture("input.txt", {"request": i})
            receipt_ids.append(receipt["artifact"])
            responses.append(p.wire(receipt))
        else:
            dest = root / f"snapshot-{i}.bin"
            shutil.copyfile(root / "input.txt", dest)
            assert dest.read_bytes() == raw
            responses.append(p.wire({"snapshot": dest.name, "bytes": len(raw)}))
    sha = receipt_ids[0] if receipt_ids else None
    if enabled & {"Q", "C"} and sha is None: sha = artifacts.capture("input.txt")["artifact"]
    if "Q" in enabled:
        view = artifacts.search(sha, "ERROR_RARE")
        text = "".join(x["text"] for x in view["matches"])
        assert view["complete"] and view["total_matches"] == 2
        responses.append(p.wire({k: val for k, val in view.items() if k != "matches"}))
    elif targeted:
        with (root / "input.txt").open(encoding="utf-8", newline="") as f:
            text = "".join(line for line in f if "ERROR_RARE" in line)
    else:
        with (root / "input.txt").open(encoding="utf-8", newline="") as f: text = f.read()
    expected = [line for line in raw.decode("utf-8").splitlines(keepends=True) if "ERROR_RARE" in line]
    if "C" in enabled:
        response = p.render(text)
        assert len(response.encode()) <= len(text.encode())
        returned_text = p.expand(json.loads(response)) if response != text else response
    else: response = text; returned_text = text
    answers = [line for line in returned_text.splitlines(keepends=True) if "ERROR_RARE" in line]
    assert answers == expected and len(answers) == 2
    responses.append(response)
    events = [{"id": "r1", "source_kind": "local_log", "source": "synthetic fixture", "task": "target", "model": "fixture", "input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 40}, {"id": "r2", "source_kind": "local_log", "source": "synthetic fixture", "task": "target", "model": "fixture", "input_tokens": 200, "output_tokens": 30, "cached_input_tokens": 100}]
    events += [dict(events[0])]
    if "U" in enabled:
        for event in events: artifacts.record_usage(event)
        report = artifacts.usage()
        assert report["groups"][0]["total_tokens"] == 350 and report["groups"][0]["events"] == 2
        responses.append(p.wire(report))
    else:
        unique = {x["id"]: x for x in events}
        assert sum(x["input_tokens"] + x["output_tokens"] for x in unique.values()) == 350
        responses.append(p.wire(events))
    if "S" in enabled:
        artifacts.restore(sha, "roundtrip.txt")
        assert (root / "roundtrip.txt").read_bytes() == raw
        (root / "roundtrip.txt").unlink()  # one known temporary output, not a recursive removal
    # Full data and ledger remain intact independently of the chosen view.
    assert (root / "input.txt").read_bytes() == raw
    assert len(store.read()["tasks"]) == 8 and len(store.read()["notes"]) == 11
    milliseconds = (time.perf_counter() - start) * 1000
    artifact_files = list(root.glob("snapshot-*.bin"))
    home = root / "work/veronica/artifacts"
    if home.exists(): artifact_files += [x for x in home.rglob("*") if x.is_file()]
    return {"valid": True, "returned_utf8_bytes": sum(len(x.encode("utf-8")) for x in responses), "evidence_hash_calls": hash_calls, "evidence_bytes_hashed": hash_bytes, "artifact_disk_bytes_including_catalog": sum(x.stat().st_size for x in artifact_files), "local_ms": milliseconds, "model_tokens": None, "api_cost": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True); parser.add_argument("--output", default=str(ROOT.parent / "benchmark-results")); parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--skill", default=str(ROOT.parent / "veronica"))
    args = parser.parse_args(); assert args.repeats > 0
    global p, v
    sys.path.insert(0, str(Path(args.skill).resolve() / "scripts"))
    import preserve as p
    import veronica as v
    spec = importlib.util.spec_from_file_location("veronica_baseline", args.baseline); baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)
    conditions = [("baseline-full", set(), False), ("baseline-targeted", set(), True)]
    conditions += [("+".join(group), set(group), False) for n in (1, 2) for group in itertools.combinations(FEATURES, n)]
    conditions += [("+".join(group), set(group), False) for group in [("S", "C", "Q"), ("S", "H", "R"), ("C", "Q", "R"), ("H", "R", "U")]]
    conditions += [("+".join(FEATURES), set(FEATURES), False)]
    conditions += [("adaptive-native", {"H", "R"}, True)]
    records = []
    with tempfile.TemporaryDirectory(prefix="veronica-benchmark-") as name:
        base = Path(name)
        for case in ("repetitive", "unique", "unicode"):
            seed_root = base / ("seed-" + case); raw = seed(seed_root, case)
            for rep in range(args.repeats):
                ordered = conditions if rep % 2 == 0 else list(reversed(conditions))
                for condition, enabled, targeted in ordered:
                    root = base / f"{case}-{rep}-{condition}"
                    shutil.copytree(seed_root, root)
                    measured = workflow(root, enabled, baseline, raw, targeted)
                    records.append({"case": case, "repeat": rep + 1, "condition": condition, "features": sorted(enabled), **measured})
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for case in ("repetitive", "unique", "unicode"):
        control = next(r for r in records if r["case"] == case and r["condition"] == "baseline-full")
        direct = next(r for r in records if r["case"] == case and r["condition"] == "baseline-targeted")
        for condition, enabled, targeted in conditions:
            runs = [r for r in records if r["case"] == case and r["condition"] == condition]
            medians = {key: statistics.median(r[key] for r in runs) for key in ("returned_utf8_bytes", "evidence_hash_calls", "evidence_bytes_hashed", "artifact_disk_bytes_including_catalog", "local_ms")}
            summaries.append({"case": case, "condition": condition, "all_valid": all(r["valid"] for r in runs), **medians, "returned_bytes_reduction_vs_full_pct": 100 * (1 - medians["returned_utf8_bytes"] / control["returned_utf8_bytes"]), "returned_bytes_reduction_vs_targeted_pct": 100 * (1 - medians["returned_utf8_bytes"] / direct["returned_utf8_bytes"])})
    result = {"scope": "Controlled local workflows; no model/API calls or billed token measurements", "features": NAMES, "conditions": len(conditions), "cases": 3, "repeats": args.repeats, "executions": len(records), "all_valid": all(r["valid"] for r in records), "limitations": ["Synthetic fixtures with expected answers and exact recovery, not a general model-quality test", "Full-content comparator measures an inefficient context-delivery pattern; targeted comparator performs native local selection", "Bytes are serialized UTF-8 bytes, not model tokens", "Synthetic usage numbers test accounting only; they are not usage of this benchmark", "Local times include hashing/storage/codec; filesystem cache and tiny samples limit latency conclusions", "Catalog and metadata overhead included in disk/returned-byte metrics; do not add component percentages"], "records": records, "summary": summaries}
    (output / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "benchmark.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0])); writer.writeheader(); writer.writerows(summaries)
    print(json.dumps({k: result[k] for k in ("conditions", "cases", "repeats", "executions", "all_valid")}))


if __name__ == "__main__": main()
