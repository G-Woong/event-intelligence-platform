#!/usr/bin/env python
"""Dead-code candidate scanner (IDENTIFY ONLY — never deletes).

Part of the turn-closeout harness dead-code audit pipeline (R-DeadCodeAudit).
Emits *candidates* for human + team audit (dry-run -> audit -> apply); it does
NOT remove anything.

Two complementary detectors, merged into one candidate list:

  1. SYMBOL level (precise) — runs ``ruff`` (already a dev dep) with the pyflakes
     F-codes that flag genuinely unused code: F401 unused import, F811
     redefinition, F841 unused local variable. High confidence, low false
     positive. Optional ``vulture`` (if installed) adds unused
     functions/classes/attributes. Both degrade gracefully when absent.

  2. MODULE level (heuristic, LOW confidence) — a module is a candidate if its
     dotted path / relpath is not referenced (import or path string) anywhere
     outside its own file and it is not a known entrypoint/init/test. False
     positives are expected (dynamic import, plugin discovery, CLI entrypoints),
     and basename collisions in a 400-module package suppress real positives
     (recall limit) — hence LOW confidence and the explicit ``tools_available``
     report so candidate==0 is never rendered as "clean".

Output: ``.harness/dead_code_candidates.json``. stdlib + optional ruff/vulture.

Usage:  python scripts/dead_code_scan.py [repo_root]
"""
import json
import os
import re
import subprocess
import sys

CODE_DIRS = ("ingestion", "backend", "agents", "workers", "scripts")
SEARCH_EXT = (".py", ".json", ".yaml", ".yml", ".toml", ".md", ".cfg", ".ini", ".txt")
SKIP_DIR = {
    "__pycache__", ".venv", "node_modules", ".git", "outputs", "logs",
    # volatile/generated dirs: reading these into the corpus made the module
    # heuristic NON-DETERMINISTIC run-to-run (.harness rewrites every scan) —
    # test-validation CONCERN-1. Excluding them stabilizes candidate counts.
    ".harness", ".claude", "dist", "build", ".next", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "htmlcov",
}
# never read secret-bearing files into the corpus (security-guardian note —
# defense in depth; these never reached the output, this removes the in-memory read)
SKIP_FILE_RE = re.compile(r"(^\.env)|(-key\.json$)|(service-account)", re.I)
ENTRYPOINT_BASES = {
    "__init__", "__main__", "main", "app", "asgi", "wsgi", "manage",
    "conftest", "celery_app", "celeryconfig", "settings", "setup",
}
IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
# also capture the names AFTER `from X import a, b as c` so a submodule imported
# as `from pkg.sub import mod` registers `mod` as referenced (test-validation
# CONCERN: IMPORT_RE alone missed submodule targets -> false dead module).
FROM_NAMES_RE = re.compile(r"^\s*from\s+[\w.]+\s+import\s+(.+)$", re.M)
RUFF_RULES = ("F401", "F811", "F841")


def _iter_files(root, exts):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIR]
        for fn in fns:
            if fn.endswith(exts) and not SKIP_FILE_RE.search(fn):
                yield os.path.join(dp, fn)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def _tool_available(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def _rel(root, p):
    return os.path.relpath(p, root).replace("\\", "/")


def _ruff_candidates(root):
    """Run ruff for unused-code F-codes; return (candidates, available, error)."""
    if not _tool_available("ruff"):
        return [], False, "ruff not importable"
    dirs = [os.path.join(root, d) for d in CODE_DIRS if os.path.isdir(os.path.join(root, d))]
    if not dirs:
        return [], True, None
    cmd = [sys.executable, "-m", "ruff", "check",
           "--select", ",".join(RUFF_RULES), "--output-format", "json"] + dirs
    try:
        r = subprocess.run(cmd, capture_output=True, cwd=root, timeout=120)
    except Exception as e:  # ruff missing/slow -> degrade
        return [], True, "ruff invocation failed: %s" % e
    try:
        rows = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
    except ValueError:
        return [], True, "ruff output not JSON"
    out = []
    for it in rows:
        code = it.get("code")
        loc = it.get("location") or {}
        out.append({
            "path": _rel(root, it.get("filename", "")),
            "symbol": (it.get("message") or "").strip(),
            "kind": "symbol",
            "evidence": "ruff %s @ line %s" % (code, loc.get("row")),
            "reference_count": 0,
            "confidence": "HIGH",
            "false_positive_risk": "LOW (pyflakes static analysis)",
            "recommended_action": "inspect",  # unused import/var: usually safe to drop, still review
            "deletion_allowed": False,
        })
    return out, True, None


VULTURE_RE = re.compile(
    r"^(.+?):(\d+):\s+unused\s+(\w[\w ]*?)\s+'([^']+)'\s+\((\d+)%\s+confidence\)")
VULTURE_SCAN_CONFIDENCE = 60  # scan low, filter per-kind below.
# Per-kind confidence floor. vulture's UNIQUE value over ruff is DEFINITION-level
# dead code (uncalled function/method/class/property) — those land at ~60%, so we
# keep them at 60. import/variable overlap ruff (F401/F841) and only add noise
# unless near-certain, so we gate them high. attribute is framework-prone -> 80.
_VULTURE_KIND_MIN = {
    "function": 60, "method": 60, "class": 60, "property": 60,
    "attribute": 80, "variable": 90, "import": 90,
}


def _vulture_candidates(root):
    """Run vulture for AST-level dead code ruff cannot see (uncalled
    function/method/class). Returns (candidates, available, error). Degrades
    gracefully if absent. Per-kind confidence floors keep the high-value
    definition-level findings while suppressing low-confidence arg/var noise."""
    if not _tool_available("vulture"):
        return [], False, "vulture not importable"
    dirs = [d for d in CODE_DIRS if os.path.isdir(os.path.join(root, d))]
    if not dirs:
        return [], True, None
    # exclude framework-invoked entrypoints that are guaranteed vulture
    # false positives (alembic migration upgrade/downgrade are called by the
    # migration runner, never statically).
    cmd = [sys.executable, "-m", "vulture", *dirs,
           "--exclude", "*/alembic/*,*/migrations/*",
           "--min-confidence", str(VULTURE_SCAN_CONFIDENCE)]
    try:
        r = subprocess.run(cmd, capture_output=True, cwd=root, timeout=120)
    except Exception as e:
        return [], True, "vulture invocation failed: %s" % e
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        m = VULTURE_RE.match(line.strip())
        if not m:
            continue
        path, _ln, kind, name, conf = m.groups()
        kind, conf = kind.strip(), int(conf)
        if conf < _VULTURE_KIND_MIN.get(kind, 80):
            continue
        definition = kind in ("function", "method", "class", "property")
        out.append({
            "path": _rel(root, os.path.join(root, path)),
            "symbol": "%s '%s'" % (kind, name),
            "kind": "vulture",
            "evidence": "vulture unused %s @ line %s (%d%%)" % (kind, _ln, conf),
            "reference_count": 0,
            "confidence": "HIGH" if conf >= 90 else ("MEDIUM" if conf >= 70 else "LOW"),
            "false_positive_risk": ("MEDIUM (dynamic dispatch / framework callback / "
                                    "entrypoint)" if definition
                                    else "HIGH (fixture / framework-set / dynamic)"),
            "recommended_action": "inspect",
            "deletion_allowed": False,
        })
    return out, True, None


def _module_candidates(root):
    """LOW-confidence module-level reference heuristic (recall-limited)."""
    modules = []
    for d in CODE_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for p in _iter_files(base, (".py",)):
            rel = _rel(root, p)
            bn = os.path.splitext(os.path.basename(p))[0]
            dotted = rel[:-3].replace("/", ".")
            modules.append((rel, bn, dotted))

    corpus = {}
    for d in CODE_DIRS + ("docs", "tests", "configs", "."):
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for p in _iter_files(base, SEARCH_EXT):
            corpus.setdefault(_rel(root, p), _read(p))

    imported = set()
    for rel, txt in corpus.items():
        if not rel.endswith(".py"):
            continue
        for m in IMPORT_RE.finditer(txt):
            name = m.group(1) or m.group(2)
            if name:
                imported.add(name)
                imported.add(name.split(".")[-1])
                imported.add(name.split(".")[0])
        # imported target names: `from X import a, b as c, (d, e)` -> a,b,d,e
        for m in FROM_NAMES_RE.finditer(txt):
            tail = m.group(1).split("#")[0].strip().strip("()")
            for part in tail.split(","):
                tok = part.strip().split(" as ")[0].strip().rstrip("\\").strip()
                if tok and tok != "*":
                    imported.add(tok)

    cands = []
    for rel, bn, dotted in modules:
        if bn in ENTRYPOINT_BASES:
            continue
        if "/tests/" in rel or rel.startswith("tests/") or bn.startswith("test_"):
            continue
        ref_import = dotted in imported or bn in imported
        ref_path = False
        for orel, txt in corpus.items():
            if orel == rel:
                continue
            if rel in txt or dotted in txt:
                ref_path = True
                break
        if not ref_import and not ref_path:
            cands.append({
                "path": rel,
                "symbol": dotted,
                "kind": "module",
                "evidence": "no inbound import/path reference found",
                "reference_count": 0,
                "confidence": "LOW",
                "false_positive_risk": "HIGH (dynamic import / plugin / CLI entrypoint; basename collision)",
                "recommended_action": "inspect",
                "deletion_allowed": False,
            })
    return cands, len(modules)


def _category(path):
    """Coarse bucket for phase-2 triage (NOT a deletion decision)."""
    p = path.replace("\\", "/")
    if "/tests/" in p or p.startswith("tests/") or "/test_" in p \
            or os.path.basename(p).startswith("test_"):
        return "tests"
    if p.startswith("scripts/"):
        return "harness_tooling"
    if p.startswith(("ingestion/", "backend/", "agents/", "workers/")):
        return "production"
    return "other"


def scan(root):
    ruff_c, ruff_ok, ruff_err = _ruff_candidates(root)
    vul_c, vulture_ok, vul_err = _vulture_candidates(root)
    mod_c, n_modules = _module_candidates(root)
    for c in ruff_c + vul_c + mod_c:
        c["category"] = _category(c["path"])
    candidates = sorted(ruff_c + vul_c + mod_c,
                        key=lambda c: (c["path"], c.get("kind", ""), c.get("symbol", "")))
    by_cat = {}
    for c in candidates:
        by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1
    return {
        "schema_version": 2,
        "scanned_dirs": list(CODE_DIRS),
        "total_modules_scanned": n_modules,
        "tools_available": {
            "ruff": ruff_ok, "vulture": vulture_ok,
            "ruff_rules": list(RUFF_RULES),
            "vulture_kind_min_confidence": _VULTURE_KIND_MIN,
            "ruff_error": ruff_err, "vulture_error": vul_err,
        },
        "candidate_count": len(candidates),
        "candidates_by_kind": {
            "symbol": sum(1 for c in candidates if c["kind"] == "symbol"),
            "vulture": sum(1 for c in candidates if c["kind"] == "vulture"),
            "module": sum(1 for c in candidates if c["kind"] == "module"),
        },
        "candidates_by_category": by_cat,
        "candidates_high_confidence": sum(1 for c in candidates if c["confidence"] == "HIGH"),
        "candidates": candidates,
        "note": "IDENTIFY ONLY — deletion_allowed is always false. symbol=HIGH "
                "confidence (ruff F-codes); module=LOW confidence heuristic with "
                "recall limit (candidate==0 is NOT 'clean'). removal only after "
                "dry-run -> team audit -> small commit. Install vulture for "
                "AST-level unused function/class detection.",
    }


def main():
    try:  # Windows cp949 stdout would crash on non-ASCII; emit UTF-8 (R1)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    result = scan(root)
    out_dir = os.path.join(root, ".harness")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "dead_code_candidates.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    t = result["tools_available"]
    k = result["candidates_by_kind"]
    print("dead_code_scan: %d modules, %d candidates (symbol=%d vulture=%d module=%d) "
          "[ruff=%s vulture=%s] -> %s"
          % (result["total_modules_scanned"], result["candidate_count"],
             k["symbol"], k["vulture"], k["module"],
             t["ruff"], t["vulture"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
