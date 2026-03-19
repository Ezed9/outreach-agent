"""
Gmail SMTP sender — plain text only, rate-limited to 30/day, 2s between sends.
Stores Message-ID for reply threading.

Daily send count is persisted to .sent_count.json so restarts don't reset the limit.
"""
import json
import os
import smtplib
import time
from datetime import date
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate

MAX_PER_DAY = 30
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

    with smtplib.SMTP_SSL(smtp_host, 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, [to], msg.as_string())

    _save_count(_load_count() + 1)

    # Rate limit: 2 seconds between sends to avoid spam flags
    time.sleep(2)

    return message_id


def remaining_today() -> int:
    return max(0, MAX_PER_DAY - _load_count())
