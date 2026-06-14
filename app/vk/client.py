from __future__ import annotations

from typing import Any

import requests


class VkApiError(RuntimeError):
    pass


class VkClient:
    def __init__(
        self,
        access_token: str,
        api_version: str = "5.199",
        timeout_seconds: int = 20,
    ) -> None:
        if not access_token:
            raise ValueError("VK_ACCESS_TOKEN is empty")

        self.access_token = access_token
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.vk.com/method"

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{method}"

        request_params = {
            **(params or {}),
            "access_token": self.access_token,
            "v": self.api_version,
        }

        response = requests.post(
            url,
            data=request_params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        payload = response.json()

        if "error" in payload:
            error = payload["error"]
            error_code = error.get("error_code")
            error_msg = error.get("error_msg")
            raise VkApiError(f"VK API error {error_code}: {error_msg}")

        return payload["response"]

    def get_token_permissions(self) -> dict[str, Any]:
        return self.call("groups.getTokenPermissions")

    def wall_post(
        self,
        group_id: int,
        message: str,
        from_group: bool = True,
        close_comments: bool = False,
        publish_date: int | None = None,
    ) -> dict[str, Any]:
        if not message.strip():
            raise ValueError("VK post message is empty")

        params: dict[str, Any] = {
            "owner_id": -abs(group_id),
            "from_group": 1 if from_group else 0,
            "message": message,
            "close_comments": 1 if close_comments else 0,
        }

        if publish_date is not None:
            params["publish_date"] = publish_date

        return self.call("wall.post", params)