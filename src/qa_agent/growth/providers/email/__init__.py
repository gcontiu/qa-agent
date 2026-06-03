"""EmailProvider protocol + implementations."""
from __future__ import annotations

import os
from typing import Protocol

import httpx


class EmailProvider(Protocol):
    async def send(
        self,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> None: ...


class ConsoleProvider:
    """Prints to stdout — use in dev/test."""

    async def send(self, to: str, subject: str, html: str, text: str | None = None) -> None:
        print(f"\n[EMAIL] To: {to} | Subject: {subject}")
        if text:
            print(text[:500])
        print()


class ResendProvider:
    def __init__(self, api_key: str, from_email: str = "Steadra <noreply@updates.steadra.dev>") -> None:
        self._api_key = api_key
        self._from = from_email

    async def send(self, to: str, subject: str, html: str, text: str | None = None) -> None:
        app_url = os.getenv("APP_URL", "https://steadra.dev")
        unsubscribe_email = f"unsubscribe@updates.steadra.dev"
        payload: dict = {
            "from": self._from,
            "to": [to],
            "subject": subject,
            "html": html,
            "headers": {
                "List-Unsubscribe": f"<mailto:{unsubscribe_email}?subject=unsubscribe>, <{app_url}/unsubscribe>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        }
        if text:
            payload["text"] = text

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=15,
            )
        resp.raise_for_status()


def from_env() -> EmailProvider:
    """Build an EmailProvider from environment variables."""
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        return ResendProvider(api_key=resend_key)
    return ConsoleProvider()
