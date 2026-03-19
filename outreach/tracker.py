import hashlib
import json
import os
from datetime import date, datetime, timedelta
from typing import Optional

from models import OutreachRecord

TRACKER_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outreach_tracker.json")

# Follow-up schedule: email number → days after email 1 was sent
FOLLOWUP_DAYS = {"2": 3, "3": 7, "4": 14, "5": 21}


def _make_id(company_name: str, website: str) -> str:
    key = f"{company_name.lower().strip()}|{website.lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def load_tracker() -> dict[str, dict]:
    if not os.path.exists(TRACKER_FILE):
        return {}
    with open(TRACKER_FILE) as f:
        return json.load(f)


def save_tracker(tracker: dict[str, dict]) -> None:
    with open(TRACKER_FILE, "w") as f:
        json.dump(tracker, f, indent=2)


def upsert_lead(tracker: dict, company_name: str, website: str, email: str, pitch: str = "") -> dict:
    lid = _make_id(company_name, website)
    if lid not in tracker:
        tracker[lid] = {
            "id": lid,
            "company_name": company_name,
            "to_email": email,
            "website": website,
            "pitch": pitch,
            "status": "pending",
            "emails": {"1": None, "2": None, "3": None, "4": None, "5": None},
            "replied_at": None,
            "notes": "",
        }
    return tracker[lid]


def mark_sent(tracker: dict, lid: str, email_num: str, subject: str, body: str, message_id: str) -> None:
    tracker[lid]["emails"][email_num] = {
        "subject": subject,
        "body": body,
        "sent_at": date.today().isoformat(),
        "message_id": message_id,
    }
    tracker[lid]["status"] = "sent"


def mark_replied(tracker: dict, lid: str) -> None:
    tracker[lid]["replied_at"] = datetime.now().isoformat()
    tracker[lid]["status"] = "replied"


def mark_skipped(tracker: dict, lid: str) -> None:
    tracker[lid]["status"] = "skipped"


def get_due_followups(tracker: dict) -> list[dict]:
    """Return records where a follow-up is due today."""
    due = []
    today = date.today()
    for lid, rec in tracker.items():
        if rec["status"] in ("replied", "skipped", "exhausted"):
            continue
        # Find next email number to send
        next_num = None
        for n in ["2", "3", "4", "5"]:
            if rec["emails"].get(n) is None:
                next_num = n
                break
        if not next_num:
            rec["status"] = "exhausted"
            continue
        # Check if email 1 was sent
        email1 = rec["emails"].get("1")
        if not email1 or not email1.get("sent_at"):
            continue
        sent_date = date.fromisoformat(email1["sent_at"])
        days_needed = FOLLOWUP_DAYS[next_num]
        if (today - sent_date).days >= days_needed:
            due.append({**rec, "_next_email_num": next_num})
    return due


def get_pending(tracker: dict) -> list[dict]:
    return [r for r in tracker.values() if r["status"] == "pending"]


def print_status(tracker: dict) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Outreach Status", show_lines=True)
    table.add_column("#", width=3)
    table.add_column("Company", min_width=20)
    table.add_column("Pitch", width=12)
    table.add_column("Status", width=12)
    table.add_column("Sent", width=6)
    table.add_column("Last sent", width=12)
    table.add_column("Replied", width=10)

    for i, rec in enumerate(tracker.values(), 1):
        sent_count = sum(1 for e in rec["emails"].values() if e and e.get("sent_at"))
        last_sent = ""
        for n in ["5", "4", "3", "2", "1"]:
            e = rec["emails"].get(n)
            if e and e.get("sent_at"):
                last_sent = e["sent_at"]
                break
        status_color = {
            "pending": "yellow",
            "sent": "cyan",
            "replied": "green",
            "skipped": "dim",
            "exhausted": "red",
        }.get(rec["status"], "white")
        table.add_row(
            str(i),
            rec["company_name"],
            rec.get("pitch", ""),
            f"[{status_color}]{rec['status']}[/{status_color}]",
            str(sent_count),
            last_sent,
            "✓" if rec.get("replied_at") else "",
        )
    console.print(table)
    console.print(f"\nTotal: {len(tracker)} leads tracked")
