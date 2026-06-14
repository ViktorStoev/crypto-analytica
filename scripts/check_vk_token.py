from __future__ import annotations

import json
import os
import sys

from app.vk.client import VkApiError
from app.vk.client import VkClient


def main() -> None:
    token = os.getenv("VK_ACCESS_TOKEN", "")
    api_version = os.getenv("VK_API_VERSION", "5.199")

    if not token:
        print("VK_ACCESS_TOKEN is not set")
        sys.exit(1)

    client = VkClient(
        access_token=token,
        api_version=api_version,
    )

    try:
        permissions = client.get_token_permissions()
    except VkApiError as exc:
        print("VK token check failed:")
        print(exc)
        sys.exit(1)

    print(json.dumps(permissions, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()