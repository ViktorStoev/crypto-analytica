from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from scripts import run_publication_job, run_scheduler


def test_scheduler_builds_daily_summary_publication_command() -> None:
    job = run_scheduler.ScheduledPublication(
        job_id="daily_summary",
        name="Daily summary",
        enabled=True,
        symbol="MARKET",
        interval="60",
        post_type="daily_summary",
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        cron_hours="7,19",
        cron_minute="10",
        timezone=ZoneInfo("UTC"),
        notify=False,
    )

    command = run_scheduler.build_publication_command(job)

    assert command[2:] == [
        "MARKET",
        "60",
        "--type",
        "daily_summary",
        "--send",
        "--symbols",
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    ]
    assert "--type" in command
    assert "--send" in command
    assert "--symbols" in command


def test_scheduler_daily_summary_is_disabled_by_default(monkeypatch) -> None:
    for name in [
        "SCHEDULER_DAILY_SUMMARY_ENABLED",
        "SCHEDULER_DAILY_SUMMARY_SYMBOLS",
    ]:
        monkeypatch.delenv(name, raising=False)

    jobs = run_scheduler.build_jobs()
    daily_summary = next(job for job in jobs if job.job_id == "daily_summary")

    assert daily_summary.enabled is False
    assert daily_summary.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def test_publication_job_parser_rejects_short_daily_summary_symbols(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_publication_job.py",
            "MARKET",
            "60",
            "--type",
            "daily_summary",
            "--symbols",
            "BTCUSDT",
            "ETHUSDT",
        ],
    )

    with pytest.raises(SystemExit):
        run_publication_job.parse_arguments()
