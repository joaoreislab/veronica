"""Fault boundaries, concurrency, deep diagnostics and real recovery round trips."""
import concurrent.futures
import contextlib
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import health
import preserve as p
import recovery
import veronica as v


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="veronica-robust-")
        self.root = Path(self.temp.name)
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        self.store = v.Store(self.workspace)
        self.store.apply({"op": "init", "goal": "Recovery fixture"})
        self.artifacts = p.Artifacts(self.workspace)
        self.product = self.workspace / "product.bin"
        self.product.write_bytes(bytes(range(256)) + "🙂\r\n original  \t".encode())

    def tearDown(self):
        self.temp.cleanup()

    def add(self, tid="a", depends=(), **extra):
        return self.store.apply({"op": "task.add", "id": tid, "title": tid,
            "depends": list(depends), "criteria": [{"id": "proof", "title": "Product exists", "kind": "file"}], **extra})

    def claim(self, tid="a"):
        return self.store.apply({"op": "task.claim", "id": tid, "owner": "fixture"})["token"]

    def prove(self, token, tid="a", **extra):
        return self.store.apply({"op": "evidence.add", "id": tid, "token": token,
            "criterion": "proof", "kind": "file", "files": ["product.bin"], "method": "Fixture check", "result": "Observed fixture", **extra})

    def snapshot(self):
        with self.store.connect() as conn:
            return self.store.load(conn), conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def inject_state(self, state):
        with self.store.connect(write=True) as conn:
            conn.execute("UPDATE project SET state=?", (json.dumps(state),))

    def usage_record(self, **extra):
        return {"id": "request", "source_kind": "provider", "source": "synthetic test only",
                "model": "fixture", "input_tokens": 10, "output_tokens": 2, **extra}

    def test_next_invalid_types_roll_back_before_projection(self):
        before = self.snapshot()
        for value in ({"step": "x"}, [], None, True, 5):
            with self.subTest(value=value), self.assertRaises(v.VeronicaError):
                self.add(next=value)
            self.assertEqual(self.snapshot(), before)
        self.add(next="")
        self.assertIn("a:", self.store.resume())

    def test_optional_evidence_fields_reject_invalid_values_atomically(self):
        self.add(); token = self.claim()
        before = self.snapshot()
        for extra in ({"limitations": {}}, {"url": []}):
            with self.assertRaises(v.VeronicaError): self.prove(token, **extra)
            self.assertEqual(self.snapshot(), before)

    def test_usage_group_identity_is_validated(self):
        for field in ("model", "task", "source_kind"):
            for value in ([], {}, True, 4):
                with self.subTest(field=field, value=value), self.assertRaises(p.PreservationError):
                    self.artifacts.record_usage(self.usage_record(**{field: value}))
        self.assertEqual(self.artifacts.usage()["records"], [])

    def test_bad_legacy_usage_is_preserved_and_is_not_counted_as_complete(self):
        self.artifacts.record_usage(self.usage_record())
        legacy = self.usage_record(id="old", model=[])
        with self.artifacts.connect(write=True) as conn:
            conn.execute("INSERT INTO usage VALUES(?,?)", (legacy["id"], p.wire(legacy)))
        result = self.artifacts.usage()
        self.assertFalse(result["complete"])
        self.assertEqual(result["groups"][0]["total_tokens"], 12)
        self.assertEqual(json.loads(result["invalid_records"][0]["stored_json"]), legacy)
        self.assertFalse(self.artifacts.reconcile()["ok"])

    def test_interrupted_restore_leaves_no_partial_destination_and_can_retry(self):
        sha = self.artifacts.capture("product.bin")["artifact"]
        def interrupted(source, destination, *args):
            destination.write(source.read(3))
            raise OSError("Injected copy interruption")
        with patch.object(p.shutil, "copyfileobj", interrupted), self.assertRaises(OSError):
            self.artifacts.restore(sha, "retry.bin")
        self.assertFalse((self.workspace / "retry.bin").exists())
        self.assertEqual(list(self.workspace.glob(".veronica-restore-*.tmp")), [])
        self.artifacts.restore(sha, "retry.bin")
        self.assertEqual((self.workspace / "retry.bin").read_bytes(), self.product.read_bytes())

    def test_restore_does_not_replace_destination_created_during_copy(self):
        sha = self.artifacts.capture("product.bin")["artifact"]
        original = p.os.link
        def race(source, destination):
            Path(destination).write_bytes(b"another writer")
            return original(source, destination)
        with patch.object(p.os, "link", race), self.assertRaises(FileExistsError):
            self.artifacts.restore(sha, "raced.bin")
        self.assertEqual((self.workspace / "raced.bin").read_bytes(), b"another writer")

    def test_restore_rejects_wrong_temporary_bytes_before_promotion(self):
        sha = self.artifacts.capture("product.bin")["artifact"]
        with patch.object(p.shutil, "copyfileobj", lambda src, dst, *args: dst.write(b"wrong")), self.assertRaises(p.PreservationError):
            self.artifacts.restore(sha, "wrong.bin")
        self.assertFalse((self.workspace / "wrong.bin").exists())

    def test_two_real_processes_record_same_usage_without_duplicate_or_error(self):
        payload = self.workspace / "usage.json"
        payload.write_text(p.wire(self.usage_record()), encoding="utf-8")
        args = [sys.executable, "-X", "utf8", p.__file__, "--workspace", str(self.workspace), "usage-record", "--input", str(payload)]
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: subprocess.run(args, capture_output=True, encoding="utf-8", timeout=20), range(2)))
        self.assertEqual([x.returncode for x in results], [0, 0], [x.stderr for x in results])
        self.assertEqual(sorted(json.loads(x.stdout)["duplicate_ignored"] for x in results), [False, True])
        self.assertEqual(self.artifacts.usage()["groups"][0]["events"], 1)

    def test_concurrent_conflicting_usage_is_rejected_without_double_count(self):
        def submit(tokens):
            try: return self.artifacts.record_usage(self.usage_record(output_tokens=tokens))
            except p.PreservationError: return "conflict"
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(submit, (2, 3)))
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(len(self.artifacts.usage()["records"]), 1)

    def test_capture_commit_failure_reconciles_receipt_exactly_once(self):
        original = self.artifacts.connect
        @contextlib.contextmanager
        def failed_commit(write=False):
            with original(write=write) as conn:
                yield conn
                if write: raise sqlite3.OperationalError("Injected commit failure")
        with patch.object(self.artifacts, "connect", failed_commit), self.assertRaises(sqlite3.OperationalError):
            self.artifacts.capture("product.bin", {"origin": "fixture"})
        report = self.artifacts.reconcile()
        self.assertFalse(report["ok"])
        self.assertIn("pending_receipt", {i["kind"] for i in report["issues"]})
        repaired = self.artifacts.reconcile(repair=True)
        self.assertTrue(repaired["ok"], repaired)
        self.assertEqual(len(repaired["repaired_receipts"]), 1)
        self.assertEqual(self.artifacts.reconcile(repair=True)["repaired_receipts"], [])
        with self.artifacts.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM origins").fetchone()[0], 1)
        self.assertEqual(self.product.read_bytes(), bytes(range(256)) + "🙂\r\n original  \t".encode())

    def test_reconciliation_does_not_invent_origin_for_old_orphan(self):
        sha = p.sha_file(self.product)
        (self.artifacts.blobs / (sha + ".bin")).write_bytes(self.product.read_bytes())
        result = self.artifacts.reconcile(repair=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["issues"][0]["origin_unknown"])
        self.assertTrue((self.artifacts.blobs / (sha + ".bin")).exists())

    def test_reconciliation_detects_corrupt_blob_and_receipt(self):
        sha = self.artifacts.capture("product.bin")["artifact"]
        (self.artifacts.blobs / (sha + ".bin")).write_bytes(b"corruption")
        (self.artifacts.receipts / "invalid.json").write_text("{", encoding="utf-8")
        result = self.artifacts.reconcile(repair=True)
        self.assertFalse(result["ok"])
        self.assertIn("corrupt_blob", {x["kind"] for x in result["issues"]})
        self.assertEqual(result["deleted_files"], 0)

    def test_publish_serializes_with_later_writer_and_does_not_regress(self):
        self.store.publish()
        started, release, later_done = threading.Event(), threading.Event(), threading.Event()
        original = v.atomic_text
        first_thread = None
        def paused(path, text):
            if threading.current_thread() is first_thread and path.name == "estado.json":
                started.set()
                if not release.wait(10): raise RuntimeError("Test barrier timeout")
            return original(path, text)
        errors = []
        def first():
            try: self.store.publish()
            except Exception as exc: errors.append(exc)
        def later():
            try:
                other = v.Store(self.workspace)
                other.apply({"op": "note", "text": "newest"})
                other.publish()
                later_done.set()
            except Exception as exc: errors.append(exc)
        first_thread = threading.Thread(target=first)
        later_thread = threading.Thread(target=later)
        with patch.object(v, "atomic_text", paused):
            first_thread.start()
            self.assertTrue(started.wait(5))
            later_thread.start()
            try: self.assertFalse(later_done.wait(.15))
            finally: release.set()
            first_thread.join(15); later_thread.join(15)
        self.assertFalse(first_thread.is_alive() or later_thread.is_alive())
        self.assertEqual(errors, [])
        saved = json.loads((self.store.home / "estado.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["revision"], self.store.read()["revision"])
        self.assertEqual(saved["notes"][-1]["text"], "newest")
        self.assertTrue(health.diagnose(self.store, True)["ok"])

    def test_partial_projection_is_detected_and_regenerated_without_ledger_loss(self):
        self.store.publish()
        self.store.apply({"op": "note", "text": "retained in ledger"})
        original = v.atomic_text
        def fail(path, text):
            if path.name == "RETOMAR.md": raise OSError("Injected projection interruption")
            return original(path, text)
        with patch.object(v, "atomic_text", fail), self.assertRaises(OSError): self.store.publish()
        self.assertIn("projections", {x["kind"] for x in health.diagnose(self.store, True)["issues"]})
        self.assertEqual(self.store.read()["notes"][-1]["text"], "retained in ledger")
        self.store.publish()
        self.assertTrue(health.diagnose(self.store, True)["ok"])

    def test_deep_dependency_context_and_acceptance_are_iterative(self):
        self.add()
        token = self.claim(); self.prove(token)
        self.store.apply({"op": "task.complete", "id": "a", "token": token})
        state = self.store.read(); prototype = copy.deepcopy(state["tasks"]["a"])
        previous = "a"
        for i in range(1200):
            tid = f"deep{i}"
            task = copy.deepcopy(prototype)
            task.update(id=tid, title=tid, depends=[previous], acceptance_id=tid,
                dependency_acceptance={previous: state["tasks"][previous]["acceptance_id"]})
            state["tasks"][tid] = task
            previous = tid
        self.inject_state(state)
        view = self.store.context(previous)
        self.assertEqual(len(view["tasks"]), 1201)
        self.assertTrue(view["all_accepted"])
        health.validate_state(state, self.store)

    def test_index_pages_reassemble_complete_index_and_retain_old_constraints(self):
        self.add("selected")
        for i in range(12): self.add(f"other{i}")
        self.store.apply({"op": "note", "kind": "decision", "text": "Old decisive constraint"})
        full = self.store.context("selected")
        combined, offset = [], 0
        while True:
            page = self.store.context("selected", index_offset=offset, index_limit=3)
            self.assertEqual(page["tasks"], full["tasks"])
            self.assertEqual(page["notes"], full["notes"])
            combined += page["task_index"]
            offset = page["task_index_page"]["next_offset"]
            if offset is None: break
        self.assertEqual(combined, full["task_index"])
        with self.assertRaises(v.VeronicaError): self.store.context(index_limit=3)

    def test_deep_doctor_rejects_logically_invalid_but_integral_sqlite(self):
        self.inject_state({})
        self.assertTrue(health.diagnose(self.store)["ok"])
        result = health.diagnose(self.store, True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["logical_state"], "invalid")

    def test_deep_doctor_detects_cycles_and_bad_field_types(self):
        self.add()
        state = self.store.read()
        for alteration in (lambda s: s["tasks"]["a"].update(next={}),
                           lambda s: s["tasks"]["a"].update(depends=["a"]),
                           lambda s: s.update(notes=[{"kind": "decision", "text": []}])):
            bad = copy.deepcopy(state); alteration(bad); self.inject_state(bad)
            self.assertFalse(health.diagnose(self.store, True)["ok"])

    def test_deep_doctor_is_read_only_and_does_not_create_artifacts(self):
        self.store.publish()
        before = {x: p.sha_file(x) for x in self.store.home.rglob("*") if x.is_file()}
        self.assertTrue(health.diagnose(self.store, True)["ok"])
        self.assertEqual(before, {x: p.sha_file(x) for x in self.store.home.rglob("*") if x.is_file()})

    def test_bundle_restores_product_artifacts_usage_leases_and_unknown_effects(self):
        self.add(); token = self.claim(); self.prove(token)
        self.store.apply({"op": "effect.prepare", "id": "a", "token": token, "key": "external", "description": "Synthetic external effect; no call made"})
        self.store.apply({"op": "effect.start", "key": "external", "token": token})
        self.artifacts.capture("product.bin", {"origin": "fixture"})
        self.artifacts.record_usage(self.usage_record())
        (self.workspace / "unselected.txt").write_text("not selected", encoding="utf-8")
        result = recovery.bundle(self.workspace, "bundle", ["product.bin"])
        destination = self.root / "restored"
        recovery.restore(result["bundle"], destination)
        restored = v.Store(destination)
        self.assertEqual((destination / "product.bin").read_bytes(), self.product.read_bytes())
        self.assertFalse((destination / "unselected.txt").exists())
        state = restored.status()
        self.assertEqual(state["tasks"]["a"]["effective_state"], "interrupted")
        self.assertFalse(state["tasks"]["a"]["ready"])
        self.assertEqual(state["effects"]["external"]["state"], "started")
        self.assertEqual(p.Artifacts(destination, create=False).usage()["records"], self.artifacts.usage()["records"])
        self.assertTrue(health.diagnose(restored, True)["ok"])
        self.assertEqual(recovery.verify(result["bundle"])["revision"], self.store.read()["revision"])

    def test_bundle_restore_resumes_accepted_evidence_in_new_process(self):
        self.add(); token = self.claim(); self.prove(token)
        self.store.apply({"op": "task.complete", "id": "a", "token": token})
        result = recovery.bundle(self.workspace, "bundle", ["product.bin"])
        destination = self.root / "fresh"
        run = subprocess.run([sys.executable, "-X", "utf8", recovery.__file__, "restore", "--bundle", result["bundle"],
            "--workspace", str(destination)], capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run([sys.executable, "-X", "utf8", v.__file__, "--workspace", str(destination), "status"],
            capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["all_accepted"])

    def test_bundle_corruption_rejects_restore_before_creating_destination(self):
        result = recovery.bundle(self.workspace, "bundle", ["product.bin"])
        (Path(result["bundle"]) / "product.bin").write_bytes(b"changed")
        destination = self.root / "refused"
        with self.assertRaises(v.VeronicaError): recovery.restore(result["bundle"], destination)
        self.assertFalse(destination.exists())

    def test_bundle_paths_and_existing_destinations_are_protected(self):
        for output, includes in (("../escape", []), ("work/veronica/backup", []), ("bundle", ["."]), ("bundle", ["../escape"])):
            with self.subTest(output=output, includes=includes), self.assertRaises(v.VeronicaError):
                recovery.bundle(self.workspace, output, includes)
        result = recovery.bundle(self.workspace, "bundle")
        with self.assertRaises(v.VeronicaError): recovery.bundle(self.workspace, "bundle")
        with self.assertRaises(v.VeronicaError): recovery.restore(result["bundle"], self.workspace)

    def test_bundle_without_product_reports_scope_and_keeps_missing_evidence_stale(self):
        self.add(); token = self.claim(); self.prove(token)
        self.store.apply({"op": "task.complete", "id": "a", "token": token})
        result = recovery.bundle(self.workspace, "bundle")
        manifest = recovery.verify(result["bundle"])
        self.assertFalse(manifest["unselected_product_files_included"])
        destination = self.root / "state-only"
        recovery.restore(result["bundle"], destination)
        self.assertEqual(v.Store(destination).status()["tasks"]["a"]["effective_state"], "stale")

    def test_bundle_refuses_unreconciled_artifacts(self):
        sha = p.sha_file(self.product)
        (self.artifacts.blobs / (sha + ".bin")).write_bytes(self.product.read_bytes())
        with self.assertRaises(v.VeronicaError): recovery.bundle(self.workspace, "refused")
        self.assertFalse((self.workspace / "refused").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
