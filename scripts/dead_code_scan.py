#!/usr/bin/env python
"""Conservative reference-based dead-code candidate scanner (IDENTIFY ONLY).

Part of the turn-closeout harness dead-code audit pipeline (R-DeadCodeAudit).
It NEVER deletes anything — it only emits *candidates* that a human + team
audit must confirm before any removal (dry-run -> audit -> apply).

Heuristic: a module is a candidate if its basename and dotted module path are
not referenced (import / from-import / path string) anywhere outside its own
file, AND it is not a known entrypoint / package init / test. False positives
are expected (dynamic imports, plugin discovery, CLI entrypoints) — hence
confidence is LOW and removal requires review.

Outputs JSON to .harness/dead_code_candidates.json. stdlib only.

Usage:  python scripts/dead_code_scan.py [repo_root]
"""
import json
import os
import re
import sys

CODE_DIRS = ("ingestion", "backend", "agents", "workers", "scripts")
SEARCH_EXT = (".py", ".json", ".yaml", ".yml", ".toml", ".md", ".cfg", ".ini", ".txt")
SKIP_DIR = {"__pycache__", ".venv", "node_modules", ".git", "outputs", "logs"}
# entrypoints / files that are referenced indirectly (frameworks, test runner)
ENTRYPOINT_BASES = {
    "__init__", "__main__", "main", "app", "asgi", "wsgi", "manage",
    "conftest", "celery_app", "celeryconfig", "settings", "setup",
}
IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)


def _iter_files(root, exts):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIR]
        for fn in fns:
            if fn.endswith(exts):
                yield os.path.join(dp, fn)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def scan(root):
    # 1) collect candidate modules
    modules = []  # (relpath, basename, dotted)
    for d in CODE_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for p in _iter_files(base, (".py",)):
            rel = os.path.relpath(p, root).replace("\\", "/")
            bn = os.path.splitext(os.path.basename(p))[0]
            dotted = rel[:-3].replace("/", ".")
            modules.append((rel, bn, dotted))

    # 2) build reference corpus (all searchable files except the module itself)
    corpus = {}  # relpath -> text
    for d in CODE_DIRS + ("docs", "tests", "configs", "."):
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for p in _iter_files(base, SEARCH_EXT):
            rel = os.path.relpath(p, root).replace("\\", "/")
            corpus.setdefault(rel, _read(p))

    # 3) set of all imported names across the codebase
    imported = set()
    for rel, txt in corpus.items():
        if rel.endswith(".py"):
            for m in IMPORT_RE.finditer(txt):
                name = m.group(1) or m.group(2)
                if name:
                    imported.add(name)
                    imported.add(name.split(".")[-1])
                    imported.add(name.split(".")[0])

    candidates = []
    for rel, bn, dotted in modules:
        if bn in ENTRYPOINT_BASES:
            continue
        if "/tests/" in rel or rel.startswith("tests/") or bn.startswith("test_"):
            continue
        # referenced via import?
        ref_import = (
            dotted in imported
            or bn in imported
            or any(dotted.endswith("." + part) for part in [bn])
        )
        # referenced by its FULL relpath or FULL dotted module string anywhere
        # outside its own file? (bare-basename substring is intentionally NOT
        # used here — it over-matches arbitrary text and hides real dead code.)
        ref_path = False
        for orel, txt in corpus.items():
            if orel == rel:
                continue
            if rel in txt or dotted in txt:
                ref_path = True
                break
        if not ref_import and not ref_path:
            candidates.append({
                "path": rel,
                "module": dotted,
                "reason": "no inbound import/path reference found",
                "confidence": "LOW",
                "action": "team audit required before removal (do NOT delete)",
            })

    return {
        "schema_version": 1,
        "scanned_dirs": list(CODE_DIRS),
        "total_modules_scanned": len(modules),
        "candidate_count": len(candidates),
        "candidates": sorted(candidates, key=lambda c: c["path"]),
        "note": "heuristic, conservative. false positives expected "
                "(dynamic import, plugin discovery, CLI entrypoints). "
                "removal only after dry-run -> team audit -> small commit.",
    }


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    result = scan(root)
    out_dir = os.path.join(root, ".harness")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "dead_code_candidates.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("dead_code_scan: %d modules scanned, %d candidates -> %s"
          % (result["total_modules_scanned"], result["candidate_count"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
