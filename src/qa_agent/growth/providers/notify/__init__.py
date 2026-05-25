"""NotificationProvider protocol + implementations."""
from __future__ import annotations

import os
from typing import Protocol

import httpx


class NotificationProvider(Protocol):
    async def notify(self, channel: str, message: str, data: dict | None = None) -> None: ...


class ConsoleNotifyProvider:
    async def notify(self, channel: str, message: str, data: dict | None = None) -> None:
        print(f"\n[NOTIFY] {channel}: {message}")
        if data:
            print(f"  {data}")


class SlackProvider:
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    async def notify(self, channel: str, message: str, data: dict | None = None) -> None:
        text = message
        if data:
            fields = "  |  ".join(f"*{k}:* {v}" for k, v in data.items())
            text = f"{message}\n{fields}"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._url,
                json={"text": text},
                timeout=10,
            )
        resp.raise_for_status()


class WebhookProvider:
    def __init__(self, url: str) -> None:
        self._url = url

    async def notify(self, channel: str, message: str, data: dict | None = None) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                self._url,
                json={"channel": channel, "message": message, "data": data or {}},
                timeout=10,
            )


def from_env() -> NotificationProvider:
    webhook = os.getenv("SLACK_FOUNDER_WEBHOOK")
    if webhook:
        return SlackProvider(webhook_url=webhook)
    return ConsoleNotifyProvider()
