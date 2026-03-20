"""
Scrapes a business website to extract context for email personalisation.
Adapted from leads-agent fetch_webpage — discovers contact/about/services pages.
"""
import re
from urllib.parse import urljoin, urlparse

import html2text
import httpx

CONTACT_PATTERNS = [
    "/contact", "/contact-us", "/about", "/about-us", "/team",
    "/services", "/our-services", "/what-we-do", "/work-with-us",
    "/book", "/booking", "/appointments", "/schedule",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch(url: str, timeout: int = 10) -> str:
    """Fetch a URL and return markdown text."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(resp.text)[:6000]
    except Exception:
        return ""


def _extract_emails(text: str) -> list[str]:
    return list(set(re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)))


def _extract_phone(text: str) -> str:
    match = re.search(r"(\+?[\d\s\-().]{7,20})", text)
    return match.group(1).strip() if match else ""


def research_business(url: str, company_name: str = "") -> dict:
    """
    Scrapes a business website and returns a structured profile for personalisation.

    Returns:
        {
            "url": str,
            "company_name": str,
            "main_content": str,        # markdown of homepage
            "sub_pages": str,           # markdown of discovered sub-pages
            "emails": list[str],
            "phone": str,
            "has_booking": bool,        # detected booking/appointment system
            "has_website": bool,        # True if URL actually loads
            "social_links": dict,       # {"instagram": ..., "facebook": ..., ...}
            "signals": list[str],       # e.g. ["no booking system", "only Facebook page"]
        }
    """
    result = {
        "url": url,
        "company_name": company_name,
        "main_content": "",
        "sub_pages": "",
        "emails": [],
        "phone": "",
        "has_booking": False,
        "has_website": False,
        "social_links": {},
        "signals": [],
    }

    if not url or not url.startswith("http"):
        result["signals"].append("no website")
        return result

    # Fetch homepage
    main_text = _fetch(url)
    if not main_text:
        result["signals"].append("website unreachable")
        return result

    result["has_website"] = True
    result["main_content"] = main_text

    # Extract emails and phone from homepage
    result["emails"] = _extract_emails(main_text)
    result["phone"] = _extract_phone(main_text)

    # Check for booking signals
    booking_keywords = ["book", "booking", "appointment", "schedule", "calendly", "acuity", "square", "fresha", "mindbody"]
    if any(kw in main_text.lower() for kw in booking_keywords):
        result["has_booking"] = True

    # Extract social links
    social_patterns = {
        "instagram": r"instagram\.com/[\w.]+",
        "facebook": r"facebook\.com/[\w.]+",
        "linkedin": r"linkedin\.com/(?:company|in)/[\w-]+",
        "tiktok": r"tiktok\.com/@[\w.]+",
    }
    for platform, pattern in social_patterns.items():
        match = re.search(pattern, main_text, re.IGNORECASE)
        if match:
            result["social_links"][platform] = "https://www." + match.group(0)

    # Fetch sub-pages (contact, about, services)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    sub_texts = []
    for pattern in CONTACT_PATTERNS[:6]:
        sub_url = urljoin(base, pattern)
        text = _fetch(sub_url, timeout=6)
        if text and len(text) > 200:
            sub_texts.append(text[:2000])
            # Extract more emails from sub-pages
            for email in _extract_emails(text):
                if email not in result["emails"]:
                    result["emails"].append(email)
    result["sub_pages"] = "\n\n---\n\n".join(sub_texts)

    # Generate signals (gaps/opportunities)
    full_text = main_text + result["sub_pages"]
    if not result["has_booking"]:
        result["signals"].append("no online booking system")
    if not result["emails"]:
        result["signals"].append("no contact email visible")
    if not result["social_links"]:
        result["signals"].append("no social media presence found")
    if len(main_text) < 500:
        result["signals"].append("very thin website content")
    automation_keywords = ["chatbot", "automation", "ai", "whatsapp", "auto-reply", "crm"]
    if not any(kw in full_text.lower() for kw in automation_keywords):
        result["signals"].append("no automation tools detected")

    # Technology signals
    full_lower = full_text.lower()
    if "wordpress" in full_lower or "theme by" in full_lower or "wp-content" in full_lower:
        result["signals"].append("wordpress site — may need redesign")
    if "wix" in full_lower or "wixsite" in full_lower:
        result["signals"].append("wix template site — limited customization")
    if "squarespace" in full_lower:
        result["signals"].append("squarespace template site")
    if "shopify" in full_lower:
        result["signals"].append("shopify store")

    # Content freshness — check copyright year
    copyright_match = re.search(r'©\s*(\d{4})', full_text)
    if copyright_match:
        year = int(copyright_match.group(1))
        if year < 2024:
            result["signals"].append(f"copyright outdated ({year}) — site may be neglected")

    # Growth signals
    if "hiring" in full_lower or "careers" in full_lower or "join our team" in full_lower:
        result["signals"].append("actively hiring — business is growing")
    if "new location" in full_lower or "now open" in full_lower or "grand opening" in full_lower:
        result["signals"].append("recently expanded or new location")
    if "coming soon" in full_lower:
        result["signals"].append("has coming-soon features — actively developing")

    # Review platform presence
    review_platforms = ["google review", "yelp", "trustpilot", "productreview"]
    if any(rp in full_lower for rp in review_platforms):
        result["signals"].append("has review platform presence")

    return result
