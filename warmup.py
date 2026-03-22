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

import json
import os
import random
import smtplib
import sys
import time
from datetime import date
from email.mime.text import MIMEText
from email.utils import make_msgid, formatdate

from dotenv import load_dotenv
from imap_tools import MailBox, MailMessageFlags, AND

WARMUP_LOG = ".warmup_log.json"


def load_log() -> list[dict]:
    if os.path.exists(WARMUP_LOG):
        with open(WARMUP_LOG) as f:
            return json.load(f)
    return []


def append_log(entry: dict) -> None:
    log = load_log()
    # Replace existing entry for same date
    log = [e for e in log if e["date"] != entry["date"]]
    log.append(entry)
    log.sort(key=lambda e: e["date"])
    with open(WARMUP_LOG, "w") as f:
        json.dump(log, f, indent=2)


def show_status() -> None:
    log = load_log()
    if not os.path.exists(".warmup_start"):
        print("[Warmup] No warmup started yet.")
        return

    with open(".warmup_start") as f:
        start = date.fromisoformat(f.read().strip())

    today = date.today()
    total_days = (today - start).days + 1

    print(f"\nWarmup tracker — started {start} (day {total_days}/28)")
    print(f"{'Day':<5} {'Date':<12} {'Week':<6} {'Target':<8} {'Sent':<6} {'Status'}")
    print("-" * 52)

    logged = {e["date"]: e for e in log}
    for day_offset in range(28):
        d = date.fromordinal(start.toordinal() + day_offset)
        day_num = day_offset + 1
        week = (day_offset // 7) + 1
        target = [5, 15, 30, 50][day_offset // 7]
        ds = d.isoformat()

        if d > today:
            print(f"{day_num:<5} {ds:<12} {week:<6} {target:<8} {'–':<6} upcoming")
        elif ds in logged:
            e = logged[ds]
            sent = e["sent"]
            status = "✓" if sent >= target else f"partial ({sent}/{target})"
            print(f"{day_num:<5} {ds:<12} {week:<6} {target:<8} {sent:<6} {status}")
        else:
            marker = "← today" if d == today else "missed"
            print(f"{day_num:<5} {ds:<12} {week:<6} {target:<8} {'0':<6} {marker}")

    print()

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


def send_warmup_email(from_addr: str, smtp_user: str, smtp_pass: str, to_addr: str, smtp_host: str = "smtp.gmail.com") -> str:
    subject = random.choice(SUBJECTS)
    body = random.choice(BODIES)
    msg_id = make_msgid(domain=from_addr.split("@")[-1])

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msg_id

    # Brevo uses port 587 (STARTTLS), Gmail uses 465 (SSL)
    if "brevo.com" in smtp_host:
        with smtplib.SMTP(smtp_host, 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP_SSL(smtp_host, 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_addr], msg.as_string())

    return msg_id


def rescue_and_reply(
    inbox_addr: str, inbox_imap_user: str, inbox_imap_pass: str,
    reply_from_addr: str, reply_smtp_user: str, reply_smtp_pass: str,
    imap_host: str = "imap.gmail.com",
    smtp_host: str = "smtp.gmail.com",
) -> int:
    """Find warmup emails in spam/inbox, mark important, send reply."""
    replied = 0
    try:
        with MailBox(imap_host).login(inbox_imap_user, inbox_imap_pass) as mailbox:
            # Check spam folder and rescue
            try:
                mailbox.folder.set("[Gmail]/Spam")
                spam_uids = list(mailbox.uids(AND(from_=reply_from_addr)))
                if spam_uids:
                    mailbox.move(spam_uids, "INBOX")
            except Exception:
                pass

            # Check inbox for warmup emails
            mailbox.folder.set("INBOX")
            msgs = list(mailbox.fetch(AND(from_=reply_from_addr, seen=False), limit=5, mark_seen=True))

            for msg in msgs:
                # Mark as important/starred
                try:
                    mailbox.flag([msg.uid], MailMessageFlags.FLAGGED, True)
                except Exception:
                    pass

                # Send reply from inbox account
                reply_body = random.choice(REPLY_BODIES)
                reply_msg = MIMEText(reply_body, "plain", "utf-8")
                reply_msg["Subject"] = f"Re: {msg.subject}"
                reply_msg["From"] = inbox_addr
                reply_msg["To"] = reply_from_addr
                reply_msg["Date"] = formatdate(localtime=True)
                reply_msg["In-Reply-To"] = msg.headers.get("message-id", [""])[0]

                # Brevo uses port 587 (STARTTLS), Gmail uses 465 (SSL)
                if "brevo.com" in smtp_host:
                    with smtplib.SMTP(smtp_host, 587) as server:
                        server.starttls()
                        server.login(reply_smtp_user, reply_smtp_pass)
                        server.sendmail(inbox_addr, [reply_from_addr], reply_msg.as_string())
                else:
                    with smtplib.SMTP_SSL(smtp_host, 465) as server:
                        server.login(reply_smtp_user, reply_smtp_pass)
                        server.sendmail(inbox_addr, [reply_from_addr], reply_msg.as_string())

                replied += 1
                time.sleep(random.uniform(5, 15))

    except Exception as e:
        print(f"[Warmup] IMAP error: {e}")

    return replied


def run_warmup():
    load_dotenv()

    # Main account (nishit@arkheai.site) — sends via Brevo, receives via Gmail IMAP
    main_addr = os.environ.get("GMAIL_ADDRESS")           # nishit@arkheai.site
    main_smtp_host = os.environ.get("GMAIL_SMTP_HOST", "smtp-relay.brevo.com")
    main_smtp_user = os.environ.get("BREVO_SMTP_USER", main_addr)
    main_smtp_pass = os.environ.get("GMAIL_APP_PASSWORD")
    main_imap_host = os.environ.get("GMAIL_IMAP_HOST", "imap.gmail.com")
    main_imap_user = os.environ.get("GMAIL_IMAP_USER", main_addr)
    main_imap_pass = os.environ.get("GMAIL_IMAP_PASSWORD", main_smtp_pass)

    # Partner account (Gmail) — sends via Gmail SMTP, receives via Gmail IMAP
    partner_addr = os.environ.get("WARMUP_PARTNER_EMAIL")
    partner_pass = os.environ.get("WARMUP_PARTNER_PASSWORD")
    partner_smtp_host = "smtp.gmail.com"
    partner_imap_host = "imap.gmail.com"

    if not all([main_addr, main_smtp_pass, partner_addr, partner_pass]):
        print("[Warmup] Missing credentials. Set GMAIL_ADDRESS, GMAIL_APP_PASSWORD, "
              "WARMUP_PARTNER_EMAIL, WARMUP_PARTNER_PASSWORD in .env")
        return

    daily_limit = get_daily_limit()
    print(f"[Warmup] Daily target: {daily_limit} warmup emails")
    print(f"[Warmup] Main: {main_addr} via {main_smtp_host}")
    print(f"[Warmup] Partner: {partner_addr} via {partner_smtp_host}")

    sent = 0
    for i in range(daily_limit):
        try:
            if i % 2 == 0:
                # Main → Partner (send via Brevo)
                from_addr = main_addr
                smtp_user, smtp_pass, smtp_host = main_smtp_user, main_smtp_pass, main_smtp_host
                to_addr = partner_addr
                # Receiver is partner — check partner IMAP, reply via partner Gmail SMTP
                recv_addr = partner_addr
                recv_imap_user, recv_imap_pass = partner_addr, partner_pass
                recv_imap_host = partner_imap_host
                reply_smtp_user, reply_smtp_pass = partner_addr, partner_pass
                reply_smtp_host = partner_smtp_host
            else:
                # Partner → Main (send via Gmail)
                from_addr = partner_addr
                smtp_user, smtp_pass, smtp_host = partner_addr, partner_pass, partner_smtp_host
                to_addr = main_addr
                # Receiver is main — check main IMAP, reply via Brevo
                recv_addr = main_addr
                recv_imap_user, recv_imap_pass = main_imap_user, main_imap_pass
                recv_imap_host = main_imap_host
                reply_smtp_user, reply_smtp_pass = main_smtp_user, main_smtp_pass
                reply_smtp_host = main_smtp_host

            print(f"  [{i+1}/{daily_limit}] Sending warmup: {from_addr} → {to_addr}")
            send_warmup_email(from_addr, smtp_user, smtp_pass, to_addr, smtp_host)
            sent += 1

            # Wait and then rescue + reply
            wait = random.uniform(30, 90)
            time.sleep(wait)

            replied = rescue_and_reply(
                inbox_addr=recv_addr,
                inbox_imap_user=recv_imap_user,
                inbox_imap_pass=recv_imap_pass,
                reply_from_addr=from_addr,
                reply_smtp_user=reply_smtp_user,
                reply_smtp_pass=reply_smtp_pass,
                imap_host=recv_imap_host,
                smtp_host=reply_smtp_host,
            )
            if replied:
                print(f"  [Warmup] Replied to {replied} warmup email(s)")

            time.sleep(random.uniform(10, 30))

        except Exception as e:
            print(f"  [Warmup] Error on send {i+1}: {e}")
            time.sleep(10)

    print(f"\n[Warmup] Done. Sent {sent}/{daily_limit} warmup emails today.")

    with open(".warmup_start") as f:
        start = date.fromisoformat(f.read().strip())
    day_num = (date.today() - start).days + 1

    append_log({
        "date": date.today().isoformat(),
        "day": day_num,
        "week": (day_num - 1) // 7 + 1,
        "target": daily_limit,
        "sent": sent,
    })


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        show_status()
    else:
        run_warmup()
