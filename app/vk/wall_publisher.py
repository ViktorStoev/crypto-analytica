from __future__ import annotations

import os

from app.vk.client import VkClient


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class VkWallPublisher:
    def __init__(
        self,
        client: VkClient,
        group_id: int,
        dry_run: bool = True,
        post_as_group: bool = True,
        close_comments: bool = False,
    ) -> None:
        self.client = client
        self.group_id = group_id
        self.dry_run = dry_run
        self.post_as_group = post_as_group
        self.close_comments = close_comments

    @classmethod
    def from_env(cls) -> "VkWallPublisher":
        access_token = os.getenv("VK_ACCESS_TOKEN", "")
        api_version = os.getenv("VK_API_VERSION", "5.199")
        group_id_raw = os.getenv("VK_GROUP_ID", "")

        if not group_id_raw:
            raise RuntimeError("VK_GROUP_ID is not set")

        client = VkClient(
            access_token=access_token,
            api_version=api_version,
        )

        return cls(
            client=client,
            group_id=int(group_id_raw),
            dry_run=env_bool("VK_DRY_RUN", True),
            post_as_group=env_bool("VK_POST_AS_GROUP", True),
            close_comments=env_bool("VK_CLOSE_COMMENTS", False),
        )

    def publish_text(self, text: str) -> dict:
        if self.dry_run:
            print("========== VK DRY RUN ==========")
            print(f"group_id: {self.group_id}")
            print(f"post_as_group: {self.post_as_group}")
            print(f"close_comments: {self.close_comments}")
            print("--------------------------------")
            print(text)
            print("================================")

            return {
                "dry_run": True,
                "group_id": self.group_id,
                "text_length": len(text),
            }

        response = self.client.wall_post(
            group_id=self.group_id,
            message=text,
            from_group=self.post_as_group,
            close_comments=self.close_comments,
        )

        post_id = response.get("post_id")
        post_url = None

        if post_id is not None:
            post_url = f"https://vk.com/wall-{abs(self.group_id)}_{post_id}"

        return {
            "dry_run": False,
            "group_id": self.group_id,
            "post_id": post_id,
            "post_url": post_url,
            "raw_response": response,
        }