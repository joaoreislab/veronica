"""Explicit recovery bundles for the ledger, artifacts and selected product files.

Use a new destination and stabilize product writers. No application or login is restored.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import sys
import tempfile

from health import validate_state
from preserve import Artifacts
from veronica import Store, VERSION, VeronicaError, atomic_text, digest, require, stamp


def clean_stage(stage, parent):
    # Delete only the uniquely created temporary directory inside the checked parent.
    stage, parent = stage.resolve(), parent.resolve()
    require(stage.parent == parent and stage.name.startswith(".veronica-recovery-"), "Unexpected staging path.")
    if stage.exists():
        shutil.rmtree(stage)


def copy_exact(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("xb") as target:
        shutil.copyfileobj(src, target, 1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    require(digest(source) == digest(destination), "Source changed during copy: " + str(source))


def sqlite_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        with contextlib.closing(sqlite3.connect(str(destination))) as target:
            src.backup(target)


def verify(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "bundle.json").read_text(encoding="utf-8"))
    require(isinstance(manifest, dict) and manifest.get("format") == "veronica-bundle-v1" and
            isinstance(manifest.get("files"), dict), "Invalid recovery manifest.")
    require("work/veronica/veronica.db" in manifest["files"], "Bundle has no ledger.")
    for name, sha in manifest["files"].items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and ".." not in rel.parts and "\\" not in name and ":" not in name,
                "Unsafe bundle path.")
        path = folder.joinpath(*rel.parts)
        require(path.resolve().is_relative_to(folder) and not path.is_symlink(), "Bundle path escapes its root.")
        require(path.is_file() and digest(path) == sha, "Bundle file missing or changed: " + name)
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p != folder / "bundle.json"}
    require(actual == set(manifest["files"]), "Unlisted files in recovery bundle.")
    store = Store(folder)
    with store.connect() as conn:
        require(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Bundle SQLite integrity failed.")
        validate_state(store.load(conn), store)
    if (store.home / "artifacts" / "catalog.sqlite").is_file():
        report = Artifacts(folder, create=False).reconcile()
        require(report["ok"], "Bundle artifact reconciliation failed: " + json.dumps(report["issues"]))
    return manifest


def bundle(workspace, output, includes=()):
    store = Store(workspace)
    destination = store.local(output)
    require(not destination.exists() and not destination.is_relative_to(store.home), "Choose a new bundle path outside Veronica state.")
    product = {}
    for raw in includes:
        source = store.local(raw)
        require(source.exists() and source != store.root and not source.is_relative_to(store.home) and
                not store.home.is_relative_to(source) and not destination.is_relative_to(source), "Select product paths outside state and bundle destination.")
        candidates = [source] if source.is_file() else [p for p in source.rglob("*") if p.is_file()]
        for path in candidates:
            require(not path.is_symlink() and path.resolve().is_relative_to(store.root), "Product symlink/escape is not bundled.")
            name = path.relative_to(store.root).as_posix()
            require(name != "bundle.json", "bundle.json at the bundle root is reserved for its manifest.")
            product[name] = path
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".veronica-recovery-", dir=destination.parent))
    try:
        # Lock both cooperating stores in the same order, before taking snapshots.
        with store.connect(write=True), contextlib.ExitStack() as locks:
            catalog = store.home / "artifacts" / "catalog.sqlite"
            if catalog.is_file():
                conn = sqlite3.connect(catalog.as_uri() + "?mode=rw", uri=True, timeout=15)
                locks.callback(conn.close)
                conn.execute("BEGIN IMMEDIATE")
                locks.callback(conn.rollback)
                report = Artifacts(store.root, create=False).reconcile()
                require(report["ok"], "Reconcile artifacts before bundling: " + json.dumps(report["issues"]))
            state = store.read()
            validate_state(state, store)
            sqlite_copy(store.db, stage / "work/veronica/veronica.db")
            if catalog.is_file():
                sqlite_copy(catalog, stage / "work/veronica/artifacts/catalog.sqlite")
                for part in ("blobs", "receipts"):
                    for source in sorted((catalog.parent / part).glob("*")):
                        if source.is_file() and source.suffix in {".bin", ".json"}:
                            require(not source.is_symlink() and source.resolve().is_relative_to(store.home), "Artifact path escapes state.")
                            copy_exact(source, stage / source.relative_to(store.root))
            for name, source in product.items():
                copy_exact(source, stage / name)
            files = {p.relative_to(stage).as_posix(): digest(p) for p in sorted(stage.rglob("*")) if p.is_file()}
            manifest = {"format": "veronica-bundle-v1", "version": VERSION, "at": stamp(),
                "revision": state["revision"], "files": files, "product_paths": list(includes),
                "scope": "ledger_artifacts_and_explicit_product_paths", "environment_restored": False,
                "unselected_product_files_included": False, "source_writers_must_be_stable": True}
            atomic_text(stage / "bundle.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            verify(stage)
        require(not destination.exists(), "Bundle destination appeared; refusing replacement.")
        os.rename(stage, destination)
        return {"ok": True, "bundle": str(destination), "files": len(files), "revision": state["revision"], "scope": manifest["scope"]}
    finally:
        if stage.exists():
            clean_stage(stage, destination.parent)


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    require(not destination.exists() and not destination.is_relative_to(source), "Restore requires a new workspace outside the bundle.")
    manifest = verify(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".veronica-recovery-", dir=destination.parent))
    try:
        for name in manifest["files"]:
            copy_exact(source / name, stage / name)
        # Check copied data again before modifying its lease state.
        atomic_text(stage / "bundle.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        verify(stage)
        (stage / "bundle.json").unlink()
        store = Store(stage)
        with store.connect(write=True) as conn:
            state = store.load(conn)
            for task in state["tasks"].values():
                if task.get("lease"):
                    task["lease"]["expires"] = 0
            state["version"], state["updated"] = VERSION, stamp()
            state["revision"] += 1
            conn.execute("UPDATE project SET state=? WHERE id=1", (json.dumps(state, ensure_ascii=False),))
            conn.execute("INSERT INTO events(at,op,payload) VALUES(?,?,?)", (stamp(), "recovery.restore",
                json.dumps({"bundle_revision": manifest["revision"], "leases_expired": True})))
        store.publish()
        require(not destination.exists(), "Workspace destination appeared; refusing replacement.")
        os.rename(stage, destination)
        return {"ok": True, "workspace": str(destination), "leases_expired": True,
                "external_effects_preserved": True, "environment_restored": False,
                "revision": state["revision"], "files": len(manifest["files"])}
    finally:
        if stage.exists():
            clean_stage(stage, destination.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("bundle")
    sub.add_argument("--workspace", required=True)
    sub.add_argument("--output", required=True)
    sub.add_argument("--include", action="append", default=[])
    sub = commands.add_parser("verify"); sub.add_argument("--bundle", required=True)
    sub = commands.add_parser("restore")
    sub.add_argument("--bundle", required=True); sub.add_argument("--workspace", required=True)
    args = parser.parse_args()
    try:
        if args.command == "bundle":
            result = bundle(args.workspace, args.output, args.include)
        elif args.command == "restore":
            result = restore(args.bundle, args.workspace)
        else:
            manifest = verify(args.bundle)
            result = {"ok": True, "revision": manifest["revision"], "files": len(manifest["files"]), "scope": manifest["scope"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (VeronicaError, OSError, ValueError, sqlite3.Error, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
