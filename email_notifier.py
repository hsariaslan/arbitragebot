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


_RESUME_INSTRUCTIONS_HTML = (
    "<h4>How to Resume Trading</h4>"
    "<ol>"
    "<li>Open the dashboard: <a href='https://bot.sariaslan.org'>https://bot.sariaslan.org</a></li>"
    "<li>Log in (you will keep your existing session if still active).</li>"
    "<li>Go to <b>Settings → Danger Zone</b>.</li>"
    "<li>Review the <b>Trading Paused</b> banner — it shows the reason.</li>"
    "<li>Click the green <b>Resume Trading</b> button.</li>"
    "</ol>"
    "<p><i>Until you click Resume Trading, the bot will re-send this email every hour.</i></p>"
)


def _build_emergency_html(
    *,
    reason: str,
    drawdown_pct: float,
    peak_value: float,
    current_value: float,
    positions_sold: int,
    total_sold: float,
    portfolio_breakdown: dict[str, float] | None,
    liquidated_positions: list[dict] | None,
    consolidation_summary: dict | None,
    is_reminder: bool,
    paused_for_seconds: float,
) -> str:
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
            for p in sorted(liquidated_positions, key=lambda x: -x["gross"])
        )
        positions_html = (
            "<h4>Liquidated Positions</h4>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<tr><th>Exchange</th><th>Symbol</th><th>Qty</th>"
            "<th>Price</th><th>Gross</th><th>Fee</th><th>Net</th></tr>"
            f"{pos_rows}</table>"
        )

    breakdown_html = ""
    if portfolio_breakdown:
        rows = "".join(
            f"<tr><td>{html.escape(ex)}</td><td>${val:.2f}</td></tr>"
            for ex, val in sorted(portfolio_breakdown.items(), key=lambda x: -x[1])
        )
        breakdown_html = (
            "<h4>USDT Per Exchange (after consolidation)</h4>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<tr><th>Exchange</th><th>USDT</th></tr>"
            f"{rows}</table>"
        )

    consolidation_html = ""
    if consolidation_summary:
        rows = "".join(
            f"<tr><td>{html.escape(t['from_exchange'])}</td>"
            f"<td>${t['amount_usd']:.2f}</td>"
            f"<td>${t['fee_usd']:.4f}</td></tr>"
            for t in consolidation_summary.get("transfers", [])
        )
        moved = consolidation_summary.get("total_moved", 0.0)
        fees = consolidation_summary.get("total_fees", 0.0)
        consolidation_html = (
            "<h4>Emergency Consolidation to Bitfinex Hub</h4>"
            "<p>All available USDT was moved from peripheral exchanges to "
            "<b>Bitfinex</b> using the cheapest withdrawal route per exchange "
            "($0 from MEXC/Bybit free networks, $0.001 from Bitget, $0.01 "
            "from Binance, etc). Bitfinex was chosen because its USDT "
            "withdrawal fees are $0 on 14 networks — the safest hub if you "
            "decide to withdraw, swap, or redistribute.</p>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<tr><th>From</th><th>Amount</th><th>Fee</th></tr>"
            f"{rows}</table>"
            f"<p><b>Total moved:</b> ${moved:.2f} | "
            f"<b>Total consolidation fees:</b> ${fees:.4f}</p>"
        )
    elif consolidation_summary is not None:
        # Empty result — explicitly note that everything was already on Bitfinex
        consolidation_html = (
            "<p><i>No consolidation needed — capital was already on Bitfinex "
            "or below per-exchange dust threshold.</i></p>"
        )

    if is_reminder:
        hours = paused_for_seconds / 3600.0
        header = (
            f"<h3 style='color:red'>REMINDER — Bot Still Paused (~{hours:.1f}h)</h3>"
            "<p>This is an automated reminder. The bot triggered an emergency "
            "stop and is awaiting your manual resume action.</p>"
        )
        subject = f"ArbitrageBot: REMINDER — Still Paused ({hours:.1f}h) | Drawdown -{drawdown_pct:.1f}%"
    else:
        header = "<h3 style='color:red'>Emergency Sell-All Triggered</h3>"
        subject = f"ArbitrageBot: EMERGENCY — Portfolio -{drawdown_pct:.1f}%"

    body = (
        f"{header}"
        f"<p><b>Time:</b> {now}<br>"
        f"<b>Reason:</b> {html.escape(reason)}<br>"
        f"<b>Drawdown:</b> {drawdown_pct:.2f}% "
        f"(${drop:.2f} from peak ${peak_value:.2f})<br>"
        f"<b>Current portfolio:</b> ${current_value:.2f}<br>"
        f"<b>Positions liquidated:</b> {positions_sold}<br>"
        f"<b>Total crypto sold:</b> ${total_sold:.2f}</p>"
        f"{positions_html}"
        f"{consolidation_html}"
        f"{breakdown_html}"
        f"<p style='color:red'><b>Trading is PAUSED. Manual resume required.</b></p>"
        f"{_RESUME_INSTRUCTIONS_HTML}"
    )
    return subject, body


async def notify_emergency(
    reason: str,
    drawdown_pct: float,
    peak_value: float,
    current_value: float,
    positions_sold: int,
    total_sold: float,
    portfolio_breakdown: dict[str, float] | None = None,
    liquidated_positions: list[dict] | None = None,
    consolidation_summary: dict | None = None,
) -> None:
    """Email notification on emergency sell-all.

    Includes drawdown info, positions liquidated, emergency consolidation
    summary (USDT moved to Bitfinex), per-exchange USDT breakdown after
    consolidation, and step-by-step manual-resume instructions.
    """
    subject, body = _build_emergency_html(
        reason=reason,
        drawdown_pct=drawdown_pct,
        peak_value=peak_value,
        current_value=current_value,
        positions_sold=positions_sold,
        total_sold=total_sold,
        portfolio_breakdown=portfolio_breakdown,
        liquidated_positions=liquidated_positions,
        consolidation_summary=consolidation_summary,
        is_reminder=False,
        paused_for_seconds=0.0,
    )
    await send_email_async(subject, body)


async def notify_emergency_reminder(
    reason: str,
    drawdown_pct: float,
    peak_value: float,
    current_value: float,
    paused_for_seconds: float,
    portfolio_breakdown: dict[str, float] | None = None,
) -> None:
    """Hourly reminder while bot is still paused after an emergency.

    Sent when `AnomalyProtection.should_resend_emergency_email()` returns
    True. Uses the same template as the initial email, with a REMINDER
    banner indicating how long the bot has been paused.
    """
    subject, body = _build_emergency_html(
        reason=reason,
        drawdown_pct=drawdown_pct,
        peak_value=peak_value,
        current_value=current_value,
        positions_sold=0,
        total_sold=0.0,
        portfolio_breakdown=portfolio_breakdown,
        liquidated_positions=None,
        consolidation_summary=None,
        is_reminder=True,
        paused_for_seconds=paused_for_seconds,
    )
    await send_email_async(subject, body)
