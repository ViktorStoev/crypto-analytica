from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest


GATEWAY_PATH = (
    Path(__file__).parents[1]
    / "docker"
    / "telegram-gateway"
    / "telegram_gateway.py"
)


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_serving(port: int, timeout: float = 2) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=0.2,
            ) as sock:
                sock.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                response = sock.recv(1024)

            if response.startswith(b"HTTP/1.1 405"):
                return
        except OSError:
            time.sleep(0.01)

    pytest.fail("Gateway did not start serving before the timeout")


@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_gateway_exits_cleanly_on_shutdown_signal(
    shutdown_signal: signal.Signals,
) -> None:
    port = _unused_tcp_port()
    environment = os.environ.copy()
    environment["TELEGRAM_GATEWAY_HOST"] = "127.0.0.1"
    environment["TELEGRAM_GATEWAY_PORT"] = str(port)

    process = subprocess.Popen(
        [sys.executable, str(GATEWAY_PATH)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_until_serving(port)

        process.send_signal(shutdown_signal)
        output, _ = process.communicate(timeout=2)

        assert process.returncode == 0
        assert "Telegram gateway starting" in output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
