"""Launch one or more real sandbox processes for evaluation scripts."""

from __future__ import annotations

import socket
import subprocess
import sys
import time

import httpx

from config_loader import REPO_ROOT


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_servers(count: int) -> tuple[list[subprocess.Popen], list[str]]:
    processes: list[subprocess.Popen] = []
    urls: list[str] = []
    used_ports: set[int] = set()
    try:
        for _ in range(count):
            port = free_port()
            while port in used_ports:
                port = free_port()
            used_ports.add(port)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "sandbox.serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=str(REPO_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            urls.append(f"http://127.0.0.1:{port}")
        deadline = time.time() + 30
        for url in urls:
            while True:
                if time.time() > deadline:
                    raise RuntimeError(f"sandbox did not start at {url}")
                try:
                    if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.15)
        return processes, urls
    except Exception:
        stop_servers(processes)
        raise


def stop_servers(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
