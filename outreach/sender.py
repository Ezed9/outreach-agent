"""
SMTP sender — plain text only, rate-limited to 30/day, 2s between sends.
Stores Message-ID for reply threading.

Supports Gmail (port 465/SSL) and Brevo (port 587/TLS) automatically.
Daily send count is persisted to .sent_count.json so restarts don't reset the limit.
"""
import json
import os
import re
import smtplib
import time
from datetime import date
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate

MAX_PER_DAY = 30

# Box-drawing chars that indicate corrupted copy-paste from terminal
_BOX_CHARS = re.compile(r'[│─┌┐└┘╭╮╰╯┬┴├┤┼╔╗╚╝║═]')
_COUNT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".sent_count.json")


def _load_count() -> int:
    """Load today's sent count from disk. Returns 0 if no record for today."""
    try:
        with open(_COUNT_FILE) as f:
            data = json.load(f)
        if data.get("date") == date.today().isoformat():
            return int(data.get("count", 0))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return 0


def _save_count(count: int) -> None:
    with open(_COUNT_FILE, "w") as f:
        json.dump({"date": date.today().isoformat(), "count": count}, f)


def _check_daily_limit():
    count = _load_count()
    if count >= MAX_PER_DAY:
        raise RuntimeError(f"Daily send limit reached ({MAX_PER_DAY}/day). Resume tomorrow.")


def send_email(to: str, subject: str, body: str) -> str:
    """
    Send a plain-text email via Gmail SMTP.

    Returns:
        message_id (str) — stored for reply tracking

    Raises:
        RuntimeError if daily limit hit or credentials missing
    """
    _check_daily_limit()

    # Pre-send validation — catch corrupted emails before they go out
    if _BOX_CHARS.search(subject) or _BOX_CHARS.search(body):
        raise RuntimeError(f"Email to {to} contains terminal box-drawing characters — aborting send. Review and re-draft.")
    if len(subject) < 3 or len(subject) > 200:
        raise RuntimeError(f"Email to {to} has suspicious subject length ({len(subject)} chars) — aborting send.")
    if len(body) < 20:
        raise RuntimeError(f"Email to {to} has suspiciously short body ({len(body)} chars) — aborting send.")

    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    your_name = os.environ.get("YOUR_NAME", "")

    if not gmail_address or not app_password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")

    message_id = make_msgid(domain=gmail_address.split("@")[-1])

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{your_name} <{gmail_address}>" if your_name else gmail_address
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = message_id

    # Brevo uses port 587 (STARTTLS), Gmail uses 465 (SSL)
    if "brevo.com" in smtp_host:
        brevo_user = os.environ.get("BREVO_SMTP_USER", gmail_address)
        with smtplib.SMTP(smtp_host, 587) as server:
            server.starttls()
            server.login(brevo_user, app_password)
            server.sendmail(gmail_address, [to], msg.as_string())
    else:
        with smtplib.SMTP_SSL(smtp_host, 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, [to], msg.as_string())

    _save_count(_load_count() + 1)

    # Rate limit: 2 seconds between sends to avoid spam flags
    time.sleep(2)

    return message_id


def remaining_today() -> int:
    return max(0, MAX_PER_DAY - _load_count())
