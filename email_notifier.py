"""
Email notification utility for CoirnaBot dashboard.

Sends alerts via Gmail SMTP for login events and IP blocks.
Uses asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText

from config import NOTIFICATION_EMAIL, SMTP_APP_PASSWORD, SMTP_EMAIL

logger = logging.getLogger(__name__)


def _send_email(subject: str, body: str) -> None:
    """Send email via Gmail SMTP (blocking)."""
    if not all([SMTP_EMAIL, SMTP_APP_PASSWORD, NOTIFICATION_EMAIL]):
        return
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = f"CoirnaBot <{SMTP_EMAIL}>"
    msg["To"] = NOTIFICATION_EMAIL
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.send_message(msg)


async def send_email_async(subject: str, body: str) -> None:
    """Non-blocking wrapper using asyncio.to_thread."""
    try:
        await asyncio.to_thread(_send_email, subject, body)
        logger.info(f"[Email] Sent: {subject}")
    except Exception as e:
        logger.error(f"[Email] Failed to send '{subject}': {e}")


async def notify_login(ip: str, browser: str, os_info: str) -> None:
    """Email notification on successful login."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    await send_email_async(
        "CoirnaBot: New Login",
        f"<h3>New Login Detected</h3>"
        f"<p><b>IP:</b> {ip}<br>"
        f"<b>Browser:</b> {browser}<br>"
        f"<b>OS:</b> {os_info}<br>"
        f"<b>Time:</b> {now}</p>",
    )


async def notify_blocked(ip: str, browser: str, os_info: str) -> None:
    """Email notification when IP is blocked after 10 failed attempts."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    await send_email_async(
        "CoirnaBot: IP Blocked After 10 Failed Attempts",
        f"<h3>IP Blocked</h3>"
        f"<p><b>IP:</b> {ip}<br>"
        f"<b>Browser:</b> {browser}<br>"
        f"<b>OS:</b> {os_info}<br>"
        f"<b>Time:</b> {now}<br>"
        f"<b>Reason:</b> 10 consecutive failed login attempts</p>",
    )
