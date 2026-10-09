#!/usr/bin/env python3
"""Veronica 1.0: cooperative local work ledger. Standard library only.
No commands, network calls, agents, or external effects are executed here.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time
import uuid

VERSION = "1.0.0"
KINDS = {"file", "runtime", "source", "human"}
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


class VeronicaError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise VeronicaError(message)


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def label(value, field, limit=4000):
    require(isinstance(value, str) and value.strip() and len(value) <= limit,
            f"{field}: texto não vazio de até {limit} caracteres.")
    return value.strip()


def identity(value):
    require(isinstance(value, str) and ID_RE.fullmatch(value), "ID inválido.")
    return value


def number(value, field, minimum=1, maximum=100000):
    require(type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum,
            f"{field}: número entre {minimum} e {maximum}.")
    return value


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, workspace):
        self.root = Path(workspace).resolve()
        require(self.root.is_dir(), "Workspace inexistente.")
        self.home = self.root / "work" / "veronica"
        self.db = self.home / "veronica.db"

    def local(self, raw):
        path = (self.root / label(raw, "path")).resolve()
        require(path.is_relative_to(self.root), "Caminho fora do workspace.")
        return path

    def scope(self, raw):
        path = self.local(raw)
        require(not (path == self.home or self.home.is_relative_to(path) or path.is_relative_to(self.home)),
                "Reserve arquivos do produto, não o estado Veronica ou o workspace inteiro.")
        return str(path.relative_to(self.root)).replace("\\", "/")

    @contextlib.contextmanager
    def connect(self, create=False, write=False):
        if create:
            self.home.mkdir(parents=True, exist_ok=True)
        require(create or self.db.is_file(), "Projeto Veronica não inicializado.")
        conn = sqlite3.connect(str(self.db) if create else self.db.as_uri() + "?mode=rw", uri=not create, timeout=15)
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def read(self):
        with self.connect() as conn:
            return self.load(conn)

    @staticmethod
    def load(conn):
        row = conn.execute("SELECT state FROM project WHERE id=1").fetchone()
        require(row is not None, "Estado ausente.")
        state = json.loads(row[0])
        require(state.get("schema") == 1, "Schema incompatível. Preserve o banco.")
        return state

    def apply(self, p):
        require(isinstance(p, dict), "Comando deve ser objeto JSON.")
        op = p.get("op")
        require(isinstance(op, str), "Campo op ausente.")
        with self.connect(create=op == "init", write=True) as conn:
            if op == "init":
                conn.execute("CREATE TABLE IF NOT EXISTS project(id INTEGER PRIMARY KEY, state TEXT NOT NULL)")
                conn.execute("CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, op TEXT NOT NULL, payload TEXT NOT NULL)")
                require(conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 0,
                        "Projeto já existe. Use resume; init não sobrescreve.")
                s = {"schema": 1, "version": VERSION, "revision": 0, "goal": label(p.get("goal"), "goal"),
                     "created": stamp(), "limits": {"max_active": 2, "max_attempts": 3, "repeat_failure": 2},
                     "tasks": {}, "notes": [], "effects": {}}
                self.limits(s, p.get("limits", {}))
                conn.execute("INSERT INTO project VALUES(1,?)", (json.dumps(s),))
                result = {"initialized": True}
            else:
                s = self.load(conn)
                result = self.dispatch(s, p)
            s["revision"] += 1
            s["updated"] = stamp()
            conn.execute("UPDATE project SET state=? WHERE id=1", (json.dumps(s, ensure_ascii=False),))
            safe = {k: v for k, v in p.items() if k != "token"}
            conn.execute("INSERT INTO events(at,op,payload) VALUES(?,?,?)",
                         (stamp(), op, json.dumps(safe, ensure_ascii=False)))
        return {"ok": True, "revision": s["revision"], **result}

    @staticmethod
    def limits(s, values):
        require(isinstance(values, dict) and not (set(values) - set(s["limits"])), "Limite desconhecido.")
        for key, value in values.items():
            require(type(value) is int, "Limites exigem inteiros.")
            s["limits"][key] = number(value, key, maximum=1000)

    @staticmethod
    def task(s, p):
        task = s["tasks"].get(p.get("id"))
        require(task is not None, "Tarefa inexistente.")
        return task

    @staticmethod
    def owned(t, p):
        lease = t.get("lease")
        require(lease and lease["expires"] > time.time() and
                secrets.compare_digest(str(lease["token"]), str(p.get("token", ""))),
                "Reserva ausente, expirada ou token incorreto. Reivindique novamente.")

    def evidence_valid(self, e, t):
        if e["attempt"] != t["attempts"]:
            return False, "tentativa anterior"
        if e.get("expires") and e["expires"] <= time.time():
            return False, "prazo vencido"
        for file in e["files"]:
            try:
                if digest(self.local(file["path"])) != file["sha256"]:
                    return False, "arquivo mudou: " + file["path"]
            except (OSError, VeronicaError):
                return False, "arquivo ausente ou inacessível: " + file["path"]
        return True, "atual"

    def coverage(self, t):
        return [c["id"] for c in t["criteria"] if not any(e["criterion"] == c["id"] and
                e["kind"] == c["kind"] and self.evidence_valid(e, t)[0] for e in t["evidence"])]

    def accepted(self, s, tid, memo=None):
        memo = {} if memo is None else memo
        if tid not in memo:
            t = s["tasks"][tid]
            memo[tid] = t["state"] == "done" and not self.coverage(t) and all(
                self.accepted(s, dep, memo) and t.get("dependency_acceptance", {}).get(dep) ==
                s["tasks"][dep].get("acceptance_id") for dep in t["depends"])
        return memo[tid]

    def deps_ready(self, s, t):
        return all(self.accepted(s, dep) for dep in t["depends"])

    def overlap(self, a, b):
        left, right = self.local(a), self.local(b)
        return left == right or left.is_relative_to(right) or right.is_relative_to(left)

    @staticmethod
    def unresolved(s, tid):
        return any(e["task"] == tid and e["state"] in {"started", "unknown"} for e in s["effects"].values())

    def dispatch(self, s, p):
        op = p["op"]
        if op == "task.add":
            tid = identity(p.get("id"))
            require(tid not in s["tasks"], "ID já existe.")
            deps = p.get("depends", [])
            require(isinstance(deps, list) and all(isinstance(d, str) for d in deps) and len(set(deps)) == len(deps) and
                    all(d in s["tasks"] for d in deps), "Dependências devem existir e ser únicas.")
            criteria = p.get("criteria")
            require(isinstance(criteria, list) and criteria, "Defina ao menos um critério observável.")
            cleaned = []
            for c in criteria:
                require(isinstance(c, dict) and c.get("kind") in KINDS, "Tipo de critério inválido.")
                cleaned.append({"id": identity(c.get("id")), "title": label(c.get("title"), "criterion.title"), "kind": c["kind"]})
            require(len({c["id"] for c in cleaned}) == len(cleaned), "Critério duplicado.")
            paths = p.get("paths", [])
            require(isinstance(paths, list), "paths exige lista.")
            s["tasks"][tid] = {"id": tid, "title": label(p.get("title"), "title"),
                "depends": deps, "paths": [self.scope(x) for x in paths], "criteria": cleaned,
                "state": "todo", "attempts": 0, "evidence": [], "failures": [],
                "strategy": label(p.get("strategy", "direta"), "strategy"), "next": p.get("next", ""),
                "lease": None, "repeat": 0, "breaker": False}
            return {"task": tid}
        if op == "note":
            kind = p.get("kind", "decision")
            require(kind in {"decision", "finding", "handoff", "lesson"}, "Tipo de nota inválido.")
            s["notes"].append({"kind": kind, "text": label(p.get("text"), "text"), "at": stamp()})
            return {"noted": True}
        if op == "limits":
            label(p.get("reason"), "reason")
            self.limits(s, p.get("limits"))
            return {"limits": s["limits"]}
        if op.startswith("effect."):
            return self.effect(s, p)
        t = self.task(s, p)
        if op == "task.claim":
            now = time.time()
            require(not (t.get("lease") and t["lease"]["expires"] > now), "Tarefa reservada.")
            require(t["state"] not in {"waiting", "blocked"}, "Tarefa bloqueada ou aguardando. Libere com motivo ou mude estratégia.")
            require(not self.accepted(s, t["id"]), "Tarefa já concluída com evidências atuais.")
            require(self.deps_ready(s, t), "Dependência pendente ou desatualizada.")
            require(not t["breaker"], "Repetição bloqueada. Mude a estratégia com justificativa.")
            require(t["attempts"] < s["limits"]["max_attempts"], "Orçamento de tentativas esgotado.")
            require(not self.unresolved(s, t["id"]), "Reconcilie o efeito externo incerto antes de retomar.")
            active = [x for x in s["tasks"].values() if x.get("lease") and x["lease"]["expires"] > now]
            require(len(active) < s["limits"]["max_active"], "Limite de concorrência atingido.")
            require(not any(self.overlap(a, b) for x in active for a in x["paths"] for b in t["paths"]), "Área de escrita reservada por outra tarefa.")
            t["attempts"] += 1
            t["state"] = "doing"
            t["dependency_acceptance"] = {d: s["tasks"][d].get("acceptance_id") for d in t["depends"]}
            t["lease"] = {"owner": label(p.get("owner"), "owner", 200), "token": secrets.token_urlsafe(24),
                          "expires": now + number(p.get("seconds", 1800), "seconds", maximum=86400)}
            return {"task": t["id"], "token": t["lease"]["token"], "attempt": t["attempts"]}
        if op in {"task.strategy", "task.unblock"}:
            require(not (t["lease"] and t["lease"]["expires"] > time.time()), "Libere a reserva antes desta alteração.")
            reason = label(p.get("reason"), "reason")
            if op == "task.strategy":
                new = label(p.get("strategy"), "strategy")
                require(new != t["strategy"], "A estratégia deve mudar.")
                t["strategy"], t["breaker"], t["repeat"] = new, False, 0
            else:
                require(t["state"] in {"waiting", "blocked"} and not t["breaker"], "Estado não liberável sem mudar estratégia.")
            t["state"] = "todo"
            s["notes"].append({"kind": "decision", "text": t["id"] + ": " + reason, "at": stamp()})
            return {"strategy": t["strategy"], "attempts_preserved": t["attempts"]}
        self.owned(t, p)
        if op == "task.renew":
            t["lease"]["expires"] = time.time() + number(p.get("seconds", 1800), "seconds", maximum=86400)
            return {"renewed": True}
        if op == "task.next":
            t["next"] = label(p.get("next"), "next")
            return {"next": t["next"]}
        if op == "evidence.add":
            c = next((x for x in t["criteria"] if x["id"] == p.get("criterion")), None)
            require(c is not None and c["kind"] == p.get("kind"), "Critério ou tipo incompatível.")
            kind = p["kind"]
            raw_files = p.get("files", [])
            require(isinstance(raw_files, list), "files exige lista.")
            files = []
            for raw in raw_files:
                path = self.local(raw)
                require(path.is_file() and not path.is_relative_to(self.home), "Anexe arquivo real do trabalho fora do estado Veronica.")
                files.append({"path": str(path.relative_to(self.root)).replace("\\", "/"), "sha256": digest(path)})
            require(kind not in {"file", "runtime"} or files, "Verificação local exige anexos.")
            url = p.get("url", "")
            require(kind != "source" or (isinstance(url, str) and re.match(r"^https?://[^\s]+$", url)), "Fonte exige URL HTTP(S).")
            ttl = p.get("ttl_hours")
            require(kind not in {"source", "human"} or ttl is not None, "Fonte ou observação humana exige prazo de validade.")
            expires = time.time() + number(ttl, "ttl_hours", minimum=0.001, maximum=87600) * 3600 if ttl is not None else None
            e = {"id": uuid.uuid4().hex[:12], "criterion": c["id"], "kind": kind, "attempt": t["attempts"],
                 "at": stamp(), "method": label(p.get("method"), "method"), "result": label(p.get("result"), "result"),
                 "limitations": p.get("limitations", ""), "files": files, "url": url, "expires": expires}
            t["evidence"].append(e)
            t["state"] = "verify"
            return {"evidence": e["id"], "coverage_missing": self.coverage(t), "semantic_verification": "reported_by_executor"}
        if op == "task.complete":
            require(self.deps_ready(s, t), "Dependência mudou ou deixou de ser aceita.")
            require(all(t["dependency_acceptance"].get(d) == s["tasks"][d].get("acceptance_id") for d in t["depends"]),
                    "Dependência recebeu nova aceitação durante a execução. Retome e verifique novamente.")
            require(not self.coverage(t), "Critérios sem evidência atual: " + ", ".join(self.coverage(t)))
            require(not any(e["task"] == t["id"] and e["state"] in {"prepared", "started", "unknown"} for e in s["effects"].values()), "Efeito externo ainda pendente.")
            t["state"], t["lease"], t["next"] = "done", None, ""
            t["acceptance_id"] = uuid.uuid4().hex
            return {"complete": t["id"], "semantic_verification": "reported_by_executor"}
        if op in {"task.fail", "task.release"}:
            next_step = label(p.get("next"), "next")
            if op == "task.fail":
                sig = label(p.get("signature"), "signature", 500)
                t["repeat"] = t["repeat"] + 1 if t["failures"] and t["failures"][-1]["signature"] == sig else 1
                t["failures"].append({"signature": sig, "reason": label(p.get("reason"), "reason"), "at": stamp(), "attempt": t["attempts"]})
                t["breaker"] = t["repeat"] >= s["limits"]["repeat_failure"]
                state = "blocked" if t["breaker"] else "todo"
            else:
                state = p.get("state", "todo")
                require(state in {"todo", "blocked", "waiting"}, "Estado de liberação inválido.")
            t["state"], t["lease"], t["next"] = state, None, next_step
            return {"state": state, "breaker": t["breaker"]}
        raise VeronicaError("Operação desconhecida: " + op)

    def effect(self, s, p):
        key = identity(p.get("key"))
        op = p["op"]
        if op == "effect.prepare":
            require(key not in s["effects"], "Chave já registrada. Consulte o destino antes de tentar novamente.")
            t = self.task(s, p)
            self.owned(t, p)
            s["effects"][key] = {"task": t["id"], "state": "prepared", "description": label(p.get("description"), "description"), "at": stamp()}
        else:
            e = s["effects"].get(key)
            require(e is not None, "Efeito desconhecido.")
            if op == "effect.start":
                self.owned(s["tasks"][e["task"]], p)
                require(e["state"] == "prepared", "Efeito já iniciado. Reconcilie antes de repetir.")
                e["state"] = "started"
            elif op == "effect.resolve":
                require(e["state"] in {"prepared", "started", "unknown"}, "Efeito já resolvido.")
                require(p.get("state") in {"confirmed", "not_applied", "unknown"}, "Resolução inválida.")
                e["state"] = p["state"]
                e["observation"] = label(p.get("observation"), "observation")
            else:
                raise VeronicaError("Operação de efeito desconhecida.")
            e["updated"] = stamp()
        return {"effect": key, "state": s["effects"][key]["state"], "executed_by_helper": False}

    def status(self):
        s = self.read()
        safe = json.loads(json.dumps(s))
        memo = {}
        active = [x for x in s["tasks"].values() if x.get("lease") and x["lease"]["expires"] > time.time()]
        for tid, t in safe["tasks"].items():
            if t.get("lease"):
                t["lease"].pop("token", None)
                t["lease"]["active"] = t["lease"]["expires"] > time.time()
            t["accepted_current"] = self.accepted(s, tid, memo)
            t["effective_state"] = "stale" if t["state"] == "done" and not t["accepted_current"] else t["state"]
            if t["state"] in {"doing", "verify"} and not (t["lease"] and t["lease"]["active"]):
                t["effective_state"] = "interrupted"
            t["missing_evidence"] = self.coverage(t)
            t["ready"] = (not t["accepted_current"] and self.deps_ready(s, t) and not t["breaker"] and
                t["attempts"] < s["limits"]["max_attempts"] and not (t["lease"] and t["lease"]["active"]) and
                t["state"] not in {"waiting", "blocked"} and not self.unresolved(s, tid) and
                len(active) < s["limits"]["max_active"] and
                not any(self.overlap(a, b) for x in active for a in x["paths"] for b in t["paths"]))
            for e in t["evidence"]:
                e["current"], e["freshness_reason"] = self.evidence_valid(e, t)
        safe["all_accepted"] = bool(s["tasks"]) and all(t["accepted_current"] for t in safe["tasks"].values())
        return safe

    def resume(self, max_chars=9000):
        s = self.status()
        lines = ["# Retomar com Veronica", "", "Objetivo: " + s["goal"], f"Revisão: {s['revision']} | Versão: {VERSION}", "",
                 "Estado de processo. A qualidade das evidências exige julgamento do executor.",
                 "Confirme ferramentas atuais, arquivos e efeitos externos antes de continuar.", "", "## Tarefas"]
        for t in s["tasks"].values():
            lines.append(f"- {t['id']}: {t['effective_state']} — {t['title']} ({t['attempts']} tentativas)")
            if t["next"]:
                lines.append("  Próximo passo: " + t["next"])
            if t["missing_evidence"]:
                lines.append("  Evidências pendentes: " + ", ".join(t["missing_evidence"]))
        lines += ["", "## Notas recentes"] + ["- " + n["kind"] + ": " + n["text"] for n in s["notes"][-8:]]
        lines += ["", "## Efeitos externos"] + ["- " + k + ": " + e["state"] + " — " + e["description"] for k, e in s["effects"].items() if e["state"] in {"started", "unknown"}]
        lines += ["", "Registros completos: work/veronica/veronica.db. Exporte status JSON para critérios e evidências.",
                  "Reservas são cooperativas. Um checkpoint copia o estado do processo, não o produto."]
        text = "\n".join(lines) + "\n"
        if len(text) > max_chars:
            text = text[:max_chars - 200] + "\n\nResumo truncado. Consulte status JSON e o banco original antes de decidir.\n"
        return text

    def publish(self):
        atomic_text(self.home / "estado.json", json.dumps(self.status(), ensure_ascii=False, indent=2) + "\n")
        atomic_text(self.home / "RETOMAR.md", self.resume())
        return self.dashboard()

    def dashboard(self):
        s = self.status()
        esc = lambda v: html.escape(str(v), quote=True)
        rows = []
        names = {"todo": "Pendente", "doing": "Em execução", "verify": "Em verificação", "done": "Concluída", "stale": "Rever evidências", "interrupted": "Interrompida", "blocked": "Bloqueada", "waiting": "Aguardando"}
        for t in s["tasks"].values():
            details = "".join(f"<li>{esc(c['title'])} <small>({esc(c['kind'])})</small></li>" for c in t["criteria"])
            evidence = "".join(f"<li>{esc(e['result'])}<br><small>{esc(e['method'])} — {esc(e['freshness_reason'])}</small></li>" for e in t["evidence"])
            rows.append(f"<article data-state='{esc(t['effective_state'])}'><p class='meta'>{esc(t['id'])} · {esc(names[t['effective_state']])} · tentativa {t['attempts']}</p><h2>{esc(t['title'])}</h2><p>{esc(t['next'])}</p><details><summary>Critérios e evidências</summary><ul>{details}</ul><h3>Verificações registradas</h3><ul>{evidence or '<li>Ainda sem evidência</li>'}</ul><p>Dependências: {esc(', '.join(t['depends']) or 'nenhuma')}</p></details></article>")
        done = sum(t["accepted_current"] for t in s["tasks"].values())
        notes = "".join("<li>" + esc(n["text"]) + "</li>" for n in s["notes"][-8:])
        effects = "".join(f"<li>{esc(k)}: {esc(e['state'])} — {esc(e['description'])}</li>" for k, e in s["effects"].items())
        document = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>Veronica — progresso</title><style>
body{{margin:0;background:#f5f3eb;color:#172d31;font:17px/1.55 system-ui,sans-serif}}main{{max-width:980px;margin:auto;padding:45px 25px}}h1{{font-size:48px;line-height:1.05;margin:12px 0 24px}}h2{{font-size:24px}}.meta,small{{color:#41636a}}article{{border-top:1px solid #c5ceca;padding:24px 0}}summary{{cursor:pointer;color:#126b66}}details{{max-width:850px}}.lead{{font-size:24px}}progress{{width:100%;height:14px;accent-color:#126b66}}.notice{{background:#e3e9e1;padding:16px}}li{{margin-bottom:9px}}footer{{padding-top:28px;font-size:14px}}p,h2,li{{overflow-wrap:anywhere}}
</style><main><p class="meta">VERONICA 1.0 · registro local de trabalho</p><h1>{esc(s['goal'])}</h1><p class="lead">{done} de {len(s['tasks'])} tarefas com evidências atuais</p><progress value="{done}" max="{max(1,len(s['tasks']))}"></progress><p class="notice">Este painel é uma fotografia do estado. Gere novamente para atualizar hashes e prazos. A qualidade de cada verificação depende da evidência observada.</p>{''.join(rows)}<h2>Decisões e aprendizados recentes</h2><ul>{notes or '<li>Sem notas</li>'}</ul><h2>Ações externas registradas</h2><ul>{effects or '<li>Nenhuma</li>'}</ul><footer>Revisão {s['revision']} · gerado {esc(stamp())} · sem conexão de rede ou serviço em segundo plano</footer></main></html>"""
        path = self.home / "painel.html"
        atomic_text(path, document)
        return str(path)

    def checkpoint(self, reason):
        label(reason, "reason")
        folder = self.home / "checkpoints" / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as source:
            with contextlib.closing(sqlite3.connect(str(folder / "veronica.db"))) as target:
                source.backup(target)
        with contextlib.closing(sqlite3.connect(str(folder / "veronica.db"))) as conn:
            s = self.load(conn)
        for t in s["tasks"].values():
            if t.get("lease"):
                t["lease"].pop("token", None)
        atomic_text(folder / "estado.json", json.dumps(s, ensure_ascii=False, indent=2))
        atomic_text(folder / "manifesto.json", json.dumps({"version": VERSION, "at": stamp(), "reason": reason,
             "revision": s["revision"], "scope": "process_state_only", "database_sha256": digest(folder / "veronica.db"),
             "product_files_copied": False}, ensure_ascii=False, indent=2))
        self.publish()
        return {"checkpoint": str(folder), "scope": "process_state_only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "apply"):
        sub = commands.add_parser(name)
        sub.add_argument("--input", required=True, help="JSON UTF-8")
    commands.add_parser("status")
    sub = commands.add_parser("resume")
    sub.add_argument("--max-chars", type=int, default=9000)
    sub = commands.add_parser("checkpoint")
    sub.add_argument("--reason", required=True)
    commands.add_parser("dashboard")
    commands.add_parser("doctor")
    args = parser.parse_args()
    try:
        store = Store(args.workspace)
        if args.command in {"init", "apply"}:
            p = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
            if args.command == "init":
                require(isinstance(p, dict) and p.get("op", "init") == "init", "init exige objeto com op init.")
                p["op"] = "init"
            result = store.apply(p)
            try:
                result["dashboard"] = store.publish()
            except Exception as exc:
                result["projection_warning"] = str(exc)
        elif args.command == "status":
            result = store.status()
        elif args.command == "resume":
            number(args.max_chars, "max-chars", minimum=1500, maximum=50000)
            print(store.resume(args.max_chars))
            return 0
        elif args.command == "checkpoint":
            require(store.db.is_file(), "Projeto não inicializado.")
            result = store.checkpoint(args.reason)
        elif args.command == "dashboard":
            result = {"dashboard": store.publish()}
        else:
            with store.connect() as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            result = {"ok": integrity == "ok", "sqlite": integrity, "events": events, "version": VERSION}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 2
    except (VeronicaError, OSError, ValueError, sqlite3.Error, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
