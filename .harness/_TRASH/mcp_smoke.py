#!/usr/bin/env python
"""Minimal MCP stdio client: spawn a server command, do initialize + tools/list, print tool names.

Verification-only (not part of runtime). Proves a stdio MCP server boots and exposes tools
through our launcher. Never prints secrets. Usage:
  py scripts/mcp_smoke.py py scripts/mcp_env_launch.py postgres
"""
from __future__ import annotations
import json, queue, subprocess, sys, threading, time

PROTO = "2024-11-05"


def _reader(stdout, q: "queue.Queue[str]") -> None:
    for line in stdout:
        q.put(line)
    q.put("")  # EOF marker


def smoke(cmd: list[str], timeout: float = 90.0) -> int:
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1,
                         encoding="utf-8", errors="replace")
    q: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=_reader, args=(p.stdout, q), daemon=True).start()

    def send(obj: dict) -> None:
        p.stdin.write(json.dumps(obj) + "\n"); p.stdin.flush()

    def wait_for(want_id: int, deadline: float):
        while time.time() < deadline:
            try:
                line = q.get(timeout=deadline - time.time())
            except queue.Empty:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == want_id:
                return msg
        return None

    end = time.time() + timeout
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": PROTO, "capabilities": {},
                         "clientInfo": {"name": "mcp-smoke", "version": "0"}}})
        init = wait_for(1, end)
        if not init or "result" not in init:
            print("  initialize: FAIL (no result)"); return 2
        srv = init["result"].get("serverInfo", {})
        print(f"  initialize: OK server={srv.get('name','?')} v={srv.get('version','?')}")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tl = wait_for(2, end)
        if not tl or "result" not in tl:
            print("  tools/list: FAIL (no result)"); return 3
        tools = [t["name"] for t in tl["result"].get("tools", [])]
        print(f"  tools/list: OK count={len(tools)}")
        print("  tools:", ", ".join(tools[:12]) + (" ..." if len(tools) > 12 else ""))
        return 0 if tools else 4
    finally:
        try:
            p.terminate(); p.wait(timeout=10)
        except Exception:
            p.kill()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: mcp_smoke.py <server cmd...>"); raise SystemExit(1)
    raise SystemExit(smoke(sys.argv[1:]))
