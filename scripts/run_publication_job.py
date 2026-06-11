"""Полный цикл подготовки и публикации Telegram-поста.

Последовательность:

1. Получить свежие данные Bybit.
2. Пересчитать индикаторы.
3. Построить анализ и Telegram-пост.
4. При наличии --send опубликовать пост.
5. Защита от дублей выполняется publication_service.

Предварительная проверка без отправки:

docker compose run --rm app \
    python scripts/run_publication_job.py BTCUSDT 60

Реальная тихая публикация:

docker compose run --rm app \
    python scripts/run_publication_job.py BTCUSDT 60 --send

Публикация с уведомлением:

docker compose run --rm app \
    python scripts/run_publication_job.py \
    BTCUSDT 60 --send --notify
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Текущий collect_market_once.py собирает именно часовые свечи.
# Поэтому пока честно ограничиваем job интервалом 60.
SUPPORTED_INTERVALS = {"60"}


class PublicationJobError(RuntimeError):
    """Ошибка одного из шагов полного цикла публикации."""


def parse_arguments() -> argparse.Namespace:
    """Прочитать аргументы командной строки."""

    parser = argparse.ArgumentParser(
        description=(
            "Collect market data, calculate indicators, "
            "build a Telegram post and optionally publish it."
        )
    )

    parser.add_argument(
        "symbol",
        help="Bybit symbol, for example BTCUSDT.",
    )

    parser.add_argument(
        "interval",
        help="Candle interval. Currently supported: 60.",
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help=(
            "Actually publish the post. "
            "Without this flag, the post is only previewed."
        ),
    )

    parser.add_argument(
        "--notify",
        action="store_true",
        help=(
            "Enable Telegram subscriber notification. "
            "Can only be used together with --send."
        ),
    )

    args = parser.parse_args()

    args.symbol = args.symbol.upper()

    if args.interval not in SUPPORTED_INTERVALS:
        parser.error(
            "Only interval 60 is currently supported because "
            "collect_market_once.py collects 1H candles."
        )

    if args.notify and not args.send:
        parser.error(
            "--notify can only be used together with --send"
        )

    return args


def run_python_step(
    *,
    step_number: int,
    step_name: str,
    script_name: str,
    arguments: Sequence[str],
) -> None:
    """Запустить один Python-скрипт и проверить код завершения."""

    script_path = SCRIPTS_DIR / script_name

    if not script_path.is_file():
        raise PublicationJobError(
            f"Script not found: {script_path}"
        )

    command = [
        sys.executable,
        str(script_path),
        *arguments,
    ]

    print()
    print("=" * 70)
    print(f"STEP {step_number}: {step_name}")
    print("=" * 70)
    print(
        "Command: "
        f"python scripts/{script_name} "
        f"{' '.join(arguments)}"
    )
    print()

    completed_process = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    if completed_process.returncode != 0:
        raise PublicationJobError(
            f"Step {step_number} failed: {step_name}. "
            f"Exit code: {completed_process.returncode}"
        )

    print()
    print(
        f"Step {step_number} completed successfully: "
        f"{step_name}"
    )


def run_publication_job(
    *,
    symbol: str,
    interval: str,
    send: bool,
    notify: bool,
) -> None:
    """Выполнить полный последовательный цикл публикации."""

    started_at = datetime.now(timezone.utc)

    print("=" * 70)
    print("CRYPTO-ANALYTICA PUBLICATION JOB")
    print("=" * 70)
    print(f"Started at: {started_at:%Y-%m-%d %H:%M:%S} UTC")
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")
    print(f"Send enabled: {send}")
    print(f"Notifications enabled: {notify}")

    run_python_step(
        step_number=1,
        step_name="Collect fresh Bybit market data",
        script_name="collect_market_once.py",
        arguments=[symbol],
    )

    run_python_step(
        step_number=2,
        step_name="Calculate technical indicators",
        script_name="calculate_indicators.py",
        arguments=[symbol, interval],
    )

    publication_arguments = [
        symbol,
        interval,
    ]

    if send:
        publication_arguments.append("--send")

    if notify:
        publication_arguments.append("--notify")

    run_python_step(
        step_number=3,
        step_name=(
            "Build and publish Telegram post"
            if send
            else "Build Telegram post preview"
        ),
        script_name="send_telegram_post.py",
        arguments=publication_arguments,
    )

    finished_at = datetime.now(timezone.utc)
    duration = finished_at - started_at

    print()
    print("=" * 70)
    print("PUBLICATION JOB COMPLETED")
    print("=" * 70)
    print(
        f"Finished at: "
        f"{finished_at:%Y-%m-%d %H:%M:%S} UTC"
    )
    print(
        f"Duration: "
        f"{duration.total_seconds():.2f} seconds"
    )
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")

    if send:
        print(
            "Result: publication processed. "
            "The post was sent or skipped as a duplicate."
        )
    else:
        print(
            "Result: preview completed. "
            "Nothing was sent to Telegram."
        )


def main() -> None:
    """Точка запуска из командной строки."""

    args = parse_arguments()

    try:
        run_publication_job(
            symbol=args.symbol,
            interval=args.interval,
            send=args.send,
            notify=args.notify,
        )

    except PublicationJobError as exc:
        print()
        print("=" * 70)
        print("PUBLICATION JOB FAILED")
        print("=" * 70)
        print(f"Error: {exc}")
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        print("Publication job interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()