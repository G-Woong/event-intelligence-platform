#!/usr/bin/env python
"""MCP stdio launcher that loads project .env at runtime, then execs the real server.

Why: Claude Code resolves ${VAR} in .mcp.json from its OWN process env and does NOT
auto-load the project .env. This launcher reads .env at spawn time (the same way the app's
pydantic-settings does) so MCP servers get DATABASE_URL / REDIS_URL / GITHUB_PAT without
the assistant ever reading secret VALUES and without hardcoding anything in .mcp.json.

It also rewrites docker-internal hostnames (postgres/redis) -> 127.0.0.1 and strips the
SQLAlchemy +asyncpg driver suffix, because MCP servers run on the HOST (compose exposes
127.0.0.1:5432 / 127.0.0.1:6379) while the app runs inside the compose network.

Usage (server mode, used by .mcp.json):  py scripts/mcp_env_launch.py <postgres|redis|github>
Usage (check mode, used for verification): py scripts/mcp_env_launch.py <target> --check
  --check NEVER prints secret values: only host:port reachability and (for github) the login.
"""
from __future__ import annotations
import os, re, sys, shutil, socket, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    # utf-8-sig: strip a Windows-editor BOM so the first key isn't "﻿KEY".
    for raw in p.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # .env wins over a MISSING or EMPTY process env var ("빈값=DEFAULT" 계약).
        # A real non-empty process env var still takes precedence.
        if v and not os.environ.get(k):
            os.environ[k] = v


def _host_local(url: str) -> str:
    # docker-network service hostnames -> host loopback (compose exposes 127.0.0.1 ports)
    url = re.sub(r"@postgres:", "@127.0.0.1:", url)
    url = re.sub(r"@redis:", "@127.0.0.1:", url)
    url = re.sub(r"//postgres:", "//127.0.0.1:", url)
    url = re.sub(r"//redis:", "//127.0.0.1:", url)
    # Force IPv4: on Windows 'localhost' resolves ::1 first; compose binds 127.0.0.1 (IPv4)
    # only, so the ::1 attempt stalls ~30s and overruns the MCP startup timeout. (postgres init
    # 36.5s@localhost vs 1.5s@127.0.0.1, measured.)
    url = re.sub(r"@localhost:", "@127.0.0.1:", url)
    url = re.sub(r"//localhost:", "//127.0.0.1:", url)
    return url


# config.py 의 "빈값=DEFAULT" 계약과 동일한 dev 기본값(이미 repo 의 compose/config 에 공개된 dev 자격).
_PG_DEFAULT = "postgresql+asyncpg://event_user:event_pass@127.0.0.1:5432/event_intel"


def pg_uri() -> str:
    u = os.environ.get("DATABASE_URL", "").strip() or _PG_DEFAULT  # 빈값 -> 코드 기본값
    u = re.sub(r"^postgresql\+\w+://", "postgresql://", u)  # strip +asyncpg/+psycopg2
    return _host_local(u)


def redis_uri() -> str:
    return _host_local(os.environ.get("REDIS_MCP_URL") or os.environ.get("REDIS_URL", ""))


def gh_token() -> str:
    # 사용자가 쓸 수 있는 흔한 키 이름들을 모두 수용(첫 비공백 값).
    for k in ("GITHUB_PAT", "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _host_port(uri: str, default_port: int) -> tuple[str, int]:
    m = re.search(r"//(?:[^@/]*@)?([^:/]+)(?::(\d+))?", uri)
    if not m:
        return "", default_port
    return m.group(1), int(m.group(2) or default_port)


def _probe_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check(target: str) -> int:
    if target == "postgres":
        uri = pg_uri()
        if not uri:
            print("postgres CHECK: FAIL - DATABASE_URL not found in .env"); return 1
        h, p = _host_port(uri, 5432)
        ok = _probe_tcp(h, p)
        print(f"postgres CHECK: env=loaded host={h}:{p} reachable={ok} (uri masked)")
        return 0 if ok else 2
    if target == "redis":
        uri = redis_uri()
        if not uri:
            print("redis CHECK: FAIL - REDIS_MCP_URL/REDIS_URL not found in .env"); return 1
        h, p = _host_port(uri, 6379)
        ok = _probe_tcp(h, p)
        print(f"redis CHECK: env=loaded host={h}:{p} reachable={ok} (uri masked)")
        return 0 if ok else 2
    if target == "github":
        tok = gh_token()
        if not tok:
            print("github CHECK: FAIL - no token found (tried GITHUB_PAT/GITHUB_TOKEN/GH_TOKEN/GITHUB_PERSONAL_ACCESS_TOKEN)"); return 1
        import json, urllib.request
        try:
            req = urllib.request.Request(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {tok}", "User-Agent": "mcp-env-check",
                         "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                login = json.load(r).get("login", "?")
                scopes = r.headers.get("x-oauth-scopes")
            print(f"github CHECK: token=present(len={len(tok)}) valid=True login={login} "
                  f"classic_scopes={scopes or '(fine-grained/none)'}")
            return 0
        except Exception as e:  # noqa: BLE001 - report masked, never print token
            print(f"github CHECK: token=present(len={len(tok)}) valid=False reason={type(e).__name__}")
            return 2
    print(f"unknown target: {target}"); return 1


def serve(target: str) -> int:
    if target == "postgres":
        uri = pg_uri()
        if not uri:
            print("postgres: DATABASE_URL empty and no default", file=sys.stderr); return 1
        os.environ["DATABASE_URI"] = uri
        uvx = shutil.which("uvx") or "uvx"
        cmd = [uvx, "postgres-mcp", "--access-mode=restricted"]
    elif target == "redis":
        url = redis_uri()
        if not url:
            print("redis: REDIS_MCP_URL/REDIS_URL not set", file=sys.stderr); return 1
        uvx = shutil.which("uvx") or "uvx"
        # NOTE: --url places creds in argv. Current dev redis is no-auth; if an ACL
        # password is used, prefer REDIS_* env vars to avoid process-list exposure.
        cmd = [uvx, "--from", "redis-mcp-server@latest", "redis-mcp-server", "--url", url]
    elif target == "github":
        # 공식 Go 서버 + --read-only: 쓰기 도구를 서버 레벨에서 숨김(토큰 scope 의존 X, push 금지 정책 정합).
        # 토큰은 -e 로 launcher env 에서 전달(argv 노출 0). Docker 필요.
        tok = gh_token()
        if not tok:
            print("github: no token (GITHUB_PAT/GITHUB_TOKEN/GH_TOKEN/GITHUB_PERSONAL_ACCESS_TOKEN)",
                  file=sys.stderr); return 1
        os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"] = tok
        cmd = ["docker", "run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
               "ghcr.io/github/github-mcp-server", "stdio", "--read-only"]
    else:
        print(f"unknown target: {target}", file=sys.stderr); return 1
    # inherit stdio so the MCP protocol passes through to the child (same pattern as cmd /c npx)
    return subprocess.run(cmd, env=os.environ).returncode


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: mcp_env_launch.py <postgres|redis|github> [--check]", file=sys.stderr)
        return 1
    load_env()
    target = sys.argv[1]
    if "--check" in sys.argv[2:]:
        return check(target)
    return serve(target)


if __name__ == "__main__":
    raise SystemExit(main())
