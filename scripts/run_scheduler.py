"""Multi-job scheduler for Telegram content publication.

Manual checks:

docker compose run --rm scheduler python scripts/run_scheduler.py --print-config
docker compose run --rm scheduler python scripts/run_scheduler.py --run-once --job snapshot

Permanent mode:

docker compose up -d scheduler
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
)
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_JOB_SCRIPT = PROJECT_ROOT / "scripts" / "run_publication_job.py"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "60"
DEFAULT_TIMEZONE = "UTC"

DEFAULT_SNAPSHOT_HOURS = "0,4,8,12,16,20"
DEFAULT_SNAPSHOT_MINUTE = "5"
DEFAULT_DEEP_DIVE_HOURS = "9,18"
DEFAULT_DEEP_DIVE_MINUTE = "20"
DEFAULT_ALERT_HOURS = "*"
DEFAULT_ALERT_MINUTE = "*/30"
DEFAULT_DAILY_SUMMARY_HOURS = "7,19"
DEFAULT_DAILY_SUMMARY_MINUTE = "10"
DEFAULT_DAILY_SUMMARY_SYMBOLS = "BTCUSDT ETHUSDT SOLUSDT"
DEFAULT_TUTORIAL_DAY_OF_WEEK = "mon,thu"
DEFAULT_TUTORIAL_HOURS = "11"
DEFAULT_TUTORIAL_MINUTE = "0"
DEFAULT_RELEASE_DAY_OF_WEEK = "fri"
DEFAULT_RELEASE_HOURS = "12"
DEFAULT_RELEASE_MINUTE = "0"

LOGGER = logging.getLogger("crypto_telegram_scheduler")


@dataclass(frozen=True)
class ScheduledPublication:
    """One scheduled content publication job."""

    job_id: str
    name: str
    enabled: bool
    symbol: str
    interval: str
    post_type: str
    symbols: list[str]
    cron_hours: str
    cron_minute: str
    timezone: ZoneInfo
    notify: bool
    no_event_ok: bool = False
    day_of_week: str | None = None


class SchedulerJobError(RuntimeError):
    """Ошибка запуска publication job."""


def setup_logging() -> None:
    """Настроить простой stdout logging для Docker logs."""

    logging.basicConfig(
        level=os.getenv("SCHEDULER_LOG_LEVEL", "INFO").upper(),
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s: %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_env_value(
    name: str,
    default: str,
) -> str:
    """Получить строковую настройку из environment."""

    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return value.strip()


def get_env_bool(
    name: str,
    default: bool,
) -> bool:
    """Read boolean environment value."""

    raw_default = "true" if default else "false"
    raw_value = get_env_value(name, raw_default).lower()

    return raw_value in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def get_env_symbols(
    name: str,
    default: str,
) -> list[str]:
    """Read a comma- or space-separated symbol list."""

    raw_value = get_env_value(name, default)
    normalized = raw_value.replace(",", " ")

    return [
        item.strip().upper()
        for item in normalized.split()
        if item.strip()
    ]


def build_publication_command(
    job: ScheduledPublication,
) -> list[str]:
    """Сформировать команду запуска полной publication job."""

    command = [
        sys.executable,
        str(PUBLICATION_JOB_SCRIPT),
        job.symbol,
        job.interval,
        "--type",
        job.post_type,
        "--send",
    ]

    if job.symbols:
        command.append("--symbols")
        command.extend(job.symbols)

    if job.no_event_ok:
        command.append("--no-event-ok")

    if job.notify:
        command.append("--notify")

    return command


def run_command(
    command: Sequence[str],
) -> None:
    """Запустить внешнюю команду и проверить код завершения."""

    command_for_log = " ".join(
        Path(part).name
        if part.endswith(".py")
        else part
        for part in command
    )

    LOGGER.info("Starting publication command: %s", command_for_log)

    started_at = datetime.now(timezone.utc)

    completed_process = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        check=False,
    )

    finished_at = datetime.now(timezone.utc)
    duration = (finished_at - started_at).total_seconds()

    if completed_process.returncode != 0:
        raise SchedulerJobError(
            "Publication command failed: "
            f"exit_code={completed_process.returncode}, "
            f"duration_seconds={duration:.2f}"
        )

    LOGGER.info(
        "Publication command completed successfully: "
        "duration_seconds=%.2f",
        duration,
    )


def publication_job(
    job: ScheduledPublication,
) -> None:
    """Function called by APScheduler."""

    LOGGER.info(
        "Publication job started: "
        "job_id=%s symbol=%s interval=%s post_type=%s symbols=%s "
        "no_event_ok=%s notify=%s",
        job.job_id,
        job.symbol,
        job.interval,
        job.post_type,
        ",".join(job.symbols) if job.symbols else "-",
        job.no_event_ok,
        job.notify,
    )

    command = build_publication_command(job)
    run_command(command)

    LOGGER.info(
        "Publication job finished: job_id=%s post_type=%s",
        job.job_id,
        job.post_type,
    )


def scheduler_event_listener(event) -> None:
    """Логировать результат запуска job."""

    if event.code == EVENT_JOB_EXECUTED:
        LOGGER.info(
            "Scheduler event: job executed successfully, job_id=%s",
            event.job_id,
        )
        return

    if event.code == EVENT_JOB_ERROR:
        LOGGER.exception(
            "Scheduler event: job failed, job_id=%s",
            event.job_id,
            exc_info=event.exception,
        )
        return

    if event.code == EVENT_JOB_MISSED:
        LOGGER.warning(
            "Scheduler event: job missed, job_id=%s",
            event.job_id,
        )
        return


def parse_arguments() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""

    parser = argparse.ArgumentParser(
        description="Run crypto-analytica Telegram scheduler."
    )

    parser.add_argument(
        "--run-once",
        action="store_true",
        help=(
            "Run enabled publication jobs immediately and exit. "
            "Use --job to run only one job."
        ),
    )

    parser.add_argument(
        "--job",
        help=(
            "Limit --run-once to one job id: snapshot, deep_dive, "
            "alert, daily_summary, tutorial, release_note."
        ),
    )

    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print scheduler configuration and exit.",
    )

    return parser.parse_args()


def build_jobs() -> list[ScheduledPublication]:
    """Load scheduled publication jobs from environment."""

    timezone_name = get_env_value(
        "SCHEDULER_TIMEZONE",
        DEFAULT_TIMEZONE,
    )
    timezone_obj = ZoneInfo(timezone_name)

    global_symbol = get_env_value(
        "SCHEDULER_SYMBOL",
        DEFAULT_SYMBOL,
    ).upper()
    global_interval = get_env_value(
        "SCHEDULER_INTERVAL",
        DEFAULT_INTERVAL,
    )
    global_notify = get_env_bool(
        "SCHEDULER_NOTIFY",
        False,
    )

    return [
        ScheduledPublication(
            job_id="snapshot",
            name="Market snapshot",
            enabled=get_env_bool("SCHEDULER_SNAPSHOT_ENABLED", True),
            symbol=get_env_value(
                "SCHEDULER_SNAPSHOT_SYMBOL",
                global_symbol,
            ).upper(),
            interval=get_env_value(
                "SCHEDULER_SNAPSHOT_INTERVAL",
                global_interval,
            ),
            post_type="market_snapshot",
            symbols=[],
            cron_hours=get_env_value(
                "SCHEDULER_SNAPSHOT_CRON_HOURS",
                DEFAULT_SNAPSHOT_HOURS,
            ),
            cron_minute=get_env_value(
                "SCHEDULER_SNAPSHOT_CRON_MINUTE",
                DEFAULT_SNAPSHOT_MINUTE,
            ),
            timezone=timezone_obj,
            notify=get_env_bool(
                "SCHEDULER_SNAPSHOT_NOTIFY",
                global_notify,
            ),
        ),
        ScheduledPublication(
            job_id="deep_dive",
            name="Deep dive",
            enabled=get_env_bool("SCHEDULER_DEEP_DIVE_ENABLED", True),
            symbol=get_env_value(
                "SCHEDULER_DEEP_DIVE_SYMBOL",
                global_symbol,
            ).upper(),
            interval=get_env_value(
                "SCHEDULER_DEEP_DIVE_INTERVAL",
                global_interval,
            ),
            post_type="deep_dive",
            symbols=[],
            cron_hours=get_env_value(
                "SCHEDULER_DEEP_DIVE_CRON_HOURS",
                DEFAULT_DEEP_DIVE_HOURS,
            ),
            cron_minute=get_env_value(
                "SCHEDULER_DEEP_DIVE_CRON_MINUTE",
                DEFAULT_DEEP_DIVE_MINUTE,
            ),
            timezone=timezone_obj,
            notify=get_env_bool(
                "SCHEDULER_DEEP_DIVE_NOTIFY",
                global_notify,
            ),
        ),
        ScheduledPublication(
            job_id="alert",
            name="Event alert scan",
            enabled=get_env_bool("SCHEDULER_ALERT_ENABLED", True),
            symbol=get_env_value(
                "SCHEDULER_ALERT_SYMBOL",
                global_symbol,
            ).upper(),
            interval=get_env_value(
                "SCHEDULER_ALERT_INTERVAL",
                global_interval,
            ),
            post_type="alert",
            symbols=[],
            cron_hours=get_env_value(
                "SCHEDULER_ALERT_CRON_HOURS",
                DEFAULT_ALERT_HOURS,
            ),
            cron_minute=get_env_value(
                "SCHEDULER_ALERT_CRON_MINUTE",
                DEFAULT_ALERT_MINUTE,
            ),
            timezone=timezone_obj,
            notify=get_env_bool(
                "SCHEDULER_ALERT_NOTIFY",
                global_notify,
            ),
            no_event_ok=get_env_bool(
                "SCHEDULER_ALERT_NO_EVENT_OK",
                True,
            ),
        ),
        ScheduledPublication(
            job_id="daily_summary",
            name="Daily summary",
            enabled=get_env_bool("SCHEDULER_DAILY_SUMMARY_ENABLED", False),
            symbol="MARKET",
            interval=get_env_value(
                "SCHEDULER_DAILY_SUMMARY_INTERVAL",
                global_interval,
            ),
            post_type="daily_summary",
            symbols=get_env_symbols(
                "SCHEDULER_DAILY_SUMMARY_SYMBOLS",
                DEFAULT_DAILY_SUMMARY_SYMBOLS,
            ),
            cron_hours=get_env_value(
                "SCHEDULER_DAILY_SUMMARY_CRON_HOURS",
                DEFAULT_DAILY_SUMMARY_HOURS,
            ),
            cron_minute=get_env_value(
                "SCHEDULER_DAILY_SUMMARY_CRON_MINUTE",
                DEFAULT_DAILY_SUMMARY_MINUTE,
            ),
            timezone=timezone_obj,
            notify=get_env_bool(
                "SCHEDULER_DAILY_SUMMARY_NOTIFY",
                global_notify,
            ),
        ),
        ScheduledPublication(
            job_id="tutorial",
            name="RSI tutorial",
            enabled=get_env_bool("SCHEDULER_TUTORIAL_ENABLED", False),
            symbol="EDUCATION",
            interval="static",
            post_type="rsi_tutorial",
            symbols=[],
            cron_hours=get_env_value(
                "SCHEDULER_TUTORIAL_CRON_HOURS",
                DEFAULT_TUTORIAL_HOURS,
            ),
            cron_minute=get_env_value(
                "SCHEDULER_TUTORIAL_CRON_MINUTE",
                DEFAULT_TUTORIAL_MINUTE,
            ),
            day_of_week=get_env_value(
                "SCHEDULER_TUTORIAL_DAY_OF_WEEK",
                DEFAULT_TUTORIAL_DAY_OF_WEEK,
            ),
            timezone=timezone_obj,
            notify=get_env_bool(
                "SCHEDULER_TUTORIAL_NOTIFY",
                global_notify,
            ),
        ),
        ScheduledPublication(
            job_id="release_note",
            name="Release note",
            enabled=get_env_bool("SCHEDULER_RELEASE_NOTE_ENABLED", False),
            symbol="PROJECT",
            interval="static",
            post_type="release_note",
            symbols=[],
            cron_hours=get_env_value(
                "SCHEDULER_RELEASE_NOTE_CRON_HOURS",
                DEFAULT_RELEASE_HOURS,
            ),
            cron_minute=get_env_value(
                "SCHEDULER_RELEASE_NOTE_CRON_MINUTE",
                DEFAULT_RELEASE_MINUTE,
            ),
            day_of_week=get_env_value(
                "SCHEDULER_RELEASE_NOTE_DAY_OF_WEEK",
                DEFAULT_RELEASE_DAY_OF_WEEK,
            ),
            timezone=timezone_obj,
            notify=get_env_bool(
                "SCHEDULER_RELEASE_NOTE_NOTIFY",
                global_notify,
            ),
        ),
    ]


def make_trigger(job: ScheduledPublication) -> CronTrigger:
    """Build APScheduler cron trigger for one job."""

    kwargs = {
        "hour": job.cron_hours,
        "minute": job.cron_minute,
        "timezone": job.timezone,
    }

    if job.day_of_week:
        kwargs["day_of_week"] = job.day_of_week

    return CronTrigger(**kwargs)


def print_scheduler_config(
    jobs: list[ScheduledPublication],
) -> None:
    """Показать настройки scheduler без секретов."""

    print("Scheduler jobs:")

    for job in jobs:
        day = job.day_of_week or "*"
        symbols = ",".join(job.symbols) if job.symbols else "-"
        print(
            f"  {job.job_id}: enabled={job.enabled} "
            f"type={job.post_type} symbol={job.symbol} symbols={symbols} "
            f"interval={job.interval} cron={day} {job.cron_hours}:{job.cron_minute} "
            f"notify={job.notify} no_event_ok={job.no_event_ok}"
        )


def enabled_jobs(
    jobs: list[ScheduledPublication],
    job_id: str | None,
) -> list[ScheduledPublication]:
    """Filter enabled jobs, optionally by id."""

    result = [
        job
        for job in jobs
        if job.enabled and (job_id is None or job.job_id == job_id)
    ]

    if job_id is not None and not any(job.job_id == job_id for job in jobs):
        raise SchedulerJobError(
            f"Unknown scheduler job id: {job_id}"
        )

    return result


def main() -> None:
    """Точка входа."""

    setup_logging()

    args = parse_arguments()
    jobs = build_jobs()

    if args.print_config:
        print_scheduler_config(jobs)
        return

    selected_jobs = enabled_jobs(jobs, args.job)

    if not selected_jobs:
        LOGGER.warning(
            "No enabled scheduler jobs selected. job_filter=%s",
            args.job,
        )
        return

    if args.run_once:
        LOGGER.info(
            "Running scheduler jobs once and exiting: jobs=%s",
            ",".join(job.job_id for job in selected_jobs),
        )
        for job in selected_jobs:
            publication_job(job)
        return

    scheduler = BlockingScheduler(
        timezone=selected_jobs[0].timezone,
    )

    scheduler.add_listener(
        scheduler_event_listener,
        EVENT_JOB_EXECUTED
        | EVENT_JOB_ERROR
        | EVENT_JOB_MISSED,
    )

    for job in selected_jobs:
        trigger = make_trigger(job)
        next_run_time = trigger.get_next_fire_time(
            None,
            datetime.now(job.timezone),
        )

        scheduler.add_job(
            publication_job,
            trigger=trigger,
            id=job.job_id,
            name=job.name,
            args=[job],
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
            replace_existing=True,
        )

        LOGGER.info(
            "Scheduled job: id=%s type=%s symbol=%s symbols=%s "
            "cron_hours=%s cron_minute=%s day_of_week=%s next_run=%s",
            job.job_id,
            job.post_type,
            job.symbol,
            ",".join(job.symbols) if job.symbols else "-",
            job.cron_hours,
            job.cron_minute,
            job.day_of_week or "*",
            next_run_time,
        )

    def handle_shutdown(signum, frame) -> None:
        LOGGER.info(
            "Shutdown signal received: signal=%s",
            signum,
        )
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    scheduler.start()


if __name__ == "__main__":
    main()
