"""
Pre-flight check — run before starting outreach.
Verifies DNS, SMTP credentials, LLM access, and mail-tester score reminder.
"""
import os
import smtplib
import socket

from dotenv import load_dotenv

load_dotenv()


def check_env():
    required = ["GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "YOUR_NAME"]
    llm_keys = ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"  ✗ Missing .env vars: {', '.join(missing)}")
        return False
    has_llm = any(os.environ.get(k) for k in llm_keys)
    if not has_llm:
        print("  ✗ No LLM key found. Set GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY")
        return False
    print("  ✓ Environment variables OK")
    return True


def check_gmail():
    addr = os.environ.get("GMAIL_ADDRESS", "")
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    if not addr or not pwd:
        print("  ✗ SMTP credentials not set")
        return False
    try:
        if "brevo.com" in host:
            login_user = os.environ.get("BREVO_SMTP_USER", addr)
            with smtplib.SMTP(host, 587, timeout=10) as server:
                server.starttls()
                server.login(login_user, pwd)
        else:
            with smtplib.SMTP_SSL(host, 465, timeout=10) as server:
                server.login(addr, pwd)
        print(f"  ✓ SMTP login OK ({addr} via {host})")
        return True
    except smtplib.SMTPAuthenticationError:
        print("  ✗ SMTP auth failed. Check GMAIL_APP_PASSWORD")
        return False
    except Exception as e:
        print(f"  ✗ SMTP error: {e}")
        return False


def check_dns():
    try:
        import dns.resolver
        addr = os.environ.get("GMAIL_ADDRESS", "")
        if not addr or "@" not in addr:
            print("  ✗ GMAIL_ADDRESS not set")
            return False
        domain = addr.split("@")[1]
        mx = dns.resolver.resolve(domain, "MX")
        print(f"  ✓ MX records found for {domain}: {[str(r.exchange) for r in mx][:2]}")
        return True
    except Exception as e:
        print(f"  ✗ DNS check failed: {e}")
        return False


def check_ollama():
    try:
        import httpx
        resp = httpx.get("http://localhost:11434", timeout=2)
        print("  ✓ Ollama running (local LLM available)")
        return True
    except Exception:
        print("  ℹ Ollama not running (optional, cloud LLMs will be used)")
        return False


def main():
    print("\n🔍 Outreach Agent Pre-flight Check\n")
    print("1. Environment variables")
    check_env()
    print("\n2. Gmail SMTP")
    check_gmail()
    print("\n3. DNS")
    check_dns()
    print("\n4. Ollama (optional)")
    check_ollama()
    print("\n5. Manual checks needed:")
    print("  → Test your sending domain at https://mail-tester.com (aim 9+/10)")
    print("  → Add your domain to https://postmaster.google.com")
    print("  → Verify SPF/DKIM/DMARC at https://mxtoolbox.com/emailhealth")
    print("  → Run warmup.py daily for 4 weeks before cold outreach\n")


if __name__ == "__main__":
    main()
