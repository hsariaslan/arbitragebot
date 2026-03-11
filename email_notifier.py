"""
Email notification utility for ArbitrageBot dashboard.

Sends alerts via Gmail SMTP for login events and IP blocks.
Uses asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
import html
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
    msg["From"] = f"ArbitrageBot <{SMTP_EMAIL}>"
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
        "ArbitrageBot: New Login",
        f"<h3>New Login Detected</h3>"
        f"<p><b>IP:</b> {html.escape(ip)}<br>"
        f"<b>Browser:</b> {html.escape(browser)}<br>"
        f"<b>OS:</b> {html.escape(os_info)}<br>"
        f"<b>Time:</b> {now}</p>",
    )


async def notify_blocked(ip: str, browser: str, os_info: str) -> None:
    """Email notification when IP is blocked after 10 failed attempts."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    await send_email_async(
        "ArbitrageBot: IP Blocked After 10 Failed Attempts",
        f"<h3>IP Blocked</h3>"
        f"<p><b>IP:</b> {html.escape(ip)}<br>"
        f"<b>Browser:</b> {html.escape(browser)}<br>"
        f"<b>OS:</b> {html.escape(os_info)}<br>"
        f"<b>Time:</b> {now}<br>"
        f"<b>Reason:</b> 10 consecutive failed login attempts</p>",
    )


async def notify_emergency(
    reason: str,
    drawdown_pct: float,
    peak_value: float,
    current_value: float,
    positions_sold: int,
    total_sold: float,
    portfolio_breakdown: dict[str, float] | None = None,
    liquidated_positions: list[dict] | None = None,
) -> None:
    """Email notification on emergency sell-all.

    Includes drawdown info, positions liquidated, and per-exchange USDT breakdown.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    drop = peak_value - current_value

    positions_html = ""
    if liquidated_positions:
        pos_rows = "".join(
            f"<tr><td>{html.escape(p['exchange'])}</td>"
            f"<td>{html.escape(p['symbol'])}</td>"
            f"<td>{p['qty']:.6f}</td>"
            f"<td>${p['price']:.4f}</td>"
            f"<td>${p['gross']:.2f}</td>"
            f"<td>{p['fee_pct']:.3f}%</td>"
            f"<td>${p['net']:.2f}</td></tr>"
            for p in sorted(
                liquidated_positions, key=lambda x: -x["gross"]
            )
        )
        positions_html = (
            f"<h4>Liquidated Positions</h4>"
            f"<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tr><th>Exchange</th><th>Symbol</th><th>Qty</th>"
            f"<th>Price</th><th>Gross</th><th>Fee</th><th>Net</th></tr>"
            f"{pos_rows}</table>"
        )

    breakdown_html = ""
    if portfolio_breakdown:
        rows = "".join(
            f"<tr><td>{html.escape(ex)}</td><td>${val:.2f}</td></tr>"
            for ex, val in sorted(
                portfolio_breakdown.items(), key=lambda x: -x[1]
            )
        )
        breakdown_html = (
            f"<h4>USDT Per Exchange (after sell-all)</h4>"
            f"<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tr><th>Exchange</th><th>USDT</th></tr>"
            f"{rows}</table>"
        )

    await send_email_async(
        f"ArbitrageBot: EMERGENCY — Portfolio -{drawdown_pct:.1f}%",
        f"<h3 style='color:red'>Emergency Sell-All Triggered</h3>"
        f"<p><b>Time:</b> {now}<br>"
        f"<b>Reason:</b> {html.escape(reason)}<br>"
        f"<b>Drawdown:</b> {drawdown_pct:.2f}% "
        f"(${drop:.2f} from peak ${peak_value:.2f})<br>"
        f"<b>Current portfolio:</b> ${current_value:.2f}<br>"
        f"<b>Positions liquidated:</b> {positions_sold}<br>"
        f"<b>Total crypto sold:</b> ${total_sold:.2f}</p>"
        f"{positions_html}"
        f"{breakdown_html}"
        f"<p style='color:red'><b>Trading is PAUSED. "
        f"Manual resume required from dashboard.</b></p>",
    )
