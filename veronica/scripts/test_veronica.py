"""Behavioral invariants. Run with Python, using isolated temporary workspaces."""
import importlib.util
import contextlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).with_name("veronica.py")
spec = importlib.util.spec_from_file_location("veronica", HELPER)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="veronica-test-")
        self.root = Path(self.temp.name)
        self.store = v.Store(self.root)
        self.store.apply({"op": "init", "goal": "Verificar invariantes"})
        self.file = self.root / "produto.txt"
        self.file.write_text("versão 1", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def add(self, tid="a", deps=None, paths=None, kind="file"):
        self.store.apply({"op": "task.add", "id": tid, "title": tid,
            "depends": deps or [], "paths": paths or [],
            "criteria": [{"id": "ok", "title": "Entrega observada", "kind": kind}]})

    def claim(self, tid="a", seconds=1800):
        return self.store.apply({"op": "task.claim", "id": tid, "owner": "teste", "seconds": seconds})["token"]

    def prove(self, token, tid="a", kind="file", **extra):
        return self.store.apply({"op": "evidence.add", "id": tid, "token": token,
            "criterion": "ok", "kind": kind, "method": "Conferência da fixture",
            "result": "Fixture corresponde ao esperado", "files": ["produto.txt"], **extra})

    def finish(self, token, tid="a"):
        return self.store.apply({"op": "task.complete", "id": tid, "token": token})

    def test_completion_requires_evidence_and_kind(self):
        self.add()
        token = self.claim()
        with self.assertRaises(v.VeronicaError):
            self.finish(token)
        with self.assertRaises(v.VeronicaError):
            self.prove(token, kind="runtime")
        self.prove(token)
        self.finish(token)
        self.assertTrue(self.store.status()["all_accepted"])

    def test_missing_or_changed_file_invalidates_done(self):
        self.add()
        token = self.claim()
        self.prove(token)
        self.finish(token)
        self.file.write_text("versão 2", encoding="utf-8")
        self.assertEqual(self.store.status()["tasks"]["a"]["effective_state"], "stale")
        self.file.unlink()
        self.assertFalse(self.store.status()["all_accepted"])

    def test_dependency_reacceptance_does_not_restore_old_downstream(self):
        self.add("a")
        self.add("b", ["a"])
        with self.assertRaises(v.VeronicaError):
            self.claim("b")
        token = self.claim()
        self.prove(token)
        self.finish(token)
        bt = self.claim("b")
        self.prove(bt, "b")
        self.finish(bt, "b")
        self.file.write_text("mudança", encoding="utf-8")
        at = self.claim("a")
        self.prove(at)
        self.finish(at)
        self.assertFalse(self.store.status()["tasks"]["b"]["accepted_current"])

    def test_expiry_and_fencing(self):
        self.add()
        with patch.object(v.time, "time", return_value=1000):
            old = self.claim(seconds=10)
            self.prove(old)
        with patch.object(v.time, "time", return_value=1011):
            self.assertEqual(self.store.status()["tasks"]["a"]["effective_state"], "interrupted")
            new = self.claim()
            with self.assertRaises(v.VeronicaError):
                self.finish(old)
            with self.assertRaises(v.VeronicaError):
                self.finish(new)
            self.prove(new)
            self.finish(new)

    def test_source_expiry(self):
        self.add(kind="source")
        with patch.object(v.time, "time", return_value=2000):
            token = self.claim()
            self.prove(token, kind="source", url="https://example.org/source", ttl_hours=0.001)
            self.finish(token)
        with patch.object(v.time, "time", return_value=2004):
            self.assertFalse(self.store.status()["all_accepted"])

    def test_write_overlap_and_concurrency_limit(self):
        self.add("a", paths=["src"])
        self.add("b", paths=["src/arquivo.py"])
        self.add("c", paths=["documentos"])
        self.add("d")
        self.claim("a")
        with self.assertRaises(v.VeronicaError):
            self.claim("b")
        self.claim("c")
        with self.assertRaises(v.VeronicaError):
            self.claim("d")

    def test_failure_breaker_and_attempt_budget(self):
        self.store.apply({"op": "limits", "reason": "Fixture with explicit user limits", "limits": {"max_attempts": 3, "repeat_failure": 2}})
        self.add()
        for _ in range(2):
            token = self.claim()
            self.store.apply({"op": "task.fail", "id": "a", "token": token,
                "signature": "mesmo", "reason": "falha observada", "next": "investigar"})
        with self.assertRaises(v.VeronicaError):
            self.claim()
        self.store.apply({"op": "task.strategy", "id": "a", "strategy": "alternativa", "reason": "Diagnóstico aponta outra via"})
        token = self.claim()
        self.store.apply({"op": "task.release", "id": "a", "token": token, "next": "nova tentativa"})
        with self.assertRaises(v.VeronicaError):
            self.claim()

    def test_ambiguous_effect_requires_reconciliation(self):
        self.add()
        token = self.claim()
        self.store.apply({"op": "effect.prepare", "id": "a", "token": token,
            "key": "acao", "description": "Efeito simulado, nenhuma API"})
        self.store.apply({"op": "effect.start", "key": "acao", "token": token})
        self.prove(token)
        with self.assertRaises(v.VeronicaError):
            self.finish(token)
        self.store.apply({"op": "task.release", "id": "a", "token": token, "next": "Consultar destino"})
        with self.assertRaises(v.VeronicaError):
            self.claim()
        self.store.apply({"op": "effect.resolve", "key": "acao", "state": "not_applied", "observation": "Destino simulado confirmou ausência"})
        new = self.claim()
        self.prove(new)
        self.finish(new)
        self.assertTrue(self.store.status()["all_accepted"])

    def test_rejected_operation_rolls_back_event_and_state(self):
        before = self.store.read()["revision"]
        with self.assertRaises(v.VeronicaError):
            self.store.apply({"op": "init", "goal": "substituir"})
        self.assertEqual(self.store.read()["revision"], before)
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)

    def test_paths_are_confined_and_state_is_not_evidence(self):
        with self.assertRaises(v.VeronicaError):
            self.add(paths=["../fora"])
        self.add()
        token = self.claim()
        with self.assertRaises(v.VeronicaError):
            self.store.apply({"op": "evidence.add", "id": "a", "token": token,
                "criterion": "ok", "kind": "file", "files": ["work/veronica/veronica.db"],
                "method": "arquivo", "result": "existe"})

    def test_checkpoint_and_resume_from_new_process(self):
        self.add()
        token = self.claim()
        self.store.apply({"op": "task.next", "id": "a", "token": token, "next": "Conferir linha pendente"})
        cp = self.store.checkpoint("Interrupção simulada")
        db = Path(cp["checkpoint"]) / "veronica.db"
        with contextlib.closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(v.Store.load(conn)["revision"], self.store.read()["revision"])
        resumed = subprocess.run([sys.executable, "-X", "utf8", str(HELPER), "--workspace", str(self.root), "resume"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn("Conferir linha pendente", resumed.stdout)
        self.assertNotIn(token, resumed.stdout)
        self.assertNotIn(token, json.dumps(self.store.status()))

    def test_two_real_processes_cannot_claim_same_task(self):
        self.add()
        paths = []
        for index in range(2):
            path = self.root / f"claim-{index}.json"
            path.write_text(json.dumps({"op": "task.claim", "id": "a", "owner": f"processo {index}"}), encoding="utf-8")
            paths.append(path)
        processes = [subprocess.Popen([sys.executable, "-X", "utf8", str(HELPER), "--workspace", str(self.root), "apply", "--input", str(p)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for p in paths]
        for process in processes:
            process.communicate(timeout=30)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2])
        self.assertEqual(self.store.read()["tasks"]["a"]["attempts"], 1)

    def test_waiting_requires_explicit_unblock(self):
        self.add()
        token = self.claim()
        self.store.apply({"op": "task.release", "id": "a", "token": token, "state": "waiting", "next": "Aguardar dado"})
        with self.assertRaises(v.VeronicaError):
            self.claim()
        self.store.apply({"op": "task.unblock", "id": "a", "reason": "Dado recebido"})
        self.claim()

    def test_dashboard_escapes_user_text(self):
        self.store.apply({"op": "note", "text": "<script>texto</script>"})
        text = Path(self.store.publish()).read_text(encoding="utf-8")
        self.assertNotIn("<script>texto</script>", text)
        self.assertIn("&lt;script&gt;", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
