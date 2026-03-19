"""
Rich CLI batch review interface.
Shows each drafted email and lets you Approve / Edit / Skip.
"""
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

console = Console()


def review_batch(drafts: list[dict]) -> list[dict]:
    """
    Show each draft for review.

    Args:
        drafts: list of {
            "id": str,
            "company_name": str,
            "to_email": str,
            "pitch": str,
            "subject": str,
            "body": str,
            "website": str,
        }

    Returns:
        list of approved drafts (same schema, possibly with edited subject/body)
    """
    if not drafts:
        console.print("[yellow]No drafts to review.[/yellow]")
        return []

    approved = []
    total = len(drafts)

    console.print(f"\n[bold cyan]📬 Reviewing {total} email drafts[/bold cyan]\n")

    for i, draft in enumerate(drafts, 1):
        while True:
            # Display draft
            header = f"[{i}/{total}] {draft['company_name']} — pitch: [bold]{draft['pitch']}[/bold]"
            if draft.get("to_email"):
                header += f" → {draft['to_email']}"

            email_display = (
                f"[bold]Subject:[/bold] {draft['subject']}\n\n"
                f"{draft['body']}"
            )

            console.print(Panel(
                email_display,
                title=header,
                border_style="cyan",
                padding=(1, 2),
            ))

            console.print("\n[bold green][A][/bold green]pprove  "
                         "[bold yellow][E][/bold yellow]dit  "
                         "[bold red][S][/bold red]kip  "
                         "[bold dim][Q][/bold dim]uit\n")

            choice = Prompt.ask("Choice", choices=["a", "e", "s", "q", "A", "E", "S", "Q"],
                                default="a", show_choices=False).lower()

            if choice == "q":
                console.print(f"\n[yellow]Stopped at {i}/{total}. {len(approved)} approved so far.[/yellow]")
                return approved

            elif choice == "s":
                console.print(f"[dim]Skipped {draft['company_name']}[/dim]\n")
                break

            elif choice == "a":
                approved.append(draft)
                console.print(f"[green]✓ Approved[/green]\n")
                break

            elif choice == "e":
                # Edit subject and body
                console.print("\n[bold]Edit subject[/bold] (press Enter to keep):")
                new_subject = input(f"  [{draft['subject']}] → ").strip()
                if new_subject:
                    draft["subject"] = new_subject

                console.print("\n[bold]Edit body[/bold] (paste new body, type END on a new line when done, or press Enter to keep):")
                lines = []
                first = input("  > ")
                if first.strip():
                    lines.append(first)
                    while True:
                        line = input("  > ")
                        if line.strip().upper() == "END":
                            break
                        lines.append(line)
                    draft["body"] = "\n".join(lines)

                approved.append(draft)
                console.print(f"[green]✓ Approved (edited)[/green]\n")
                break

    if approved:
        console.print(f"\n[bold green]✓ {len(approved)}/{total} emails approved[/bold green]")
        confirm = Prompt.ask(
            f"\nSend {len(approved)} emails now?",
            choices=["y", "n"],
            default="y"
        ).lower()
        if confirm != "y":
            console.print("[yellow]Cancelled. No emails sent.[/yellow]")
            return []
    else:
        console.print("\n[yellow]No emails approved.[/yellow]")

    return approved
