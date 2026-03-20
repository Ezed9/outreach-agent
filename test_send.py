"""Quick test: send one email and log the Message-ID for reply tracking."""
from dotenv import load_dotenv
load_dotenv()

from outreach.sender import send_email
from outreach.tracker import load_tracker, save_tracker, upsert_lead, mark_sent

TO = "nishitbaishya9@gmail.com"
SUBJECT = "test reply flow"
BODY = """Hey Nishit,

This is a test email from the outreach agent. Reply to this and then run:

  python main.py --check-replies

to confirm reply detection is working.

Nishit — Arkhe AI"""

print(f"Sending test email to {TO}...")
message_id = send_email(TO, SUBJECT, BODY)
print(f"Sent! Message-ID: {message_id}")

# Log it in the tracker so --check-replies can find the reply
tracker = load_tracker()
upsert_lead(tracker, "Test Reply Account", "https://test.internal", TO, campaign="test")
lid = list(tracker.keys())[-1]
mark_sent(tracker, lid, "1", SUBJECT, BODY, message_id)
save_tracker(tracker)
print("Logged in tracker. Reply to the email then run: python main.py --check-replies")
