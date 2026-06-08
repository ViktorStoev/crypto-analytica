"""Проверка Telegram-бота, канала и прав на публикацию.

Запуск:

docker compose run --rm app python scripts/check_telegram_bot.py
"""

import sys

from app.telegram.publisher import TelegramError, TelegramPublisher


def main() -> None:
    try:
        publisher = TelegramPublisher()

        print("1. Checking Telegram bot token...")
        bot = publisher.get_me()

        bot_id = bot.get("id")
        bot_username = bot.get("username")
        bot_name = bot.get("first_name")

        if not isinstance(bot_id, int):
            raise RuntimeError(
                "Telegram did not return a valid bot ID."
            )

        print("   Token is valid.")
        print(f"   Bot name: {bot_name}")
        print(f"   Bot username: @{bot_username}")

        print()
        print("2. Checking Telegram channel...")
        chat = publisher.get_chat()

        channel_title = chat.get("title")
        channel_username = chat.get("username")
        channel_type = chat.get("type")

        print("   Channel is available.")
        print(f"   Channel title: {channel_title}")
        print(f"   Channel username: @{channel_username}")
        print(f"   Channel type: {channel_type}")

        if channel_type != "channel":
            print()
            print(
                "ERROR: TELEGRAM_CHAT_ID does not point "
                "to a Telegram channel."
            )
            sys.exit(1)

        print()
        print("3. Checking bot permissions...")
        membership = publisher.get_chat_member(bot_id)

        status = membership.get("status")
        can_post_messages = membership.get("can_post_messages")

        print(f"   Bot status: {status}")
        print(f"   Can post messages: {can_post_messages}")

        if status != "administrator":
            print()
            print(
                "ERROR: The bot is not an administrator "
                "of the Telegram channel."
            )
            sys.exit(1)

        if can_post_messages is not True:
            print()
            print(
                "ERROR: The bot does not have permission "
                "to publish messages."
            )
            sys.exit(1)

        print()
        print("Telegram check completed successfully.")
        print("The bot can publish messages to the channel.")

    except TelegramError as exc:
        print(f"Telegram check failed: {exc}")
        sys.exit(1)

    except RuntimeError as exc:
        print(f"Telegram check failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()