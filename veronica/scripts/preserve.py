#!/usr/bin/env python3
"""Veronica: exact artifacts, reversible views and observed-usage records.

Standard library only. No model calls, execution of commands or hidden deletion.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid


class PreservationError(ValueError):
    pass


def check(condition, message):
    if not condition:
        raise PreservationError(message)


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def compact(text):
    """Compare complete frames, keep order/endings, and verify exact UTF-8 bytes."""
    data = text.encode("utf-8")
    base = {"format": "raw", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "text": text}
    dictionary, lookup, runs = [], {}, []
    for line in text.splitlines(keepends=True):
        if line not in lookup:
            lookup[line] = len(dictionary)
            dictionary.append(line)
        index = lookup[line]
        if runs and runs[-1][0] == index:
            runs[-1][1] += 1
        else:
            runs.append([index, 1])
    candidate = {"format": "lines-v1", "bytes": len(data), "sha256": base["sha256"], "dictionary": dictionary, "runs": runs}
    check(expand(candidate) == text, "Round-trip mismatch; original remains available.")
    return candidate if len(wire(candidate).encode("utf-8")) < len(data) else base


def render(text):
    """A complete frame only when shorter than plain text; otherwise exact text."""
    frame = compact(text)
    return wire(frame) if frame["format"] == "lines-v1" else text


def expand(frame):
    check(isinstance(frame, dict), "Frame must be an object.")
    size = frame.get("bytes")
    check(type(size) is int and size >= 0, "Invalid original byte count.")
    if frame.get("format") == "raw":
        text = frame.get("text")
        check(isinstance(text, str), "Invalid raw frame.")
    else:
        check(frame.get("format") == "lines-v1", "Unknown frame format.")
        dictionary, runs = frame.get("dictionary"), frame.get("runs")
        check(isinstance(dictionary, list) and all(isinstance(x, str) and x for x in dictionary), "Invalid dictionary.")
        check(isinstance(runs, list), "Invalid runs.")
        parts, used = [], 0
        for run in runs:
            check(isinstance(run, list) and len(run) == 2, "Invalid run.")
            index, count = run
            check(type(index) is int and 0 <= index < len(dictionary) and type(count) is int and count > 0, "Invalid run index/count.")
            line = dictionary[index]
            used += len(line.encode("utf-8")) * count
            check(used <= size, "Decoded size exceeds original byte count.")
            parts.append(line * count)
        text = "".join(parts)
    data = text.encode("utf-8")
    check(len(data) == size and hashlib.sha256(data).hexdigest() == frame.get("sha256"), "Frame integrity mismatch.")
    return text


class Artifacts:
    def __init__(self, workspace, create=True):
        self.root = Path(workspace).resolve()
        check(self.root.is_dir(), "Workspace does not exist.")
        self.home = self.local("work/veronica/artifacts")
        self.blobs = self.home / "blobs"
        self.read_only = not create
        self.receipts = self.home / "receipts"
        if create:
            self.home.mkdir(parents=True, exist_ok=True)
        check(self.blobs.resolve().is_relative_to(self.root), "Artifact directory leaves workspace.")
        if create:
            self.blobs.mkdir(exist_ok=True)
            self.receipts.mkdir(exist_ok=True)
        self.db = self.home / "catalog.sqlite"
        check(self.db.resolve().is_relative_to(self.root), "Catalog leaves workspace.")
        if create:
            with self.connect(write=True) as conn:
                for sql in (
                    "CREATE TABLE IF NOT EXISTS blobs(sha TEXT PRIMARY KEY, bytes INTEGER NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS origins(id INTEGER PRIMARY KEY, sha TEXT NOT NULL, source TEXT NOT NULL, at REAL NOT NULL, metadata TEXT NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS capture_receipts(id TEXT PRIMARY KEY, origin_id INTEGER NOT NULL)"):
                    conn.execute(sql)
        else:
            check(self.db.is_file(), "Artifact catalog does not exist.")

    def local(self, raw):
        check(isinstance(raw, (str, Path)) and str(raw), "Path required.")
        p = (self.root / raw).resolve()
        check(p.is_relative_to(self.root), "Path leaves workspace.")
        return p

    @contextlib.contextmanager
    def connect(self, write=False):
        check(not (write and self.read_only), "Read-only catalog.")
        conn = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=15) if self.read_only else sqlite3.connect(str(self.db), timeout=15)
        try:
            if not self.read_only:
                conn.execute("PRAGMA synchronous=FULL")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def path(self, sha):
        check(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "Invalid artifact ID.")
        p = self.local(self.blobs / (sha + ".bin"))
        check(p.is_file() and sha_file(p) == sha, "Artifact missing or changed; do not trust its views.")
        return p

    def capture(self, source, metadata=None):
        src = self.local(source)
        check(src.is_file(), "Source must be a file.")
        check(not src.is_relative_to(self.home), "Capture product data, not the artifact store itself.")
        metadata = {} if metadata is None else metadata
        check(isinstance(metadata, dict), "Metadata must be an object.")
        metadata = json.loads(wire(metadata))
        # Snapshot actual bytes from one open stream, never a lossy text rewrite.
        fd, name = tempfile.mkstemp(dir=self.blobs, suffix=".tmp")
        temp = Path(name)
        try:
            with os.fdopen(fd, "wb") as target:
                with src.open("rb") as source_stream:
                    shutil.copyfileobj(source_stream, target, 1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            sha, size = sha_file(temp), temp.stat().st_size
            dst = self.local(self.blobs / (sha + ".bin"))
            receipt_id = uuid.uuid4().hex
            receipt = {"id": receipt_id, "sha": sha, "bytes": size,
                "source": src.relative_to(self.root).as_posix(), "at": time.time(), "metadata": metadata}
            with self.connect(write=True) as conn:
                reused = dst.exists()
                if reused:
                    check(sha_file(dst) == sha, "Existing snapshot is corrupt; preserve it for diagnosis.")
                # Durable receipt precedes blob promotion; a failed catalog commit can be reconciled.
                with (self.receipts / (receipt_id + ".json")).open("x", encoding="utf-8") as stream:
                    stream.write(wire(receipt))
                    stream.flush()
                    os.fsync(stream.fileno())
                if not reused:
                    os.replace(temp, dst)
                conn.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (sha, size))
                cursor = conn.execute("INSERT INTO origins(sha,source,at,metadata) VALUES(?,?,?,?)", (sha, receipt["source"], receipt["at"], wire(metadata)))
                conn.execute("INSERT INTO capture_receipts VALUES(?,?)", (receipt_id, cursor.lastrowid))
            return {"artifact": sha, "bytes": size, "reused_blob": reused, "origin_id": cursor.lastrowid,
                "capture_receipt": receipt_id, "original_available": True}
        finally:
            temp.unlink(missing_ok=True)

    def restore(self, sha, output):
        source = self.path(sha)
        dst = self.local(output)
        check(not dst.is_relative_to(self.root / "work" / "veronica"), "Restore outside Veronica state.")
        check(not dst.exists(), "Output exists; choose a new path.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".veronica-restore-", suffix=".tmp", dir=dst.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, "wb") as target, source.open("rb") as src:
                shutil.copyfileobj(src, target, 1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            check(sha_file(temp) == sha, "Restored output differs from snapshot.")
            # Atomic no-overwrite promotion on local filesystems supporting hard links.
            os.link(temp, dst)
        finally:
            temp.unlink(missing_ok=True)
        return {"restored": dst.relative_to(self.root).as_posix(), "sha256": sha, "byte_exact": True}

    def read(self, sha, start=1, end=None):
        check(type(start) is int and start >= 1 and (end is None or type(end) is int and end >= start), "Invalid inclusive line range.")
        path = self.path(sha)
        chunks, total = [], 0
        # newline='' preserves CRLF, lone CR, LF and trailing whitespace.
        with path.open("r", encoding="utf-8", newline="") as stream:
            for total, line in enumerate(stream, 1):
                if total >= start and (end is None or total <= end):
                    chunks.append(line)
        return {"artifact": sha, "start": start, "end": min(end or total, total), "total_lines": total,
                "complete": start == 1 and (end is None or end >= total), "text": "".join(chunks), "original_available": True}

    def search(self, sha, query, offset=0, limit=None):
        check(isinstance(query, str) and query, "Literal query required; no stopword removal.")
        check(type(offset) is int and offset >= 0 and (limit is None or type(limit) is int and limit > 0), "Invalid pagination.")
        matches, total = [], 0
        path = self.path(sha)
        with path.open("r", encoding="utf-8", newline="") as stream:
            for number, line in enumerate(stream, 1):
                if query in line:
                    if total >= offset and (limit is None or len(matches) < limit):
                        matches.append({"line": number, "text": line})
                    total += 1
        next_offset = offset + len(matches)
        return {"artifact": sha, "query": query, "matches": matches, "total_matches": total,
                "complete": offset == 0 and len(matches) == total, "next_offset": next_offset if next_offset < total else None,
                "original_available": True, "view_is_not_complete_memory": True}

    @staticmethod
    def validate_usage(payload):
        check(isinstance(payload, dict), "Usage must be an object.")
        check(isinstance(payload.get("id"), str) and payload["id"], "Unique request/event ID required.")
        check(isinstance(payload.get("source_kind"), str) and payload["source_kind"] in {"provider", "local_log", "estimate"} and isinstance(payload.get("source"), str) and payload["source"], "Usage provenance required.")
        for field in ("model", "task"):
            check(payload.get(field) is None or isinstance(payload[field], str), "Invalid usage identity: " + field)
        fields = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "reasoning_output_tokens")
        check(any(payload.get(k) is not None for k in fields), "No usage values supplied.")
        for field in fields:
            value = payload.get(field)
            check(value is None or type(value) is int and value >= 0, "Invalid token count: " + field)
        inp, cached, written = (payload.get(k) for k in fields[:3])
        out, reasoning = (payload.get(k) for k in fields[3:])
        check(inp is None or (cached or 0) + (written or 0) <= inp, "Cache fields are disjoint subsets of input in this schema.")
        check(out is None or reasoning is None or reasoning <= out, "Reasoning is a subset of output in this schema.")

    def record_usage(self, payload):
        self.validate_usage(payload)
        text = wire(payload)
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT payload FROM usage WHERE id=?", (payload["id"],)).fetchone()
            check(row is None or json.loads(row[0]) == payload, "Event ID already has different usage; reconcile it.")
            if row is None:
                conn.execute("INSERT INTO usage VALUES(?,?)", (payload["id"], text))
        return {"recorded": payload["id"], "duplicate_ignored": row is not None, "changes_model_or_budget": False}

    def usage(self):
        records, invalid = [], []
        with self.connect() as conn:
            for event_id, text in conn.execute("SELECT id,payload FROM usage ORDER BY id"):
                try:
                    record = json.loads(text)
                    self.validate_usage(record)
                    check(record["id"] == event_id, "Usage ID differs from row key.")
                    records.append(record)
                except (ValueError, TypeError, KeyError) as exc:
                    invalid.append({"id": event_id, "stored_json": text, "error": str(exc)})
        groups = {}
        for record in records:
            key = (record["source_kind"], record.get("model"), record.get("task"))
            groups.setdefault(key, []).append(record)
        output = []
        for (kind, model, task), items in groups.items():
            totals = {}
            for field in ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "reasoning_output_tokens"):
                values = [r.get(field) for r in items]
                totals[field] = sum(values) if all(v is not None for v in values) else None
            total = totals["input_tokens"] + totals["output_tokens"] if totals["input_tokens"] is not None and totals["output_tokens"] is not None else None
            output.append({"source_kind": kind, "model": model, "task": task, "events": len(items), **totals, "total_tokens": total})
        return {"groups": output, "records": records, "invalid_records": invalid, "complete": not invalid,
                "subscription_bill": None, "currency_cost": None}

    def reconcile(self, repair=False):
        """Inspect every blob and replay only verified capture receipts; never delete data."""
        issues, repaired = [], []
        with self.connect(write=repair) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            check(integrity == "ok", "Catalog integrity failure: " + integrity)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            registered = dict(conn.execute("SELECT sha,bytes FROM blobs"))
            verified = {}
            for path in sorted(self.blobs.glob("*.bin")):
                sha = path.stem
                if not re.fullmatch(r"[0-9a-f]{64}", sha) or sha_file(path) != sha:
                    issues.append({"kind": "corrupt_blob", "path": path.name})
                else:
                    verified[sha] = path.stat().st_size
            for path in sorted(self.receipts.glob("*.json")):
                try:
                    receipt = json.loads(path.read_text(encoding="utf-8"))
                    check(isinstance(receipt, dict) and re.fullmatch(r"[0-9a-f]{32}", str(receipt.get("id", ""))) and
                        path.stem == receipt["id"], "Invalid receipt ID.")
                    sha = receipt["sha"]
                    check(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "Invalid receipt hash.")
                    check(type(receipt["bytes"]) is int and receipt["bytes"] >= 0 and isinstance(receipt["metadata"], dict), "Invalid receipt data.")
                    self.local(receipt["source"])
                    check(type(receipt["at"]) in (float, int) and 0 <= receipt["at"] < float("inf"), "Invalid receipt timestamp.")
                    existing = conn.execute("SELECT origin_id FROM capture_receipts WHERE id=?", (receipt["id"],)).fetchone() if "capture_receipts" in tables else None
                    if existing:
                        origin = conn.execute("SELECT sha,source,at,metadata FROM origins WHERE id=?", (existing[0],)).fetchone()
                        check(origin is not None and origin[:3] == (sha, receipt["source"], receipt["at"]) and json.loads(origin[3]) == receipt["metadata"], "Receipt differs from recorded origin.")
                        continue
                    check(verified.get(sha) == receipt["bytes"], "Receipt has no matching intact blob.")
                    if repair:
                        conn.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (sha, receipt["bytes"]))
                        cursor = conn.execute("INSERT INTO origins(sha,source,at,metadata) VALUES(?,?,?,?)", (sha, receipt["source"], receipt["at"], wire(receipt["metadata"])))
                        conn.execute("INSERT INTO capture_receipts VALUES(?,?)", (receipt["id"], cursor.lastrowid))
                        registered[sha] = receipt["bytes"]
                        repaired.append(receipt["id"])
                    else:
                        issues.append({"kind": "pending_receipt", "id": receipt["id"], "artifact": sha})
                except (ValueError, TypeError, KeyError, OSError) as exc:
                    issues.append({"kind": "invalid_receipt", "path": path.name, "error": str(exc)})
            for sha, size in registered.items():
                if verified.get(sha) != size:
                    issues.append({"kind": "missing_or_changed_blob", "artifact": sha})
            for sha in verified.keys() - registered.keys():
                issues.append({"kind": "orphan_blob", "artifact": sha, "origin_unknown": True})
            for origin_id, sha, metadata in conn.execute("SELECT id,sha,metadata FROM origins"):
                if sha not in registered:
                    issues.append({"kind": "orphan_origin", "origin_id": origin_id})
                try:
                    check(isinstance(json.loads(metadata), dict), "Origin metadata must be an object.")
                except (ValueError, TypeError) as exc:
                    issues.append({"kind": "invalid_origin", "origin_id": origin_id, "error": str(exc)})
        issues.extend({"kind": "invalid_usage", **item} for item in self.usage()["invalid_records"])
        return {"ok": not issues, "issues": issues, "repaired_receipts": repaired, "deleted_files": 0,
                "verified_blobs": len(verified), "temporary_files": [x.name for x in self.blobs.glob("*.tmp")]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("capture"); sub.add_argument("--file", required=True); sub.add_argument("--metadata", help="JSON file")
    sub = commands.add_parser("restore"); sub.add_argument("--artifact", required=True); sub.add_argument("--output", required=True)
    sub = commands.add_parser("read"); sub.add_argument("--artifact", required=True); sub.add_argument("--start", type=int, default=1); sub.add_argument("--end", type=int)
    sub = commands.add_parser("search"); sub.add_argument("--artifact", required=True); sub.add_argument("--query", required=True); sub.add_argument("--offset", type=int, default=0); sub.add_argument("--limit", type=int)
    sub = commands.add_parser("compact"); sub.add_argument("--artifact", required=True); sub.add_argument("--render", action="store_true", help="Compact frame when smaller, otherwise exact plain text; explicit text-output mode.")
    sub = commands.add_parser("usage-record"); sub.add_argument("--input", required=True)
    commands.add_parser("usage")
    sub = commands.add_parser("reconcile"); sub.add_argument("--repair", action="store_true", help="Replay verified pending capture receipts; never delete blobs.")
    args = parser.parse_args()
    try:
        store = Artifacts(args.workspace, create=args.command != "reconcile" or args.repair)
        if args.command == "capture":
            meta = json.loads(store.local(args.metadata).read_text(encoding="utf-8-sig")) if args.metadata else {}
            result = store.capture(args.file, meta)
        elif args.command == "restore": result = store.restore(args.artifact, args.output)
        elif args.command == "read": result = store.read(args.artifact, args.start, args.end)
        elif args.command == "search": result = store.search(args.artifact, args.query, args.offset, args.limit)
        elif args.command == "compact":
            text = store.read(args.artifact)["text"]
            if args.render:
                print(render(text), end="")
                return 0
            result = compact(text)
        elif args.command == "usage-record": result = store.record_usage(json.loads(store.local(args.input).read_text(encoding="utf-8-sig")))
        elif args.command == "reconcile": result = store.reconcile(args.repair)
        else: result = store.usage()
        print(wire(result))
        return 0 if result.get("ok", True) else 2
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError, UnicodeError) as exc:
        print(wire({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
