"""
Email warmup script — run daily for 4 weeks before cold outreach.
Sends between two accounts, rescues from spam, marks as important, replies.

Adapted from: github.com/manojnilanga/mail-server-warmup

Setup:
  Add WARMUP_PARTNER_EMAIL and WARMUP_PARTNER_PASSWORD to .env
  (a second Gmail account you control)

Schedule:
  Week 1: 5 sends/day
  Week 2: 15 sends/day
  Week 3: 30 sends/day
  Week 4: 50 sends/day
"""

import os
import random
import smtplib
import time
from datetime import date
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate

from dotenv import load_dotenv
from imap_tools import MailBox, MailMessageFlags, AND

load_dotenv()

SUBJECTS = [
    "checking in",
    "quick thought",
    "following up",
    "wanted to share something",
    "have a minute?",
    "something interesting",
    "a question for you",
    "touching base",
]

BODIES = [
    "Hey, just wanted to check in and see how things are going your end. Let me know when you have a moment to chat.",
    "Was thinking about what we discussed the other day — curious to hear your thoughts when you get a chance.",
    "Quick one — are you free for a brief call sometime this week? Would love to catch up.",
    "Something came across my desk that made me think of you. Will share more soon.",
    "Hope the week is treating you well. Just wanted to reach out and say hi.",
    "Been a while! How are things going on your end? Would love to reconnect.",
]

REPLY_BODIES = [
    "Thanks for reaching out! Yes, sounds good — I'll follow up soon.",
    "Great to hear from you. Happy to chat whenever works.",
    "Appreciate you thinking of me. Let's connect this week.",
    "Good timing! I was actually going to reach out. Let's chat.",
]


def get_daily_limit() -> int:
    """Ramp schedule based on how long warmup has been running."""
    if not os.path.exists(".warmup_start"):
        with open(".warmup_start", "w") as f:
            f.write(date.today().isoformat())
        return 5

    with open(".warmup_start") as f:
        start = date.fromisoformat(f.read().strip())

    days = (date.today() - start).days
    if days < 7:
        return 5
    elif days < 14:
        return 15
    elif days < 21:
        return 30
    else:
        return 50


def send_warmup_email(from_addr: str, from_pass: str, to_addr: str, smtp_host: str = "smtp.gmail.com") -> str:
    subject = random.choice(SUBJECTS)
    body = random.choice(BODIES)
    msg_id = make_msgid(domain=from_addr.split("@")[-1])

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msg_id

    with smtplib.SMTP_SSL(smtp_host, 465) as server:
        server.login(from_addr, from_pass)
        server.sendmail(from_addr, [to_addr], msg.as_string())

    return msg_id


def rescue_and_reply(
    inbox_addr: str, inbox_pass: str,
    reply_to_addr: str, reply_to_pass: str,
    imap_host: str = "imap.gmail.com",
    smtp_host: str = "smtp.gmail.com",
) -> int:
    """Find warmup emails in spam/inbox, mark important, send reply."""
    replied = 0
    try:
        with MailBox(imap_host).login(inbox_addr, inbox_pass) as mailbox:
            # Check spam folder and rescue
            try:
                mailbox.folder.set("[Gmail]/Spam")
                spam_uids = list(mailbox.uids(AND(from_=reply_to_addr)))
                if spam_uids:
                    mailbox.move(spam_uids, "INBOX")
            except Exception:
                pass

            # Check inbox for warmup emails
            mailbox.folder.set("INBOX")
            msgs = list(mailbox.fetch(AND(from_=reply_to_addr, seen=False), limit=5, mark_seen=True))

            for msg in msgs:
                # Mark as important/starred
                try:
                    mailbox.flag([msg.uid], MailMessageFlags.FLAGGED, True)
                except Exception:
                    pass

                # Send reply
                reply_body = random.choice(REPLY_BODIES)
                reply_msg = MIMEText(reply_body, "plain", "utf-8")
                reply_msg["Subject"] = f"Re: {msg.subject}"
                reply_msg["From"] = inbox_addr
                reply_msg["To"] = reply_to_addr
                reply_msg["Date"] = formatdate(localtime=True)
                reply_msg["In-Reply-To"] = msg.headers.get("message-id", [""])[0]

                with smtplib.SMTP_SSL(smtp_host, 465) as server:
                    server.login(inbox_addr, inbox_pass)
                    server.sendmail(inbox_addr, [reply_to_addr], reply_msg.as_string())

                replied += 1
                time.sleep(random.uniform(5, 15))

    except Exception as e:
        print(f"[Warmup] IMAP error: {e}")

    return replied


def run_warmup():
    load_dotenv()

    main_addr = os.environ.get("GMAIL_ADDRESS")
    main_pass = os.environ.get("GMAIL_APP_PASSWORD")
    partner_addr = os.environ.get("WARMUP_PARTNER_EMAIL")
    partner_pass = os.environ.get("WARMUP_PARTNER_PASSWORD")

    if not all([main_addr, main_pass, partner_addr, partner_pass]):
        print("[Warmup] Missing credentials. Set GMAIL_ADDRESS, GMAIL_APP_PASSWORD, "
              "WARMUP_PARTNER_EMAIL, WARMUP_PARTNER_PASSWORD in .env")
        return

    daily_limit = get_daily_limit()
    print(f"[Warmup] Daily target: {daily_limit} warmup emails")

    sent = 0
    for i in range(daily_limit):
        try:
            # Alternate direction each send
            if i % 2 == 0:
                from_addr, from_pass = main_addr, main_pass
                to_addr = partner_addr
            else:
                from_addr, from_pass = partner_addr, partner_pass
                to_addr = main_addr

            print(f"  [{i+1}/{daily_limit}] Sending warmup: {from_addr} → {to_addr}")
            send_warmup_email(from_addr, from_pass, to_addr)
            sent += 1

            # Wait and then rescue + reply
            wait = random.uniform(30, 90)
            time.sleep(wait)

            replied = rescue_and_reply(to_addr,
                                       main_pass if to_addr == main_addr else partner_pass,
                                       from_addr, from_pass)
            if replied:
                print(f"  [Warmup] Replied to {replied} warmup email(s)")

            time.sleep(random.uniform(10, 30))

        except Exception as e:
            print(f"  [Warmup] Error on send {i+1}: {e}")
            time.sleep(10)

    print(f"\n[Warmup] Done. Sent {sent}/{daily_limit} warmup emails today.")


if __name__ == "__main__":
    run_warmup()
