"""
Email verification via DNS MX lookup + SMTP RCPT check.
No paid API — runs locally using dnspython + smtplib.
"""
import smtplib
import socket
from typing import Optional

import dns.resolver


def verify_email(email: str, from_address: str = "verify@example.com", timeout: int = 10) -> dict:
    """
    Verify an email address exists.

    Steps:
    1. Format check
    2. DNS MX lookup for the domain
    3. SMTP RCPT TO handshake

    Returns:
        {"email": str, "valid": bool, "reason": str}

    Caveats:
    - Some servers (Yahoo, Hotmail) accept all addresses — result may be false positive
    - Port 25 may be blocked on cloud hosts — run locally
    """
    if "@" not in email:
        return {"email": email, "valid": False, "reason": "invalid format"}

    domain = email.split("@")[1].lower()

    # MX lookup
    try:
        mx_records = dns.resolver.resolve(domain, "MX", lifetime=timeout)
        mx_host = sorted(mx_records, key=lambda r: r.preference)[0].exchange.to_text().rstrip(".")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
        return {"email": email, "valid": False, "reason": "no MX record found"}
    except Exception as e:
        return {"email": email, "valid": False, "reason": f"DNS error: {e}"}

    # SMTP check
    try:
        server = smtplib.SMTP(timeout=timeout)
        server.connect(mx_host, 25)
        server.helo(socket.getfqdn())
        server.mail(from_address)
        code, _ = server.rcpt(email)
        server.quit()
        if code == 250:
            return {"email": email, "valid": True, "reason": "SMTP accepted"}
        else:
            return {"email": email, "valid": False, "reason": f"SMTP rejected (code {code})"}
    except smtplib.SMTPConnectError:
        # Port 25 blocked — fall back to just trusting the MX record
        return {"email": email, "valid": True, "reason": "MX exists (SMTP blocked, assuming valid)"}
    except Exception as e:
        return {"email": email, "valid": False, "reason": f"SMTP error: {e}"}


def verify_list(emails: list[str], from_address: str = "verify@example.com") -> list[dict]:
    return [verify_email(e, from_address) for e in emails]
