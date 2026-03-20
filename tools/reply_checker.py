"""
Checks Gmail INBOX for replies to sent cold emails.
Uses imap_tools with In-Reply-To header matching.
"""
import os
from typing import Optional

from imap_tools import H, MailBox


def check_for_replies(message_ids: list[str]) -> list[str]:
    """
    Check if any of the given Message-IDs have received replies.

    Args:
        message_ids: List of Message-ID strings stored when sending

    Returns:
        List of Message-IDs that received at least one reply
    """
    # IMAP may use a different account (e.g. personal Gmail that forwards from sending domain)
    imap_user = os.environ.get("GMAIL_IMAP_USER") or os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ.get("GMAIL_IMAP_PASSWORD") or os.environ["GMAIL_APP_PASSWORD"]
    imap_host = os.environ.get("GMAIL_IMAP_HOST", "imap.gmail.com")

    replied_ids = []
    try:
        with MailBox(imap_host).login(imap_user, gmail_password) as mailbox:
            for msg_id in message_ids:
                # Search by In-Reply-To header (most reliable)
                try:
                    criteria = H("In-Reply-To", msg_id)
                    replies = list(mailbox.fetch(criteria, mark_seen=False))
                    if replies:
                        replied_ids.append(msg_id)
                        continue
                except Exception:
                    pass
                # Fallback: search References header
                try:
                    criteria = H("References", msg_id)
                    refs = list(mailbox.fetch(criteria, mark_seen=False))
                    if refs:
                        replied_ids.append(msg_id)
                except Exception:
                    pass
    except Exception as e:
        print(f"[ReplyChecker] IMAP error: {e}")

    return replied_ids
