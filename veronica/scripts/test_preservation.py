"""Behavioral tests for exact preservation, views, reuse, usage and old ledgers."""
import contextlib
import importlib.util
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import preserve as p
import veronica as v


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="veronica-preserve-")
        self.root = Path(self.temp.name)
        self.artifacts = p.Artifacts(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, data, filename="input.txt"):
        (self.root / filename).write_bytes(data)
        return self.artifacts.capture(filename)["artifact"]

    def test_codec_adversarial_and_random_exact_roundtrip(self):
        texts = ["", "x", "\ufefffirst\r\n second\t  \rthird\n", 'null,"",000001,123456789012345678901\n', "🙂漢字é\r\n" * 80, "\n" * 400, "  patch anchor\t \n" * 100, "no newline", "a\u2028b\u2029c\x00"]
        rng = random.Random(8123)
        alphabet = ["x", "é", "🙂", "\n", "\r\n", "\t", " ", '"', "\u2028"]
        texts += ["".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 350))) for _ in range(150)]
        for text in texts:
            with self.subTest(length=len(text)):
                frame = p.compact(text)
                self.assertEqual(p.expand(json.loads(p.wire(frame))).encode("utf-8"), text.encode("utf-8"))
                raw = {"format": "raw", "bytes": len(text.encode()), "sha256": frame["sha256"], "text": text}
                self.assertLessEqual(len(p.wire(frame).encode()), len(p.wire(raw).encode()))

    def test_codec_rejects_corruption_and_oversized_runs(self):
        frame = p.compact("long repeated line\r\n" * 200)
        self.assertEqual(frame["format"], "lines-v1")
        frame["dictionary"][0] += "changed"
        with self.assertRaises(p.PreservationError): p.expand(frame)
        frame = p.compact("x\n" * 500)
        frame["runs"][0][1] = 10**20
        with self.assertRaises(p.PreservationError): p.expand(frame)

    def test_unique_small_text_falls_back_to_raw(self):
        self.assertEqual(p.compact("unique short text")["format"], "raw")
        self.assertEqual(p.render("unique short text"), "unique short text")

    def test_render_never_grows_plain_text_and_preserves_original(self):
        for text in ("", "tiny", "🙂unique\r\n", "long repeated line\r\n" * 300):
            result = p.render(text)
            self.assertLessEqual(len(result.encode()), len(text.encode()))
            if result != text:
                self.assertEqual(p.expand(json.loads(result)), text)

    def test_binary_snapshot_and_restore_are_byte_exact(self):
        raw = bytes(range(256)) * 40
        artifact = self.capture(raw, "binary.dat")
        result = self.artifacts.restore(artifact, "restored.dat")
        self.assertTrue(result["byte_exact"])
        self.assertEqual((self.root / "restored.dat").read_bytes(), raw)
        with self.assertRaises(UnicodeError): self.artifacts.read(artifact)

    def test_same_blob_retains_separate_origins(self):
        artifact = self.capture(b"same data", "a.txt")
        (self.root / "b.txt").write_bytes(b"same data")
        second = self.artifacts.capture("b.txt", {"exit_code": 2})
        self.assertEqual(second["artifact"], artifact)
        self.assertTrue(second["reused_blob"])
        self.assertEqual(len(list(self.artifacts.blobs.glob("*.bin"))), 1)
        with self.artifacts.connect() as conn:
            records = conn.execute("SELECT source,metadata FROM origins ORDER BY id").fetchall()
        self.assertEqual([r[0] for r in records], ["a.txt", "b.txt"])
        self.assertEqual(json.loads(records[1][1]), {"exit_code": 2})

    def test_source_change_never_replaces_old_snapshot(self):
        first = self.capture(b"first\r\n")
        second = self.capture(b"second\n")
        self.assertNotEqual(first, second)
        self.artifacts.restore(first, "old.txt")
        self.assertEqual((self.root / "old.txt").read_bytes(), b"first\r\n")

    def test_blob_corruption_is_rejected(self):
        sha = self.capture(b"proof")
        self.artifacts.path(sha).write_bytes(b"wrong")
        with self.assertRaises(p.PreservationError): self.artifacts.read(sha)
        with self.assertRaises(p.PreservationError): self.artifacts.capture("input.txt")

    def test_read_and_pagination_preserve_unicode_spaces_and_endings(self):
        data = "\ufefffirst\r\n  anchor🙂 \t\rthird\nfourth".encode()
        sha = self.capture(data)
        self.assertEqual(self.artifacts.read(sha)["text"].encode(), data)
        selected = self.artifacts.read(sha, 2, 3)
        self.assertEqual(selected["text"], "  anchor🙂 \t\rthird\n")
        self.assertFalse(selected["complete"])
        self.assertEqual(self.artifacts.read(sha, 20)["text"], "")

    def test_search_complete_pagination_and_literal_semantics(self):
        sha = self.capture(b"error. one\r\nError. two\nerror. three  \nerror. four")
        first = self.artifacts.search(sha, "error.", limit=2)
        second = self.artifacts.search(sha, "error.", offset=first["next_offset"], limit=2)
        all_hits = self.artifacts.search(sha, "error.")
        self.assertEqual(first["total_matches"], 3)
        self.assertEqual(first["matches"] + second["matches"], all_hits["matches"])
        self.assertTrue(all_hits["complete"])
        self.assertIsNone(second["next_offset"])
        self.assertEqual(self.artifacts.search(sha, ".*")["total_matches"], 0)

    def test_paths_and_existing_outputs_are_protected(self):
        sha = self.capture(b"x")
        for destination in ("../escape", "work/veronica/overwrite", "input.txt"):
            with self.assertRaises(p.PreservationError): self.artifacts.restore(sha, destination)
        with self.assertRaises(p.PreservationError): self.artifacts.capture("../escape")
        with self.assertRaises(p.PreservationError): self.artifacts.read("bad-id")

    def test_usage_idempotent_subset_counts_and_unknown_values(self):
        record = {"id": "req", "source_kind": "provider", "source": "fixture usage", "model": "fixture", "input_tokens": 1000, "cached_input_tokens": 600, "cache_write_tokens": 100, "output_tokens": 100, "reasoning_output_tokens": 40}
        self.assertFalse(self.artifacts.record_usage(record)["duplicate_ignored"])
        self.assertTrue(self.artifacts.record_usage(record)["duplicate_ignored"])
        group = self.artifacts.usage()["groups"][0]
        self.assertEqual(group["total_tokens"], 1100)
        self.assertEqual(group["events"], 1)
        with self.assertRaises(p.PreservationError): self.artifacts.record_usage({**record, "output_tokens": 101})
        self.artifacts.record_usage({"id": "partial", "source_kind": "estimate", "source": "fixture estimate", "output_tokens": 10})
        estimate = next(g for g in self.artifacts.usage()["groups"] if g["source_kind"] == "estimate")
        self.assertIsNone(estimate["total_tokens"])
        self.assertIsNone(estimate["input_tokens"])
        self.assertIsNone(self.artifacts.usage()["currency_cost"])

    def test_usage_rejects_overlapping_or_invalid_counts(self):
        base = {"id": "bad", "source_kind": "local_log", "source": "fixture", "input_tokens": 10, "output_tokens": 5}
        for extra in ({"cached_input_tokens": 11}, {"cached_input_tokens": 8, "cache_write_tokens": 4}, {"reasoning_output_tokens": 6}, {"input_tokens": True}, {"output_tokens": -1}):
            with self.subTest(extra=extra), self.assertRaises(p.PreservationError): self.artifacts.record_usage({**base, **extra})

    def test_cli_capture_read_restore_and_error(self):
        self.capture(b"cli\r\n")
        script = Path(p.__file__)
        def call(*args):
            return subprocess.run([sys.executable, "-X", "utf8", str(script), "--workspace", str(self.root), *args], capture_output=True, encoding="utf-8")
        result = call("capture", "--file", "input.txt")
        self.assertEqual(result.returncode, 0, result.stderr)
        sha = json.loads(result.stdout)["artifact"]
        self.assertEqual(json.loads(call("read", "--artifact", sha).stdout)["text"], "cli\r\n")
        self.assertEqual(call("restore", "--artifact", sha, "--output", "cli-restored.txt").returncode, 0)
        self.assertEqual(call("restore", "--artifact", sha, "--output", "cli-restored.txt").returncode, 2)


class LedgerEfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="veronica-context-")
        self.root = Path(self.temp.name)
        self.store = v.Store(self.root)
        self.store.apply({"op": "init", "goal": "Preserve old constraints"})
        (self.root / "proof.txt").write_bytes(b"one proof\r\n" * 100)

    def tearDown(self): self.temp.cleanup()

    def add(self, tid, deps=None):
        self.store.apply({"op": "task.add", "id": tid, "title": tid, "depends": deps or [], "criteria": [{"id": "proof", "kind": "file", "title": "Exact proof"}]})

    def complete(self, tid):
        token = self.store.apply({"op": "task.claim", "id": tid, "owner": "fixture"})["token"]
        self.store.apply({"op": "evidence.add", "id": tid, "token": token, "criterion": "proof", "kind": "file", "files": ["proof.txt"], "method": "Fixture hash", "result": "Fixture exists"})
        self.store.apply({"op": "task.complete", "id": tid, "token": token})

    def test_context_preserves_all_fields_and_old_notes(self):
        self.add("dependency"); self.complete("dependency")
        self.add("target", ["dependency"]); self.add("unrelated")
        for i in range(12): self.store.apply({"op": "note", "kind": "decision", "text": f"constraint-{i}"})
        view = self.store.context("target")
        self.assertEqual(set(view["tasks"]), {"target", "dependency"})
        self.assertEqual(len(view["notes"]), 12)
        self.assertEqual(view["task_index"][0]["id"], "unrelated")
        self.assertFalse(view["complete_project_view"])
        full = self.store.context()
        self.assertEqual(full, self.store.status())
        self.assertEqual(json.loads(p.expand(self.store.context(compact_output=True))), full)
        self.assertIn("constraint-0", self.store.resume(full=True))
        self.assertNotIn("constraint-0", self.store.resume())

    def test_hash_reuse_is_per_call_and_changes_still_invalidate(self):
        for i in range(6): self.add(f"t{i}"); self.complete(f"t{i}")
        with patch.object(v, "digest", wraps=v.digest) as spy:
            self.assertTrue(self.store.status()["all_accepted"])
            self.assertEqual(spy.call_count, 1)
            self.assertTrue(self.store.status()["all_accepted"])
            self.assertEqual(spy.call_count, 2)
        (self.root / "proof.txt").write_bytes(b"changed")
        self.assertFalse(self.store.status()["all_accepted"])
        self.assertTrue(all(t["effective_state"] == "stale" for t in self.store.status()["tasks"].values()))

    def test_default_attempts_do_not_stop_after_three_failures(self):
        self.add("a")
        for _ in range(8):
            token = self.store.apply({"op": "task.claim", "id": "a", "owner": "fixture"})["token"]
            self.store.apply({"op": "task.fail", "id": "a", "token": token, "signature": "fixture", "reason": "Observed failure", "next": "Try another approach"})
        state = self.store.status()
        self.assertFalse(state["tasks"]["a"]["breaker"])
        self.assertTrue(state["tasks"]["a"]["ready"])
        self.assertEqual(len(state["tasks"]["a"]["failures"]), 8)

    def test_publish_checks_once_and_next_publish_detects_changes(self):
        self.add("a"); self.complete("a")
        with patch.object(self.store, "status", wraps=self.store.status) as spy:
            self.store.publish()
            self.assertEqual(spy.call_count, 1)
        saved = json.loads((self.store.home / "estado.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["all_accepted"])
        (self.root / "proof.txt").write_bytes(b"changed after snapshot")
        self.store.publish()
        saved = json.loads((self.store.home / "estado.json").read_text(encoding="utf-8"))
        self.assertFalse(saved["all_accepted"])
        self.assertIn("Rever evidências", (self.store.home / "painel.html").read_text(encoding="utf-8"))

    def test_existing_version_and_explicit_limits_are_preserved(self):
        with self.store.connect(write=True) as conn:
            state = self.store.load(conn); state["version"] = "1.0.0"; state["limits"].update(max_attempts=3, repeat_failure=2)
            conn.execute("UPDATE project SET state=?", (json.dumps(state),))
        self.add("a")
        self.assertEqual(self.store.read()["version"], v.VERSION)
        self.assertEqual(self.store.read()["limits"]["max_attempts"], 3)
        self.assertEqual(self.store.read()["limits"]["repeat_failure"], 2)

    def test_context_cli_is_complete_and_lease_tokens_are_not_exported(self):
        self.add("a")
        token = self.store.apply({"op": "task.claim", "id": "a", "owner": "fixture"})["token"]
        result = subprocess.run([sys.executable, "-X", "utf8", v.__file__, "--workspace", str(self.root), "context", "--compact"], capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        expanded = p.expand(json.loads(result.stdout))
        self.assertNotIn(token, expanded)
        self.assertEqual(json.loads(expanded)["tasks"]["a"]["state"], "doing")


if __name__ == "__main__": unittest.main(verbosity=2)
