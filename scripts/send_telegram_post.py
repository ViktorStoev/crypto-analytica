"""Формирование и ручная отправка аналитического поста.

Предварительный просмотр:

docker compose run --rm app \
    python scripts/send_telegram_post.py BTCUSDT 60

Публикация без уведомления:

docker compose run --rm app \
    python scripts/send_telegram_post.py BTCUSDT 60 --send

Публикация с уведомлением:

docker compose run --rm app \
    python scripts/send_telegram_post.py \
    BTCUSDT 60 --send --notify

Регистрация уже существующего сообщения:

docker compose run --rm app \
    python scripts/send_telegram_post.py \
    BTCUSDT 60 --register-existing-message-id 11
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine

from app.analytics.data_loader import get_database_url
from app.analytics.market_analysis import build_analysis
from app.posting.content_renderer import (
    NoAlertEventError,
    build_post as build_content_post,
)
from app.posting.publication_service import (
    publish_telegram_post,
    register_existing_publication,
)
from app.posting.template_generator import (
    build_telegram_post,
)
from app.telegram.publisher import (
    TelegramError,
    TelegramPublisher,
)


LEGACY_POST_TYPES = {
    "market_analysis",
    "legacy_market_analysis",
}

CONTENT_POST_TYPES = {
    "market_snapshot",
    "deep_dive",
    "alert",
    "chart_caption",
    "chart_only",
}

SUPPORTED_POST_TYPES = sorted(
    LEGACY_POST_TYPES | CONTENT_POST_TYPES
)


def parse_arguments() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""

    parser = argparse.ArgumentParser(
        description=(
            "Build an analytical Telegram post "
            "and optionally publish it."
        )
    )

    parser.add_argument(
        "symbol",
        help="Bybit symbol, for example BTCUSDT.",
    )

    parser.add_argument(
        "interval",
        help="Candle interval, for example 60.",
    )

    parser.add_argument(
        "--type",
        default="market_snapshot",
        choices=SUPPORTED_POST_TYPES,
        help=(
            "Telegram post format. Default: market_snapshot. "
            "Use market_analysis or legacy_market_analysis for the old template."
        ),
    )

    parser.add_argument(
        "--no-event-ok",
        action="store_true",
        help=(
            "For --type alert: exit with code 0 when no alert rule fired. "
            "Useful for scheduler/event scans."
        ),
    )

    action_group = parser.add_mutually_exclusive_group()

    action_group.add_argument(
        "--send",
        action="store_true",
        help=(
            "Publish the post through Telegram. "
            "Without this flag, only preview it."
        ),
    )

    action_group.add_argument(
        "--register-existing-message-id",
        type=int,
        metavar="MESSAGE_ID",
        help=(
            "Register an already published Telegram "
            "message without sending it again."
        ),
    )

    parser.add_argument(
        "--notify",
        action="store_true",
        help=(
            "Enable subscriber notification. "
            "Can only be used together with --send."
        ),
    )

    args = parser.parse_args()

    if args.notify and not args.send:
        parser.error(
            "--notify can only be used together with --send"
        )

    if args.no_event_ok and args.type != "alert":
        parser.error(
            "--no-event-ok can only be used together with --type alert"
        )

    return args


def normalize_post_type(post_type: str) -> str:
    """Normalize CLI aliases to values stored in generated_posts."""

    if post_type == "legacy_market_analysis":
        return "market_analysis"

    if post_type == "chart_only":
        return "chart_caption"

    return post_type


def build_post_text(
    *,
    post_type: str,
    analysis: dict,
) -> str:
    """Build Telegram text for the requested post type."""

    if post_type in LEGACY_POST_TYPES:
        return build_telegram_post(analysis)

    return build_content_post(
        post_type,  # type: ignore[arg-type]
        analysis=analysis,
    )


def main() -> None:
    """Сформировать пост и выполнить выбранное действие."""

    args = parse_arguments()

    symbol = args.symbol.upper()
    interval = args.interval
    requested_post_type = args.type
    stored_post_type = normalize_post_type(
        requested_post_type
    )

    print("Building market analysis...")
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")
    print(f"Post type: {stored_post_type}")

    engine = create_engine(
        get_database_url()
    )

    analysis = build_analysis(
        engine=engine,
        symbol=symbol,
        interval=interval,
    )

    if "error" in analysis:
        print()
        print("Analysis could not be built:")
        print(analysis["error"])
        sys.exit(1)

    try:
        post = build_post_text(
            post_type=requested_post_type,
            analysis=analysis,
        )

    except NoAlertEventError as exc:
        print()
        print(f"No alert post generated: {exc}")
        if args.no_event_ok:
            print("No-event alert scan completed successfully.")
            return
        sys.exit(2)

    candle_time = analysis.get("candle_time")
    current_price = (
        analysis.get("price", {}).get("current")
    )

    if not candle_time:
        print(
            "Analysis does not contain candle_time."
        )
        sys.exit(1)

    print()
    print("Analysis built successfully.")
    print(f"Candle time: {candle_time}")
    print(f"Current price: {current_price}")
    print(
        f"Post length: {len(post)} characters"
    )

    print()
    print("=" * 70)
    print(f"TELEGRAM POST PREVIEW: {stored_post_type}")
    print("=" * 70)
    print(post)
    print("=" * 70)

    if (
        not args.send
        and args.register_existing_message_id is None
    ):
        print()
        print("Preview completed.")
        print("The post was not sent to Telegram.")
        print(
            "Use --send when the text "
            "is ready for publication."
        )
        return

    try:
        publisher = TelegramPublisher()

    except TelegramError as exc:
        print(
            f"Telegram initialization failed: {exc}"
        )
        sys.exit(1)

    if args.register_existing_message_id is not None:
        print()
        print(
            "Registering existing Telegram message..."
        )

        result = register_existing_publication(
            engine=engine,
            publisher=publisher,
            symbol=symbol,
            interval=interval,
            candle_time=candle_time,
            content=post,
            telegram_message_id=(
                args.register_existing_message_id
            ),
            disable_notification=True,
            post_type=stored_post_type,
        )

        print()
        print("Existing publication processed.")
        print(
            f"Publication ID: "
            f"{result.publication_id}"
        )
        print(f"Status: {result.status}")
        print(f"Duplicate: {result.duplicate}")
        print(
            f"Telegram message ID: "
            f"{result.telegram_message_id}"
        )
        return

    print()
    print("Sending post to Telegram...")

    result = publish_telegram_post(
        engine=engine,
        publisher=publisher,
        symbol=symbol,
        interval=interval,
        candle_time=candle_time,
        content=post,
        disable_notification=not args.notify,
        post_type=stored_post_type,
    )

    if result.duplicate:
        print()
        print(
            "Publication skipped: "
            "a record for this candle already exists."
        )
        print(
            f"Publication ID: "
            f"{result.publication_id}"
        )
        print(
            f"Existing status: {result.status}"
        )
        print(
            f"Telegram message ID: "
            f"{result.telegram_message_id}"
        )

        if result.status == "sent":
            print()
            print(
                "The existing publication is confirmed "
                "as successfully sent."
            )
            return

        print()
        print(
            "The existing publication is not confirmed "
            "as successfully sent."
        )
        print(
            "Manual review is required before retrying."
        )

        if result.error_text:
            print(f"Existing error: {result.error_text}")

        sys.exit(2)

    if result.status != "sent":
        print()
        print("Telegram publication was not confirmed.")
        print(
            f"Publication ID: "
            f"{result.publication_id}"
        )
        print(f"Status: {result.status}")
        print(f"Error: {result.error_text}")
        sys.exit(1)

    print()
    print("Telegram post sent successfully.")
    print(
        f"Publication ID: "
        f"{result.publication_id}"
    )
    print(
        f"Telegram message ID: "
        f"{result.telegram_message_id}"
    )
    print(f"Candle time: {candle_time}")
    print(
        f"Notifications enabled: "
        f"{args.notify}"
    )


if __name__ == "__main__":
    main()
