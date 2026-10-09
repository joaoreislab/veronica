"""On-demand logical diagnostics. No agent calls, repairs or background service."""
import json
import math
import re


def validate_state(s, store):
    from veronica import KINDS, identity, require

    def text(value, field):
        require(isinstance(value, str), field + ": texto inválido.")

    def count(value, field):
        require(type(value) is int and value >= 0, field + ": inteiro não negativo esperado.")

    def instant(value, field):
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, field + ": prazo inválido.")

    require(isinstance(s, dict) and s.get("schema") == 1, "Schema incompatível.")
    for field in ("goal", "version", "created"):
        text(s.get(field), field)
    count(s.get("revision"), "revision")
    require(isinstance(s.get("limits"), dict), "limits inválido.")
    for key in ("max_active", "max_attempts", "repeat_failure"):
        count(s["limits"].get(key), "limits." + key)
    require(s["limits"]["max_active"] > 0, "max_active deve ser positivo.")
    require(isinstance(s.get("tasks"), dict) and isinstance(s.get("notes"), list) and
            isinstance(s.get("effects"), dict), "Coleções de estado inválidas.")
    edges, indegrees = {}, {}
    for tid, t in s["tasks"].items():
        identity(tid)
        require(isinstance(t, dict) and t.get("id") == tid, "Identidade de tarefa inconsistente: " + tid)
        for field in ("title", "strategy", "next"):
            text(t.get(field), tid + "." + field)
        require(isinstance(t.get("state"), str) and t["state"] in
            {"todo", "doing", "verify", "done", "blocked", "waiting"}, "Estado inválido: " + tid)
        for field in ("attempts", "repeat"):
            count(t.get(field), tid + "." + field)
        require(type(t.get("breaker")) is bool, "breaker inválido: " + tid)
        deps = t.get("depends")
        require(isinstance(deps, list) and all(isinstance(x, str) and x in s["tasks"] for x in deps) and
            len(set(deps)) == len(deps), "Dependências inválidas: " + tid)
        indegrees[tid] = len(deps)
        for dep in deps:
            edges.setdefault(dep, []).append(tid)
        require(isinstance(t.get("paths"), list), "paths inválido: " + tid)
        for path in t["paths"]:
            store.scope(path)
        criteria = t.get("criteria")
        require(isinstance(criteria, list) and criteria, "Critérios ausentes: " + tid)
        kinds = {}
        for c in criteria:
            require(isinstance(c, dict), "Critério inválido: " + tid)
            cid = identity(c.get("id"))
            require(cid not in kinds and isinstance(c.get("kind"), str) and c["kind"] in KINDS, "Critério duplicado/inválido: " + tid)
            text(c.get("title"), "criterion.title")
            kinds[cid] = c["kind"]
        lease = t.get("lease")
        require(lease is None or isinstance(lease, dict), "Reserva inválida: " + tid)
        if lease is not None:
            for field in ("owner", "token"):
                text(lease.get(field), "lease." + field)
            instant(lease.get("expires"), "lease.expires")
        require(t["state"] not in {"doing", "verify"} or lease is not None, "Tarefa em execução sem reserva: " + tid)
        require(isinstance(t.get("failures"), list) and isinstance(t.get("evidence"), list), "Histórico inválido: " + tid)
        for failure in t["failures"]:
            require(isinstance(failure, dict), "Falha inválida: " + tid)
            for field in ("signature", "reason", "at"):
                text(failure.get(field), "failure." + field)
            count(failure.get("attempt"), "failure.attempt")
        if "dependency_acceptance" in t:
            require(isinstance(t["dependency_acceptance"], dict) and
                set(t["dependency_acceptance"]) == set(deps), "Aceitação de dependência inconsistente: " + tid)
            for value in t["dependency_acceptance"].values():
                require(value is None or isinstance(value, str), "Identificador de aceitação inválido: " + tid)
        if t["state"] == "done":
            text(t.get("acceptance_id"), "acceptance_id")
            require(lease is None, "Tarefa concluída ainda reservada: " + tid)
        for e in t["evidence"]:
            require(isinstance(e, dict) and isinstance(e.get("criterion"), str) and
                e["criterion"] in kinds and e.get("kind") == kinds[e["criterion"]], "Evidência sem critério válido: " + tid)
            for field in ("id", "at", "method", "result", "limitations", "url"):
                text(e.get(field), "evidence." + field)
            count(e.get("attempt"), "evidence.attempt")
            require(0 < e["attempt"] <= t["attempts"], "Tentativa da evidência inválida: " + tid)
            if e.get("expires") is not None:
                instant(e["expires"], "evidence.expires")
            require(isinstance(e.get("files"), list), "Anexos inválidos: " + tid)
            for f in e["files"]:
                require(isinstance(f, dict) and isinstance(f.get("sha256"), str) and
                    re.fullmatch(r"[0-9a-f]{64}", f["sha256"]), "Hash inválido: " + tid)
                path = store.local(f.get("path"))
                require(not path.is_relative_to(store.home), "Anexo dentro do estado Veronica: " + tid)
    queue = [tid for tid, degree in indegrees.items() if degree == 0]
    visited = 0
    while queue:
        tid = queue.pop()
        visited += 1
        for child in edges.get(tid, []):
            indegrees[child] -= 1
            if indegrees[child] == 0:
                queue.append(child)
    require(visited == len(indegrees), "Ciclo de dependências.")
    for note in s["notes"]:
        require(isinstance(note, dict) and isinstance(note.get("kind"), str) and note["kind"] in
            {"decision", "finding", "handoff", "lesson"}, "Nota inválida.")
        text(note.get("text"), "note.text")
        text(note.get("at"), "note.at")
    for key, effect in s["effects"].items():
        identity(key)
        require(isinstance(effect, dict) and isinstance(effect.get("task"), str) and effect["task"] in s["tasks"], "Efeito sem tarefa.")
        require(isinstance(effect.get("state"), str) and effect["state"] in
            {"prepared", "started", "unknown", "confirmed", "not_applied"}, "Estado de efeito inválido.")
        text(effect.get("description"), "effect.description")
        text(effect.get("at"), "effect.at")
        if effect["state"] in {"unknown", "confirmed", "not_applied"}:
            text(effect.get("observation"), "effect.observation")


def diagnose(store, deep=False):
    from veronica import VERSION, VeronicaError, digest
    result = {"ok": True, "version": VERSION, "deep": deep, "issues": []}
    with store.connect() as conn:
        result["sqlite"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        result["events"] = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if result["sqlite"] != "ok":
            result["issues"].append({"kind": "sqlite", "error": result["sqlite"]})
        if deep:
            try:
                state = store.load(conn)
                validate_state(state, store)
                if state["revision"] != result["events"]:
                    result["issues"].append({"kind": "revision_events", "revision": state["revision"], "events": result["events"]})
                for seq, payload in conn.execute("SELECT seq,payload FROM events"):
                    if not isinstance(json.loads(payload), dict):
                        result["issues"].append({"kind": "event_payload", "seq": seq})
                result["logical_state"] = "valid"
            except (VeronicaError, ValueError, KeyError, TypeError) as exc:
                result["logical_state"] = "invalid"
                result["issues"].append({"kind": "logical_state", "error": str(exc)})
    if deep:
        catalog = store.home / "artifacts" / "catalog.sqlite"
        if catalog.exists():
            from preserve import Artifacts
            try:
                result["artifacts"] = Artifacts(store.root, create=False).reconcile()
                if not result["artifacts"]["ok"]:
                    result["issues"].append({"kind": "artifacts", "error": "Inspect artifacts.issues; reconciliation is explicit."})
            except Exception as exc:
                result["issues"].append({"kind": "artifacts", "error": str(exc)})
        marker = store.home / "projecoes.json"
        if marker.is_file():
            try:
                manifest = json.loads(marker.read_text(encoding="utf-8"))
                current = store.read()["revision"]
                if manifest["revision"] != current or set(manifest["files"]) != {"estado.json", "RETOMAR.md", "painel.html"} or any(
                    digest(store.home / name) != sha for name, sha in manifest["files"].items()):
                    result["issues"].append({"kind": "projections", "error": "Stale or partial generation; regenerate dashboard."})
                result["projection_revision"] = manifest["revision"]
            except (OSError, ValueError, KeyError, TypeError, VeronicaError) as exc:
                result["issues"].append({"kind": "projections", "error": str(exc)})
        else:
            result["projections"] = "no_generation_marker"
    result["ok"] = not result["issues"]
    result["product_quality_checked"] = False
    return result
