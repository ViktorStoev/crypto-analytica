"""Клиент для отправки сообщений через Telegram Bot API.

Модуль отвечает только за взаимодействие с Telegram:

- проверяет токен бота;
- проверяет доступность канала;
- проверяет права бота в канале;
- отправляет текстовые сообщения.

Модуль не занимается:

- сбором данных с Bybit;
- расчётом индикаторов;
- формированием аналитики;
- запуском задач по расписанию.
"""

from __future__ import annotations

from typing import Any

import requests

from app.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_PROXY_URL,
)


TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_MAX_LENGTH = 4096


class TelegramError(RuntimeError):
    """Базовая ошибка работы с Telegram."""


class TelegramConfigurationError(TelegramError):
    """Ошибка конфигурации Telegram."""


class TelegramRequestError(TelegramError):
    """Ошибка сетевого запроса к Telegram."""

class TelegramTimeoutError(TelegramRequestError):
    """Telegram не ответил за установленное время."""

class TelegramApiError(TelegramError):
    """Ошибка, которую вернул Telegram Bot API."""


class TelegramPublisher:
    """Минимальный клиент Telegram Bot API."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        proxy_url: str | None = None,
        timeout: float = 20.0,
        api_base_url: str = TELEGRAM_API_BASE_URL,
    ) -> None:
        self.token = (token or TELEGRAM_BOT_TOKEN or "").strip()
        self.chat_id = (chat_id or TELEGRAM_CHAT_ID or "").strip()

        configured_proxy_url = (
            proxy_url
            if proxy_url is not None
            else TELEGRAM_PROXY_URL
        )

        self.proxy_url = (configured_proxy_url or "").strip()

        self.timeout = timeout
        self.api_base_url = api_base_url.rstrip("/")

        self.session = requests.Session()

        # Не берём proxy-настройки из окружения всей системы.
        # Прокси должен использоваться только этим Telegram-клиентом.
        self.session.trust_env = False

        self.proxies: dict[str, str] | None = None

        if self.proxy_url:
            if not self.proxy_url.startswith(("http://", "https://")):
                raise TelegramConfigurationError(
                    "TELEGRAM_PROXY_URL must start with http:// or https://"
                )

            self.proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }

        if not self.token:
            raise TelegramConfigurationError(
                "TELEGRAM_BOT_TOKEN is not set."
            )

    def _require_chat_id(self) -> str:
        """Проверить, что идентификатор канала настроен."""

        if not self.chat_id:
            raise TelegramConfigurationError(
                "TELEGRAM_CHAT_ID is not set."
            )

        return self.chat_id

    def _call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Выполнить запрос к Telegram Bot API."""

        url = f"{self.api_base_url}/bot{self.token}/{method}"

        try:
            response = self.session.post(
                url,
                json=payload or {},
                timeout=self.timeout,
                proxies=self.proxies,
            )
        except requests.Timeout as exc:
            raise TelegramTimeoutError(
                "Telegram request timed out: "
                f"method={method}, error_type={type(exc).__name__}"
            ) from exc
        except requests.RequestException as exc:
            # Не выводим полный текст requests-ошибки:
            # в нём может присутствовать URL с токеном.
            raise TelegramRequestError(
                "Telegram network request failed: "
                f"method={method}, error_type={type(exc).__name__}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramRequestError(
                "Telegram returned an invalid JSON response: "
                f"method={method}, http_status={response.status_code}"
            ) from exc

        if not response.ok or data.get("ok") is not True:
            error_code = data.get("error_code", response.status_code)
            description = data.get(
                "description",
                "Unknown Telegram API error",
            )

            raise TelegramApiError(
                "Telegram API request failed: "
                f"method={method}, "
                f"error_code={error_code}, "
                f"description={description}"
            )

        return data.get("result")

    def get_me(self) -> dict[str, Any]:
        """Получить информацию о Telegram-боте."""

        result = self._call("getMe")

        if not isinstance(result, dict):
            raise TelegramApiError(
                "Telegram getMe returned an unexpected result."
            )

        return result

    def get_chat(self) -> dict[str, Any]:
        """Получить информацию о настроенном канале."""

        result = self._call(
            "getChat",
            {
                "chat_id": self._require_chat_id(),
            },
        )

        if not isinstance(result, dict):
            raise TelegramApiError(
                "Telegram getChat returned an unexpected result."
            )

        return result

    def get_chat_member(self, user_id: int) -> dict[str, Any]:
        """Получить информацию о правах пользователя или бота в канале."""

        result = self._call(
            "getChatMember",
            {
                "chat_id": self._require_chat_id(),
                "user_id": user_id,
            },
        )

        if not isinstance(result, dict):
            raise TelegramApiError(
                "Telegram getChatMember returned an unexpected result."
            )

        return result

    def send_message(
        self,
        text: str,
        disable_notification: bool = False,
    ) -> dict[str, Any]:
        """Отправить текстовое сообщение в настроенный канал."""

        if not text or not text.strip():
            raise TelegramConfigurationError(
                "Telegram message text cannot be empty."
            )

        if len(text) > TELEGRAM_MESSAGE_MAX_LENGTH:
            raise TelegramConfigurationError(
                "Telegram message is too long: "
                f"length={len(text)}, "
                f"maximum={TELEGRAM_MESSAGE_MAX_LENGTH}"
            )

        result = self._call(
            "sendMessage",
            {
                "chat_id": self._require_chat_id(),
                "text": text,
                "disable_notification": disable_notification,
            },
        )

        if not isinstance(result, dict):
            raise TelegramApiError(
                "Telegram sendMessage returned an unexpected result."
            )

        return result