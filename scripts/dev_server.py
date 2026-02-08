from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def pids_listening_on_port(port: int) -> list[int]:
    if os.name != "nt":
        return []
    out = subprocess.check_output(["netstat", "-ano"], text=True, encoding="utf-8", errors="ignore")
    pids: list[int] = []
    for line in out.splitlines():
        if f":{port}" not in line or "LISTENING" not in line:
            continue
        cols = line.split()
        if not cols:
            continue
        try:
            pids.append(int(cols[-1]))
        except ValueError:
            continue
    return sorted(set(pids))


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], text=True, encoding="utf-8", errors="ignore")
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def start(root: Path, host: str, port: int) -> int:
    pid_path = root / "dev_server.pid"
    out_path = root / "dev_server.out.log"
    err_path = root / "dev_server.err.log"

    if pid_path.exists():
        try:
            existing = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            existing = 0
        if is_pid_running(existing):
            print(f"already running pid={existing}")
            return 0
        pid_path.unlink(missing_ok=True)

    out_path.write_text("", encoding="utf-8")
    err_path.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "app.backend.main:app", "--host", host, "--port", str(port), "--reload"],
        cwd=str(root),
        stdout=out_path.open("a", encoding="utf-8"),
        stderr=err_path.open("a", encoding="utf-8"),
        creationflags=0x00000008 if os.name == "nt" else 0,
    )
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    print(f"started pid={proc.pid}")

    for _ in range(30):
        if is_port_open(host, port):
            print(f"up http://{host}:{port}")
            return 0
        time.sleep(0.2)
    print("warning: process started but health port not ready yet")
    return 0


def stop(root: Path) -> int:
    pid_path = root / "dev_server.pid"
    if not pid_path.exists():
        print("not running (no pid file)")
        return 0
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid = 0
    stopped_any = False
    if pid and is_pid_running(pid):
        try:
            if os.name == "nt":
                subprocess.check_call(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"stopped pid={pid}")
            stopped_any = True
        except Exception:
            pass

    for listen_pid in pids_listening_on_port(8000):
        try:
            subprocess.check_call(
                ["taskkill", "/PID", str(listen_pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"stopped pid={listen_pid} (port 8000)")
            stopped_any = True
        except Exception:
            continue

    if not stopped_any:
        print("not running (stale pid)")
    pid_path.unlink(missing_ok=True)
    return 0


def status(root: Path, host: str, port: int) -> int:
    pid_path = root / "dev_server.pid"
    pid = None
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None

    running = is_pid_running(pid or 0)
    listen_pids = pids_listening_on_port(port)
    port_up = is_port_open(host, port)
    print(
        f"pid={pid if pid is not None else 'none'} running={running} port_up={port_up} "
        f"listen_pids={listen_pids}"
    )
    print(f"url=http://{host}:{port}/ui")
    print(f"logs={root / 'dev_server.out.log'} | {root / 'dev_server.err.log'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local dev server.")
    parser.add_argument("command", choices=["start", "stop", "status", "restart"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    if args.command == "start":
        return start(root, args.host, args.port)
    if args.command == "stop":
        return stop(root)
    if args.command == "status":
        return status(root, args.host, args.port)
    if args.command == "restart":
        stop(root)
        return start(root, args.host, args.port)
    return 1


if __name__ == "__main__":
    sys.exit(main())
