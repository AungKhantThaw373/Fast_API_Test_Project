"""Password-reset delivery. Local installs print the link; hosted installs can use SMTP."""

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.logging_config import get_logger

logger = get_logger("email")


def _send_smtp(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST or "", settings.SMTP_PORT, timeout=20) as client:
        if settings.SMTP_STARTTLS:
            client.starttls()
        if settings.SMTP_USERNAME:
            client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
        client.send_message(message)


async def send_password_reset(to: str, link: str) -> None:
    body = (
        "Someone asked to reset the Stillroom password for this account.\n\n"
        f"{link}\n\n"
        "The link expires in 30 minutes and works once. If this was not you, ignore this message."
    )
    if not settings.SMTP_HOST:
        # Local mode: the console is the mail transport. This is deliberate and
        # documented; production deployments should set SMTP_HOST.
        logger.warning("Password reset link for %s: %s", to, link)
        return
    try:
        await asyncio.to_thread(_send_smtp, to, "Reset your Stillroom password", body)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("Could not send password reset email: %s", type(exc).__name__)