from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Lead:
    company_name: str
    website: str
    email: str
    description: str
    source: str = ""
    linkedin: str = ""
    why_good_lead: str = ""
    score: int = 5
    url: str = ""


@dataclass
class EmailDraft:
    subject: str
    body: str


@dataclass
class SentEmail:
    subject: str
    body: str
    sent_at: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class OutreachRecord:
    id: str
    company_name: str
    to_email: str
    website: str
    pitch: str                   # "website" or "ai_automation"
    status: str                  # pending|drafted|approved|sent|replied|skipped|exhausted
    emails: dict = field(default_factory=lambda: {
        "1": None, "2": None, "3": None, "4": None, "5": None
    })
    replied_at: Optional[str] = None
    notes: str = ""

    def next_email_number(self) -> Optional[str]:
        for n in ["1", "2", "3", "4", "5"]:
            if self.emails.get(n) is None:
                return n
        return None

    def last_sent_at(self) -> Optional[str]:
        for n in ["5", "4", "3", "2", "1"]:
            e = self.emails.get(n)
            if e and e.get("sent_at"):
                return e["sent_at"]
        return None

    def sent_message_ids(self) -> list[str]:
        ids = []
        for n in ["1", "2", "3", "4", "5"]:
            e = self.emails.get(n)
            if e and e.get("message_id"):
                ids.append(e["message_id"])
        return ids
