from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest


GATEWAY_PATH = (
    Path(__file__).parents[1]
    / "docker"
    / "telegram-gateway"
    / "telegram_gateway.py"
)


@pytest.mark.parametrize("shutdown_signal", [signal.SIGTERM, signal.SIGINT])
def test_gateway_exits_cleanly_on_shutdown_signal(
    shutdown_signal: signal.Signals,
) -> None:
    environment = os.environ.copy()
    environment["TELEGRAM_GATEWAY_HOST"] = "127.0.0.1"
    environment["TELEGRAM_GATEWAY_PORT"] = "0"

    process = subprocess.Popen(
        [sys.executable, str(GATEWAY_PATH)],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        assert process.stdout is not None
        startup_line = process.stdout.readline()
        assert "Telegram gateway starting" in startup_line

        process.send_signal(shutdown_signal)
        return_code = process.wait(timeout=2)
        output = startup_line + process.stdout.read()

        assert return_code == 0
        assert (
            f"Shutdown signal received: signal={shutdown_signal.name}"
            in output
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
