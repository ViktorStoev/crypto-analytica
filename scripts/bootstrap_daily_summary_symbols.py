"""Bootstrap market data required for the daily_summary content job.

The script intentionally reuses the existing CLI scripts instead of
duplicating collection, backfill, indicator, or rendering logic.

Example:

    python scripts/bootstrap_daily_summary_symbols.py \
        --symbols BTCUSDT ETHUSDT SOLUSDT \
        --interval 60 \
        --days 180
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

DEFAULT_EXCHANGE = "bybit"
DEFAULT_CATEGORY = "linear"
SUPPORTED_INTERVALS = {"60"}


class BootstrapError(RuntimeError):
    """One of the bootstrap steps failed."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare candles, fresh market data, indicators, and a "
            "daily_summary preview for BTC/ETH/SOL-style symbol sets."
        )
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        help=(
            "Bybit symbols to prepare. Default: BTCUSDT ETHUSDT SOLUSDT."
        ),
    )
    parser.add_argument(
        "--interval",
        default="60",
        help="Candle interval. Currently supported: 60.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=180,
        help="How many days of candle history to backfill. Default: 180.",
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help="Bybit category. Currently supported: linear.",
    )
    parser.add_argument(
        "--exchange",
        default=DEFAULT_EXCHANGE,
        help="Exchange name. Currently supported: bybit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    parser.add_argument(
        "--skip-instruments-sync",
        action="store_true",
        help=(
            "Do not run sync_instruments.py before backfill. Use only when "
            "the instruments table is already known to be current."
        ),
    )
    parser.add_argument(
        "--skip-preview",
        action="store_true",
        help="Do not build the final daily_summary preview.",
    )

    args = parser.parse_args()
    args.symbols = [symbol.upper() for symbol in args.symbols]

    if len(args.symbols) < 3:
        parser.error(
            "daily_summary requires at least 3 symbols, for example: "
            "--symbols BTCUSDT ETHUSDT SOLUSDT"
        )

    if args.interval not in SUPPORTED_INTERVALS:
        parser.error(
            "Only interval 60 is currently supported because "
            "collect_market_once.py collects 1H candles."
        )

    if args.days <= 0:
        parser.error("--days must be greater than 0")

    if args.exchange != DEFAULT_EXCHANGE:
        parser.error("Only --exchange bybit is currently supported")

    if args.category != DEFAULT_CATEGORY:
        parser.error("Only --category linear is currently supported")

    return args


def script_path(script_name: str) -> Path:
    path = SCRIPTS_DIR / script_name

    if not path.is_file():
        raise BootstrapError(f"Script not found: {path}")

    return path


def format_command(arguments: Sequence[str]) -> str:
    return " ".join(arguments)


def run_python_script(
    *,
    title: str,
    script_name: str,
    arguments: Sequence[str],
    dry_run: bool,
) -> None:
    script = script_path(script_name)
    command = [
        sys.executable,
        str(script),
        *arguments,
    ]

    display_command = [
        "python",
        f"scripts/{script_name}",
        *arguments,
    ]

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(f"Command: {format_command(display_command)}")

    if dry_run:
        print("Dry run: command was not executed.")
        return

    completed_process = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    if completed_process.returncode != 0:
        raise BootstrapError(
            f"{title} failed with exit code "
            f"{completed_process.returncode}"
        )


def bootstrap_symbols(args: argparse.Namespace) -> None:
    print("=" * 70)
    print("DAILY SUMMARY SYMBOL BOOTSTRAP")
    print("=" * 70)
    print(f"Exchange: {args.exchange}")
    print(f"Category: {args.category}")
    print(f"Symbols: {', '.join(args.symbols)}")
    print(f"Interval: {args.interval}")
    print(f"Days: {args.days}")
    print(f"Dry run: {args.dry_run}")

    if not args.skip_instruments_sync:
        run_python_script(
            title="Step 1: Sync Bybit instruments",
            script_name="sync_instruments.py",
            arguments=[],
            dry_run=args.dry_run,
        )
    else:
        print()
        print("=" * 70)
        print("Step 1: Sync Bybit instruments")
        print("=" * 70)
        print("Skipped by --skip-instruments-sync.")

    for index, symbol in enumerate(args.symbols, start=1):
        run_python_script(
            title=(
                "Step 2: Backfill candles "
                f"({index}/{len(args.symbols)}: {symbol})"
            ),
            script_name="backfill_candles.py",
            arguments=[symbol, args.interval, str(args.days)],
            dry_run=args.dry_run,
        )

    run_python_script(
        title="Step 3: Collect fresh market data",
        script_name="collect_market_once.py",
        arguments=args.symbols,
        dry_run=args.dry_run,
    )

    for index, symbol in enumerate(args.symbols, start=1):
        run_python_script(
            title=(
                "Step 4: Calculate indicators "
                f"({index}/{len(args.symbols)}: {symbol})"
            ),
            script_name="calculate_indicators.py",
            arguments=[symbol, args.interval],
            dry_run=args.dry_run,
        )

    if not args.skip_preview:
        run_python_script(
            title="Step 5: Build daily_summary preview",
            script_name="generate_content_post.py",
            arguments=[
                "--type",
                "daily_summary",
                "--symbols",
                *args.symbols,
                "--interval",
                args.interval,
            ],
            dry_run=args.dry_run,
        )
    else:
        print()
        print("=" * 70)
        print("Step 5: Build daily_summary preview")
        print("=" * 70)
        print("Skipped by --skip-preview.")

    print()
    print("=" * 70)
    print("BOOTSTRAP COMPLETED")
    print("=" * 70)


def main() -> None:
    args = parse_args()

    try:
        bootstrap_symbols(args)

    except BootstrapError as exc:
        print()
        print("=" * 70)
        print("BOOTSTRAP FAILED")
        print("=" * 70)
        print(f"Error: {exc}")
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        print("Bootstrap interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
