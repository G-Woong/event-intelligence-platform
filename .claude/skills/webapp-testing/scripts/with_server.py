#!/usr/bin/env python
"""Boot backend(:8000)+frontend(:3000), wait for readiness, run a test cmd, then tear down.

Adapted from anthropics/skills/webapp-testing (Apache-2.0) for this project's stack.
localhost only — no external network. Does NOT read .env values (servers load their own).

Usage:
  python with_server.py --backend "uvicorn app.main:app --port 8000" --backend-port 8000 \
                        --frontend "npm run dev" --frontend-cwd frontend --frontend-port 3000 \
                        -- python e2e_test.py
"""
from __future__ import annotations
import argparse, subprocess, sys, time, urllib.request, socket


def _wait_port(port: int, timeout: float = 60.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend"); p.add_argument("--backend-port", type=int)
    p.add_argument("--backend-cwd", default=".")
    p.add_argument("--frontend"); p.add_argument("--frontend-port", type=int)
    p.add_argument("--frontend-cwd", default="frontend")
    p.add_argument("test", nargs=argparse.REMAINDER)
    a = p.parse_args()

    procs: list[subprocess.Popen] = []
    try:
        if a.backend:
            procs.append(subprocess.Popen(a.backend, shell=True, cwd=a.backend_cwd))
            if a.backend_port and not _wait_port(a.backend_port):
                print(f"backend :{a.backend_port} not ready", file=sys.stderr); return 2
        if a.frontend:
            procs.append(subprocess.Popen(a.frontend, shell=True, cwd=a.frontend_cwd))
            if a.frontend_port and not _wait_port(a.frontend_port):
                print(f"frontend :{a.frontend_port} not ready", file=sys.stderr); return 2

        test = a.test[1:] if a.test and a.test[0] == "--" else a.test
        if not test:
            print("no test command given", file=sys.stderr); return 1
        return subprocess.call(test)
    finally:
        for pr in reversed(procs):
            pr.terminate()
            try:
                pr.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pr.kill()


if __name__ == "__main__":
    raise SystemExit(main())
