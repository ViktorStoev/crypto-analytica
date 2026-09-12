"""Безопасное разрешение проблемных Telegram-публикаций.

Просмотр публикации:

docker compose run --rm app \
    python scripts/resolve_publication.py show 4

Подтвердить, что пост существует в Telegram:

docker compose run --rm app \
    python scripts/resolve_publication.py mark-sent 4 \
    --message-id 12 \
    --note "Пост найден в канале и проверен вручную"

Повторить публикацию после подтверждения её отсутствия:

docker compose run --rm app \
    python scripts/resolve_publication.py retry 4 \
    --confirm-not-sent \
    --note "Канал проверен вручную, публикации нет"
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from sqlalchemy import create_engine

from app.analytics.data_loader import get_database_url
from app.posting.publication_service import (
    PublicationResolutionError,
    get_publication_by_id,
    mark_unknown_publication_as_sent,
    retry_unknown_publication,
)
from app.telegram.publisher import (
    TelegramError,
    TelegramPublisher,
)


def build_parser() -> argparse.ArgumentParser:
    """Создать parser командной строки."""

    parser = argparse.ArgumentParser(
        description=(
            "Inspect or safely resolve a problematic "
            "Telegram publication."
        )
    )

    subparsers = parser.add_subparsers(
        dest="action",
        required=True,
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Show publication information.",
    )

    show_parser.add_argument(
        "publication_id",
        type=int,
    )

    mark_sent_parser = subparsers.add_parser(
        "mark-sent",
        help=(
            "Confirm that an unknown publication "
            "exists in Telegram."
        ),
    )

    mark_sent_parser.add_argument(
        "publication_id",
        type=int,
    )

    mark_sent_parser.add_argument(
        "--message-id",
        type=int,
        required=True,
        help="Existing Telegram message ID.",
    )

    mark_sent_parser.add_argument(
        "--note",
        required=True,
        help="Manual review explanation.",
    )

    retry_parser = subparsers.add_parser(
        "retry",
        help=(
            "Retry an unknown publication after confirming "
            "that no Telegram post exists."
        ),
    )

    retry_parser.add_argument(
        "publication_id",
        type=int,
    )

    retry_parser.add_argument(
        "--confirm-not-sent",
        action="store_true",
        help=(
            "Required confirmation that the channel "
            "was checked and the post is absent."
        ),
    )

    retry_parser.add_argument(
        "--note",
        required=True,
        help="Manual review explanation.",
    )

    return parser


def print_publication(
    publication: dict[str, Any],
) -> None:
    """Показать основные данные публикации."""

    print("=" * 70)
    print("PUBLICATION")
    print("=" * 70)

    fields = (
        "id",
        "post_type",
        "exchange",
        "category",
        "symbol",
        "interval",
        "candle_time",
        "telegram_chat_id",
        "status",
        "disable_notification",
        "telegram_message_id",
        "retry_count",
        "last_attempt_at",
        "manual_reviewed_at",
        "manual_review_note",
        "created_at",
        "updated_at",
        "sent_at",
        "error_text",
    )

    for field in fields:
        print(
            f"{field}: "
            f"{publication.get(field)}"
        )

    content = str(
        publication.get("content") or ""
    )

    print(f"content_length: {len(content)}")
    print(
        "content_preview: "
        f"{content[:200].replace(chr(10), ' | ')}"
    )


def main() -> None:
    """Выполнить выбранную операцию."""

    parser = build_parser()
    args = parser.parse_args()

    if (
        args.action == "retry"
        and not args.confirm_not_sent
    ):
        parser.error(
            "retry requires --confirm-not-sent. "
            "Check the Telegram channel before retrying."
        )

    engine = create_engine(
        get_database_url()
    )

    try:
        if args.action == "show":
            publication = get_publication_by_id(
                engine,
                args.publication_id,
            )

            print_publication(publication)
            return

        if args.action == "mark-sent":
            result = mark_unknown_publication_as_sent(
                engine,
                publication_id=args.publication_id,
                telegram_message_id=args.message_id,
                review_note=args.note,
            )

            print("Publication marked as sent.")
            print(
                f"Publication ID: "
                f"{result.publication_id}"
            )
            print(f"Status: {result.status}")
            print(
                f"Telegram message ID: "
                f"{result.telegram_message_id}"
            )
            return

        if args.action == "retry":
            publisher = TelegramPublisher()

            result = retry_unknown_publication(
                engine,
                publisher,
                publication_id=args.publication_id,
                review_note=args.note,
            )

            print("Controlled retry completed.")
            print(
                f"Publication ID: "
                f"{result.publication_id}"
            )
            print(f"Status: {result.status}")
            print(
                f"Telegram message ID: "
                f"{result.telegram_message_id}"
            )

            if result.error_text:
                print(
                    f"Error: {result.error_text}"
                )

            if result.status != "sent":
                sys.exit(1)

            return

        parser.error(
            f"Unsupported action: {args.action}"
        )

    except PublicationResolutionError as exc:
        print(
            f"Publication resolution failed: {exc}"
        )
        sys.exit(1)

    except TelegramError as exc:
        print(
            f"Telegram initialization failed: {exc}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()