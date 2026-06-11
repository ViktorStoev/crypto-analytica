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

    return args


def main() -> None:
    """Сформировать пост и выполнить выбранное действие."""

    args = parse_arguments()

    symbol = args.symbol.upper()
    interval = args.interval

    print("Building market analysis...")
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")

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

    post = build_telegram_post(analysis)

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
    print("TELEGRAM POST PREVIEW")
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