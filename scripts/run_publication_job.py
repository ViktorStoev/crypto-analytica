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

Публикация подробного разбора:

docker compose run --rm app \
    python scripts/run_publication_job.py \
    BTCUSDT 60 --type deep_dive --send
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
SUPPORTED_POST_TYPES = {
    "market_snapshot",
    "deep_dive",
    "alert",
    "chart_caption",
    "chart_only",
    "daily_summary",
    "rsi_tutorial",
    "release_note",
    "market_analysis",
    "legacy_market_analysis",
}
STATIC_POST_TYPES = {
    "rsi_tutorial",
    "release_note",
}
MULTI_SYMBOL_POST_TYPES = {
    "daily_summary",
}


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
        help=(
            "Candle interval. Currently supported: 60. "
            "Use static for rsi_tutorial/release_note."
        ),
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        help=(
            "Several Bybit symbols for multi-symbol post types, "
            "for example: --symbols BTCUSDT ETHUSDT SOLUSDT."
        ),
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
        "--type",
        default="market_snapshot",
        choices=sorted(SUPPORTED_POST_TYPES),
        help=(
            "Telegram post format. Default: market_snapshot. "
            "Use market_analysis or legacy_market_analysis for the old template."
        ),
    )

    parser.add_argument(
        "--no-event-ok",
        action="store_true",
        help=(
            "For --type alert: treat no detected event as a successful no-op."
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

    if (
        args.type not in STATIC_POST_TYPES
        and args.interval not in SUPPORTED_INTERVALS
    ):
        parser.error(
            "Only interval 60 is currently supported because "
            "collect_market_once.py collects 1H candles."
        )

    if args.type in STATIC_POST_TYPES and args.interval != "static":
        parser.error(
            "Static post types require interval static."
        )

    if args.type in MULTI_SYMBOL_POST_TYPES:
        symbols = args.symbols or [args.symbol]
        if len(symbols) < 3:
            parser.error(
                "daily_summary requires at least 3 symbols, "
                "for example: --symbols BTCUSDT ETHUSDT SOLUSDT"
            )

    if args.notify and not args.send:
        parser.error(
            "--notify can only be used together with --send"
        )

    if args.no_event_ok and args.type != "alert":
        parser.error(
            "--no-event-ok can only be used together with --type alert"
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
    post_type: str,
    symbols: list[str],
    no_event_ok: bool,
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
    if symbols:
        print(f"Symbols: {', '.join(symbols)}")
    print(f"Interval: {interval}")
    print(f"Post type: {post_type}")
    print(f"No-event OK: {no_event_ok}")
    print(f"Send enabled: {send}")
    print(f"Notifications enabled: {notify}")

    if post_type in STATIC_POST_TYPES:
        print()
        print("=" * 70)
        print("STEP 1-2: Skip market data refresh")
        print("=" * 70)
        print(
            "Static content does not require Bybit collection "
            "or indicator calculation."
        )

    else:
        analysis_symbols = (
            symbols
            if post_type in MULTI_SYMBOL_POST_TYPES
            else [symbol]
        )

        run_python_step(
            step_number=1,
            step_name="Collect fresh Bybit market data",
            script_name="collect_market_once.py",
            arguments=analysis_symbols,
        )

        for index, analysis_symbol in enumerate(
            analysis_symbols,
            start=1,
        ):
            run_python_step(
                step_number=2,
                step_name=(
                    "Calculate technical indicators "
                    f"({index}/{len(analysis_symbols)})"
                ),
                script_name="calculate_indicators.py",
                arguments=[analysis_symbol, interval],
            )

    publication_arguments = [
        symbol,
        interval,
        "--type",
        post_type,
    ]

    if symbols:
        publication_arguments.append("--symbols")
        publication_arguments.extend(symbols)

    if no_event_ok:
        publication_arguments.append("--no-event-ok")

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
            post_type=args.type,
            symbols=[
                item.upper()
                for item in (args.symbols or [])
            ],
            no_event_ok=args.no_event_ok,
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
