#!/usr/bin/env python3
"""Operator CLI for the whole stack.

Named stack.py, not tsys.py: a module named tsys would shadow the tsys namespace
package and break every import below.

    python scripts/stack.py status
    python scripts/stack.py up openalgo|dashboard
    python scripts/stack.py down dashboard
    python scripts/stack.py kill on|off
    python scripts/stack.py trade NIFTY [--once]

Mirrors the reference monorepo's scripts/commands/{start,stop,status}.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG_SRC = [
    ROOT / "packages" / p / "src"
    for p in ("config", "core", "domain", "broker", "tvclient", "journal", "executor")
]

SERVICES = {
    "openalgo": {
        "port": 5000,
        "cwd": ROOT / "packages" / "openalgo",
        "cmd": ["uv", "run", "app.py"],
    },
    "dashboard": {
        "port": 5050,
        "cwd": ROOT,
        "cmd": [sys.executable, str(ROOT / "apps" / "dashboard" / "server.py")],
    },
}

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def _env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = [*map(str, PKG_SRC)]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def cmd_status(_: argparse.Namespace) -> int:
    print(f"{DIM}service     port   state{RESET}")
    for name, spec in SERVICES.items():
        up = _port_open(spec["port"])
        mark = f"{GREEN}running{RESET}" if up else f"{RED}stopped{RESET}"
        print(f"{name:<11} {spec['port']:<6} {mark}")

    sys.path[:0] = [str(p) for p in PKG_SRC]
    from tsys.config import settings  # noqa: PLC0415 - needs the path set above

    kill = settings.risk.kill_switch_file
    print()
    print(f"mode          {settings.risk.mode.value}{'  (LIVE)' if settings.risk.is_live else ''}")
    print(f"broker key    {'configured' if settings.broker.configured else 'not set'}")
    print(f"kill switch   {'ENGAGED' if kill.exists() else 'clear'}  ({kill})")
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    spec = SERVICES[args.service]
    if _port_open(spec["port"]):
        print(f"{args.service} is already listening on {spec['port']}")
        return 0
    print(f"starting {args.service} on {spec['port']}...")
    subprocess.Popen(spec["cmd"], cwd=str(spec["cwd"]), env=_env())
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    spec = SERVICES[args.service]
    if not _port_open(spec["port"]):
        print(f"{args.service} is not running")
        return 0
    if sys.platform == "win32":
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
        pids = {
            line.split()[-1]
            for line in out.splitlines()
            if f":{spec['port']} " in line and "LISTENING" in line
        }
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", str(spec["cmd"][-1])], capture_output=True)
    print(f"stopped {args.service}")
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    sys.path[:0] = [str(p) for p in PKG_SRC]
    from tsys.config import settings  # noqa: PLC0415

    kill = settings.risk.kill_switch_file
    if args.state == "on":
        kill.parent.mkdir(parents=True, exist_ok=True)
        kill.write_text("engaged from scripts/tsys.py\n")
        print(f"kill switch ENGAGED -> {kill}\nno order path will place while this file exists.")
    else:
        kill.unlink(missing_ok=True)
        print("kill switch released")
    return 0


def cmd_trade(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "-m", "tsys.executor.main"]
    for index in args.index:
        cmd += ["--index", index]
    if args.once:
        cmd.append("--once")
    return subprocess.run(cmd, cwd=str(ROOT), env=_env()).returncode


def main() -> int:
    p = argparse.ArgumentParser(prog="stack", description="Trading system operator CLI.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show every service and guard").set_defaults(fn=cmd_status)

    up = sub.add_parser("up", help="start a service")
    up.add_argument("service", choices=sorted(SERVICES))
    up.set_defaults(fn=cmd_up)

    down = sub.add_parser("down", help="stop a service")
    down.add_argument("service", choices=sorted(SERVICES))
    down.set_defaults(fn=cmd_down)

    kill = sub.add_parser("kill", help="engage or release the kill switch")
    kill.add_argument("state", choices=["on", "off"])
    kill.set_defaults(fn=cmd_kill)

    trade = sub.add_parser("trade", help="run the executor")
    trade.add_argument("index", nargs="+")
    trade.add_argument("--once", action="store_true")
    trade.set_defaults(fn=cmd_trade)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
