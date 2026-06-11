"""Постоянный scheduler для автопубликации Telegram-постов.

Ручная проверка одного запуска:

docker compose run --rm scheduler python scripts/run_scheduler.py --run-once

Постоянный режим:

docker compose up -d scheduler

Расписание по умолчанию:

00:05 UTC
04:05 UTC
08:05 UTC
12:05 UTC
16:05 UTC
20:05 UTC
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
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
DEFAULT_CRON_HOURS = "0,4,8,12,16,20"
DEFAULT_CRON_MINUTE = "5"
DEFAULT_TIMEZONE = "UTC"

LOGGER = logging.getLogger("crypto_telegram_scheduler")


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


def build_publication_command(
    *,
    symbol: str,
    interval: str,
    notify: bool,
) -> list[str]:
    """Сформировать команду запуска полной publication job."""

    command = [
        sys.executable,
        str(PUBLICATION_JOB_SCRIPT),
        symbol,
        interval,
        "--send",
    ]

    if notify:
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
    *,
    symbol: str,
    interval: str,
    notify: bool,
) -> None:
    """Функция, которую вызывает APScheduler."""

    LOGGER.info(
        "Publication job started: symbol=%s interval=%s notify=%s",
        symbol,
        interval,
        notify,
    )

    command = build_publication_command(
        symbol=symbol,
        interval=interval,
        notify=notify,
    )

    run_command(command)

    LOGGER.info(
        "Publication job finished: symbol=%s interval=%s",
        symbol,
        interval,
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
            "Run one publication job immediately and exit. "
            "Useful for manual testing."
        ),
    )

    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print scheduler configuration and exit.",
    )

    return parser.parse_args()


def load_scheduler_config() -> dict[str, object]:
    """Загрузить настройки scheduler из environment."""

    symbol = get_env_value(
        "SCHEDULER_SYMBOL",
        DEFAULT_SYMBOL,
    ).upper()

    interval = get_env_value(
        "SCHEDULER_INTERVAL",
        DEFAULT_INTERVAL,
    )

    cron_hours = get_env_value(
        "SCHEDULER_CRON_HOURS",
        DEFAULT_CRON_HOURS,
    )

    cron_minute = get_env_value(
        "SCHEDULER_CRON_MINUTE",
        DEFAULT_CRON_MINUTE,
    )

    timezone_name = get_env_value(
        "SCHEDULER_TIMEZONE",
        DEFAULT_TIMEZONE,
    )

    notify_raw = get_env_value(
        "SCHEDULER_NOTIFY",
        "false",
    ).lower()

    notify = notify_raw in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }

    timezone_obj = ZoneInfo(timezone_name)

    return {
        "symbol": symbol,
        "interval": interval,
        "cron_hours": cron_hours,
        "cron_minute": cron_minute,
        "timezone_name": timezone_name,
        "timezone": timezone_obj,
        "notify": notify,
    }


def print_scheduler_config(
    config: dict[str, object],
) -> None:
    """Показать настройки scheduler без секретов."""

    print("Scheduler configuration:")
    print(f"  symbol: {config['symbol']}")
    print(f"  interval: {config['interval']}")
    print(f"  cron_hours: {config['cron_hours']}")
    print(f"  cron_minute: {config['cron_minute']}")
    print(f"  timezone: {config['timezone_name']}")
    print(f"  notify: {config['notify']}")


def main() -> None:
    """Точка входа."""

    setup_logging()

    args = parse_arguments()
    config = load_scheduler_config()

    if args.print_config:
        print_scheduler_config(config)
        return

    symbol = str(config["symbol"])
    interval = str(config["interval"])
    cron_hours = str(config["cron_hours"])
    cron_minute = str(config["cron_minute"])
    timezone_obj = config["timezone"]
    timezone_name = str(config["timezone_name"])
    notify = bool(config["notify"])

    if args.run_once:
        LOGGER.info("Running scheduler job once and exiting.")
        publication_job(
            symbol=symbol,
            interval=interval,
            notify=notify,
        )
        return

    scheduler = BlockingScheduler(
        timezone=timezone_obj,
    )

    scheduler.add_listener(
        scheduler_event_listener,
        EVENT_JOB_EXECUTED
        | EVENT_JOB_ERROR
        | EVENT_JOB_MISSED,
    )

    trigger = CronTrigger(
        hour=cron_hours,
        minute=cron_minute,
        timezone=timezone_obj,
    )
 
    next_run_time = trigger.get_next_fire_time(
    None,
    datetime.now(timezone_obj),
    )

    job = scheduler.add_job(
        publication_job,
        trigger=trigger,
        id="btc_1h_telegram_publication",
        name="BTCUSDT 1H Telegram publication",
        kwargs={
            "symbol": symbol,
            "interval": interval,
            "notify": notify,
        },
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
        replace_existing=True,
    )

    LOGGER.info(
        "Scheduler started: symbol=%s interval=%s "
        "cron_hours=%s cron_minute=%s timezone=%s notify=%s",
        symbol,
        interval,
        cron_hours,
        cron_minute,
        timezone_name,
        notify,
    )

    LOGGER.info(
        "Next run time: %s",
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