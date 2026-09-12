"""Preview Telegram post formats for crypto-analytica.

Examples:

docker compose run --rm app python scripts/generate_content_post.py \
  --type market_snapshot --symbol BTCUSDT --interval 60

docker compose run --rm app python scripts/generate_content_post.py \
  --type deep_dive --symbol BTCUSDT --interval 60

docker compose run --rm app python scripts/generate_content_post.py \
  --type alert --symbol BTCUSDT --interval 60 --no-event-ok

docker compose run --rm app python scripts/generate_content_post.py \
  --type chart_caption --symbol BTCUSDT --interval 60

docker compose run --rm app python scripts/generate_content_post.py \
  --type daily_summary --symbols BTCUSDT ETHUSDT SOLUSDT --interval 60

docker compose run --rm app python scripts/generate_content_post.py \
  --type rsi_tutorial

docker compose run --rm app python scripts/generate_content_post.py \
  --type release_note
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine

from app.analytics.data_loader import get_database_url
from app.analytics.market_analysis import build_analysis
from app.posting.content_renderer import NoAlertEventError, build_post


DYNAMIC_TYPES = {
    "market_snapshot",
    "alert",
    "deep_dive",
    "chart_caption",
    "chart_only",  # backward-compatible alias for chart_caption
    "daily_summary",
}

STATIC_TYPES = {"rsi_tutorial", "release_note"}
ALL_TYPES = sorted(DYNAMIC_TYPES | STATIC_TYPES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a preview of one Telegram content format."
    )
    parser.add_argument(
        "--type",
        default="deep_dive",
        choices=ALL_TYPES,
        help="Post type to render. Default: deep_dive.",
    )
    parser.add_argument(
        "--symbol",
        help="Single Bybit symbol, for example BTCUSDT.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Several Bybit symbols for daily_summary.",
    )
    parser.add_argument(
        "--interval",
        default="60",
        help="Candle interval, for example 60. Default: 60.",
    )
    parser.add_argument(
        "--no-event-ok",
        action="store_true",
        help=(
            "For --type alert: exit with code 0 when no alert rule fired. "
            "Useful for scheduler/event scans."
        ),
    )

    return parser.parse_args()


def build_single_analysis(symbol: str, interval: str) -> dict:
    engine = create_engine(get_database_url())

    analysis = build_analysis(
        engine=engine,
        symbol=symbol.upper(),
        interval=interval,
    )

    if "error" in analysis:
        raise RuntimeError(f"{symbol}: {analysis['error']}")

    return analysis


def print_post(post_type: str, post: str) -> None:
    print("=" * 70)
    print(f"POST TYPE: {post_type}")
    print(f"POST LENGTH: {len(post)} characters")
    print("=" * 70)
    print(post)
    print("=" * 70)


def main() -> None:
    args = parse_args()
    post_type = args.type

    try:
        if post_type in STATIC_TYPES:
            post = build_post(post_type)  # type: ignore[arg-type]

        elif post_type == "daily_summary":
            symbols = args.symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            analyses = [build_single_analysis(symbol, args.interval) for symbol in symbols]
            post = build_post("daily_summary", analyses=analyses)

        else:
            symbol = args.symbol or "BTCUSDT"
            analysis = build_single_analysis(symbol, args.interval)
            post = build_post(post_type, analysis=analysis)  # type: ignore[arg-type]

    except NoAlertEventError as exc:
        print(f"No alert post generated: {exc}")
        if args.no_event_ok:
            sys.exit(0)
        sys.exit(2)

    except Exception as exc:  # noqa: BLE001 - CLI preview should print clear error
        print(f"Failed to build post: {exc}")
        sys.exit(1)

    print_post(post_type, post)


if __name__ == "__main__":
    main()
