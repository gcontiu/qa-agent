"""NotificationProvider protocol + implementations."""
from __future__ import annotations

import os
from typing import Protocol, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..email import EmailProvider


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


class EmailNotifyProvider:
    """Sends founder notifications as plain emails through the existing
    EmailProvider (Resend in prod). Use when there's no Slack — set
    FOUNDER_NOTIFY_EMAIL to the recipient."""

    def __init__(self, to_email: str, email_provider: "EmailProvider | None" = None) -> None:
        self._to = to_email
        # Lazily build the email provider so notify stays decoupled and we
        # reuse whatever email transport is already configured (Resend/Console).
        if email_provider is None:
            from ..email import from_env as _email_from_env
            email_provider = _email_from_env()
        self._email = email_provider

    async def notify(self, channel: str, message: str, data: dict | None = None) -> None:
        rows = ""
        link = None
        for k, v in (data or {}).items():
            if k in ("approve", "link", "url") and isinstance(v, str) and v.startswith("http"):
                if k == "approve":
                    link = v
                rows += f'<tr><td style="padding:2px 12px 2px 0;color:#888">{k}</td><td><a href="{v}">{v}</a></td></tr>'
            else:
                rows += f'<tr><td style="padding:2px 12px 2px 0;color:#888">{k}</td><td>{v}</td></tr>'

        cta = (
            f'<p style="margin:16px 0"><a href="{link}" '
            f'style="background:#06b6d4;color:#000;padding:10px 18px;border-radius:8px;'
            f'text-decoration:none;font-weight:600">Open in admin →</a></p>'
            if link else ""
        )
        html = (
            f'<div style="font-family:system-ui,sans-serif;font-size:14px;color:#111">'
            f'<p style="font-weight:600;font-size:15px">{message}</p>'
            f'<table style="border-collapse:collapse;font-size:13px">{rows}</table>'
            f'{cta}'
            f'<p style="color:#aaa;font-size:11px;margin-top:20px">Steadra · {channel}</p>'
            f'</div>'
        )
        text_lines = [message] + [f"{k}: {v}" for k, v in (data or {}).items()]
        await self._email.send(
            to=self._to,
            subject=f"[Steadra] {message}",
            html=html,
            text="\n".join(text_lines),
        )


def from_env() -> NotificationProvider:
    webhook = os.getenv("SLACK_FOUNDER_WEBHOOK")
    if webhook:
        return SlackProvider(webhook_url=webhook)
    founder_email = os.getenv("FOUNDER_NOTIFY_EMAIL")
    if founder_email:
        return EmailNotifyProvider(to_email=founder_email)
    return ConsoleNotifyProvider()
