"""
Outreach Agent — entry point.

Usage:
  python main.py leads_gyms_sydney.csv        # Draft + review + send
  python main.py leads_*.csv                  # Multiple CSVs
  python main.py --follow-ups                 # Send due follow-ups
  python main.py --status                     # Show tracker table
  python main.py --verify leads_gyms.csv      # Verify emails before sending
  python main.py --check-replies              # Check Gmail for new replies
"""

import csv
import glob
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()


def load_leads_from_csv(filepath: str) -> list[dict]:
    """Load leads from a CSV file. Returns list of dicts."""
    leads = []
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Only keep leads with a website OR email — can't research without one
                website = row.get("website", "").strip()
                email = row.get("email", "").strip()
                if website or email:
                    leads.append({
                        "company_name": row.get("company_name", "").strip(),
                        "website": website,
                        "email": email,
                        "description": row.get("description", "").strip(),
                        "score": int(row.get("score", 5) or 5),
                        "linkedin": row.get("linkedin", "").strip(),
                        "why_good_lead": row.get("why_good_lead", "").strip(),
                    })
    except FileNotFoundError:
        console.print(f"[red]File not found: {filepath}[/red]")
    return leads


def cmd_send(csv_paths: list[str]):
    from outreach import (
        load_tracker, save_tracker, upsert_lead,
        mark_sent, mark_skipped, remaining_today,
        research_and_draft, draft_followup_email,
        review_batch, send_email,
    )

    tracker = load_tracker()

    # Load all leads from CSVs
    all_leads = []
    for path in csv_paths:
        for filepath in glob.glob(path):
            leads = load_leads_from_csv(filepath)
            console.print(f"[cyan]Loaded {len(leads)} leads from {filepath}[/cyan]")
            all_leads.extend(leads)

    if not all_leads:
        console.print("[red]No leads found. Check CSV file paths.[/red]")
        return

    # Filter to only new leads (not already in tracker)
    new_leads = []
    for lead in all_leads:
        rec = upsert_lead(tracker, lead["company_name"], lead["website"], lead["email"])
        if rec["status"] == "pending":
            new_leads.append(lead)

    if not new_leads:
        console.print("[yellow]No new leads to process. All already in tracker.[/yellow]")
        console.print("Run [bold]python main.py --status[/bold] to see existing outreach.")
        save_tracker(tracker)
        return

    console.print(f"\n[bold]Processing {len(new_leads)} new leads[/bold] "
                  f"({remaining_today()} sends remaining today)\n")

    # Draft emails for each lead
    drafts = []
    for i, lead in enumerate(new_leads, 1):
        console.print(f"\n[bold cyan][{i}/{len(new_leads)}] {lead['company_name']}[/bold cyan]")
        try:
            pitch, research, email_draft = research_and_draft(
                lead["company_name"],
                lead["website"],
                lead["email"],
                lead["description"],
            )
            to_email = lead["email"] or _extract_email_from_research(research)
            drafts.append({
                "id": _make_id(lead["company_name"], lead["website"]),
                "company_name": lead["company_name"],
                "to_email": to_email,
                "website": lead["website"],
                "pitch": pitch,
                "subject": email_draft["subject"],
                "body": email_draft["body"],
            })
            # Update tracker with pitch decision and discovered email
            rec = upsert_lead(tracker, lead["company_name"], lead["website"], lead["email"], pitch)
            rec["pitch"] = pitch
            if to_email and not rec["to_email"]:
                rec["to_email"] = to_email
        except Exception as e:
            console.print(f"  [red]Error drafting for {lead['company_name']}: {e}[/red]")

    save_tracker(tracker)

    if not drafts:
        console.print("[red]No drafts generated.[/red]")
        return

    # Batch review
    approved = review_batch(drafts)

    if not approved:
        return

    # Send approved emails
    tracker = load_tracker()
    sent_count = 0
    for draft in approved:
        if not draft["to_email"]:
            console.print(f"[yellow]Skipping {draft['company_name']} — no email address found[/yellow]")
            continue
        try:
            console.print(f"  Sending to {draft['to_email']}...")
            message_id = send_email(draft["to_email"], draft["subject"], draft["body"])
            mark_sent(tracker, draft["id"], "1", draft["subject"], draft["body"], message_id)
            sent_count += 1
            console.print(f"  [green]✓ Sent to {draft['company_name']}[/green]")
        except Exception as e:
            console.print(f"  [red]Failed to send to {draft['company_name']}: {e}[/red]")

    save_tracker(tracker)
    console.print(f"\n[bold green]✓ {sent_count} emails sent.[/bold green]")


def cmd_followups():
    from outreach import (
        load_tracker, save_tracker, mark_sent,
        get_due_followups, send_email, remaining_today,
    )
    from outreach.drafter import draft_followup_email
    from outreach.reviewer import review_batch

    tracker = load_tracker()
    due = get_due_followups(tracker)

    if not due:
        console.print("[green]No follow-ups due today.[/green]")
        return

    console.print(f"[bold cyan]{len(due)} follow-up(s) due[/bold cyan]\n")

    drafts = []
    for rec in due:
        email_num = rec["_next_email_num"]
        prev_email = rec["emails"].get(str(int(email_num) - 1)) or rec["emails"].get("1", {})
        prev_subject = (prev_email or {}).get("subject", "")
        prev_body = (prev_email or {}).get("body", "")

        try:
            draft = draft_followup_email(
                rec["company_name"], prev_subject, prev_body, int(email_num),
                pitch=rec.get("pitch", "")
            )
            drafts.append({
                "id": rec["id"],
                "company_name": rec["company_name"],
                "to_email": rec["to_email"],
                "website": rec["website"],
                "pitch": rec.get("pitch", ""),
                "subject": draft["subject"],
                "body": draft["body"],
                "_email_num": email_num,
            })
        except Exception as e:
            console.print(f"[red]Error drafting follow-up for {rec['company_name']}: {e}[/red]")

    approved = review_batch(drafts)

    sent_count = 0
    for draft in approved:
        try:
            message_id = send_email(draft["to_email"], draft["subject"], draft["body"])
            mark_sent(tracker, draft["id"], draft["_email_num"],
                     draft["subject"], draft["body"], message_id)
            sent_count += 1
            console.print(f"[green]✓ Follow-up sent to {draft['company_name']}[/green]")
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")

    save_tracker(tracker)
    console.print(f"\n[bold green]✓ {sent_count} follow-up(s) sent.[/bold green]")


def cmd_status():
    from outreach.tracker import load_tracker, print_status
    tracker = load_tracker()
    if not tracker:
        console.print("[yellow]No outreach tracked yet. Run python main.py <leads.csv>[/yellow]")
        return
    print_status(tracker)


def cmd_verify(csv_paths: list[str]):
    from tools.verifier import verify_email
    console.print("[bold]Verifying emails...[/bold]\n")
    for path in csv_paths:
        for filepath in glob.glob(path):
            leads = load_leads_from_csv(filepath)
            for lead in leads:
                if lead["email"]:
                    result = verify_email(lead["email"])
                    status = "[green]✓[/green]" if result["valid"] else "[red]✗[/red]"
                    console.print(f"  {status} {lead['email']} — {result['reason']}")


def cmd_check_replies():
    from outreach.tracker import load_tracker, save_tracker, mark_replied
    from tools.reply_checker import check_for_replies

    tracker = load_tracker()
    all_ids = {}
    for lid, rec in tracker.items():
        for n in ["1", "2", "3", "4", "5"]:
            e = rec["emails"].get(n)
            if e and e.get("message_id"):
                all_ids[e["message_id"]] = lid

    if not all_ids:
        console.print("[yellow]No sent emails to check.[/yellow]")
        return

    console.print(f"[cyan]Checking {len(all_ids)} sent emails for replies...[/cyan]")
    replied_msg_ids = check_for_replies(list(all_ids.keys()))

    if not replied_msg_ids:
        console.print("[green]No new replies found.[/green]")
        return

    for msg_id in replied_msg_ids:
        lid = all_ids[msg_id]
        company = tracker[lid]["company_name"]
        mark_replied(tracker, lid)
        console.print(f"[green]✓ Reply detected from {company}![/green]")

    save_tracker(tracker)


def _make_id(company_name: str, website: str) -> str:
    import hashlib
    key = f"{company_name.lower().strip()}|{website.lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _extract_email_from_research(research: dict) -> str:
    emails = research.get("emails", [])
    if emails:
        # Filter out noreply, info@ is fine
        for e in emails:
            if "noreply" not in e.lower() and "no-reply" not in e.lower():
                return e
    return ""


def main():
    args = sys.argv[1:]

    if not args:
        console.print(__doc__)
        return

    if "--status" in args:
        cmd_status()
    elif "--follow-ups" in args or "--followups" in args:
        cmd_followups()
    elif "--check-replies" in args:
        cmd_check_replies()
    elif "--verify" in args:
        csv_files = [a for a in args if a != "--verify"]
        cmd_verify(csv_files)
    else:
        # Treat remaining args as CSV file paths
        cmd_send(args)


if __name__ == "__main__":
    main()
