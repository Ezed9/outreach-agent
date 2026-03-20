"""
AI email drafter — researches each business, decides website vs AI automation pitch,
writes a fully personalised plain-text cold email (75–100 words).

Uses same LLM backend chain as leads-agent: Gemini → Groq → OpenRouter → Ollama.
Prompt engineering adapted from kaymen99/sales-outreach-automation-langgraph.
"""
import json
import os
import re

from agent import call_llm
from tools.website_researcher import research_business


# ── Prompts ─────────────────────────────────────────────────────────────────

DECIDE_PITCH_PROMPT = """You are a B2B sales strategist. Based on this business profile, decide whether to pitch:
- "website" — if they have NO website, or a very basic one with no online presence
- "ai_automation" — if they have a website but clearly lack automation (no booking system, no AI chatbot, manual processes)

Business: {company_name}
Website: {website}
Description: {description}
Website content summary: {content_summary}
Signals detected: {signals}

Reply with ONLY one word: either "website" or "ai_automation"."""


DRAFT_EMAIL_PROMPT = """You are an expert cold email copywriter helping a freelancer named {your_name} reach out to local Australian businesses.

## Business Profile
Company: {company_name}
Website: {website}
What they do: {description}
Key signals: {signals}
Website content: {content_summary}

## Pitch Type
You are pitching: {pitch_type}
{pitch_context}

## Email Rules (CRITICAL — follow exactly)
- Plain text only. No HTML, no bullet points, no bold.
- 75–100 words total (count carefully)
- Lowercase subject line (like a personal email, not marketing)
- 4 short paragraphs maximum:
  1. One specific observation about their business (reference something real)
  2. One sentence: what you offer and why it fits them specifically
  3. One line: proof or outcome (e.g. "Helped a Sydney plumber get 3 new bookings in week 1")
  4. Soft CTA: "Worth a quick chat this week?"
- NO spam words: free, guaranteed, risk-free, limited time, act now, click here
- Sign off with: {sign_off}
- Do NOT include your email or phone in the body

## Output Format
Return ONLY valid JSON, nothing else:
{{
  "subject": "lowercase subject line here",
  "body": "full email body here with \\n for line breaks"
}}"""


FOLLOWUP_PROMPT = """Write a short follow-up cold email. This is email #{followup_num} in a sequence.

Previous email sent to {company_name}:
Subject: {prev_subject}
Body: {prev_body}

Pitch type: {pitch_type}
{url_instruction}

Rules:
- 40–60 words maximum
- Different angle from email 1 — don't repeat the same pitch
- Email 2: bump/check-in — "just wanted to make sure this didn't get buried"
- Email 3: add a different value point or ask a question
- Email 4: "closing the loop" — tell them you won't follow up again after this
- Email 5: final permission-based close — "would it be ok to reach out again in a few months?"
- Lowercase subject starting with "re:" to appear as reply thread
- Sign: {sign_off}

Return ONLY valid JSON:
{{
  "subject": "re: original subject",
  "body": "email body here"
}}"""


# ── Main drafting functions ──────────────────────────────────────────────────

def decide_pitch(company_name: str, website: str, description: str, research: dict) -> str:
    """Returns 'website' or 'ai_automation'."""
    content_summary = (research.get("main_content", "") or "")[:800]
    signals = ", ".join(research.get("signals", [])) or "none detected"

    prompt = DECIDE_PITCH_PROMPT.format(
        company_name=company_name,
        website=website or "none",
        description=description,
        content_summary=content_summary,
        signals=signals,
    )
    result = call_llm(prompt).strip().lower()
    if "ai_automation" in result or "automation" in result:
        return "ai_automation"
    return "website"


def draft_initial_email(company_name: str, website: str, description: str, pitch: str, research: dict) -> dict:
    """Draft the first cold email. Returns {"subject": str, "body": str}."""
    your_name = os.environ.get("YOUR_NAME", "Nishit")
    content_summary = (research.get("main_content", "") + "\n" + research.get("sub_pages", ""))[:1200]
    signals = ", ".join(research.get("signals", [])) or "none"

    if pitch == "website":
        sign_off = f"{your_name} — Max Web"
        pitch_type = "Build them a professional website"
        pitch_context = (
            "You're reaching out on behalf of Max Web. Mention 'I run Max Web' once naturally in the email. "
            "Focus on: getting found on Google, looking credible online, converting visitors to bookings and enquiries. "
            "Proof: generate a plausible outcome for a similar type of business (no specific company names). "
            "Do NOT include any URLs or links — email 1 must be completely link-free."
        )
    else:
        sign_off = f"{your_name} — Arkhe AI"
        pitch_type = "AI automation for their business"
        pitch_context = (
            "You're reaching out on behalf of Arkhe AI. Mention 'my team at Arkhe AI' once naturally in the email. "
            "Focus on: saving hours on manual work, auto-booking, AI-powered customer replies, never missing a lead. "
            "Proof: generate a plausible outcome for a similar type of business (no specific company names). "
            "Do NOT include any URLs or links — email 1 must be completely link-free."
        )

    prompt = DRAFT_EMAIL_PROMPT.format(
        your_name=your_name,
        sign_off=sign_off,
        company_name=company_name,
        website=website or "none",
        description=description,
        signals=signals,
        content_summary=content_summary,
        pitch_type=pitch_type,
        pitch_context=pitch_context,
    )

    raw = call_llm(prompt)
    return _parse_email_json(raw)


def draft_followup_email(company_name: str, prev_subject: str, prev_body: str, followup_num: int, pitch: str = "") -> dict:
    """Draft a follow-up email. Returns {"subject": str, "body": str}."""
    your_name = os.environ.get("YOUR_NAME", "Nishit")

    if pitch == "website":
        service_url = os.environ.get("WEBSITE_PORTFOLIO_URL", "")
        sign_off = f"{your_name} — Max Web"
        pitch_type = "web development (Max Web)"
    else:
        service_url = os.environ.get("AI_SITE_URL", "")
        sign_off = f"{your_name} — Arkhe AI"
        pitch_type = "AI automation (Arkhe AI)"

    # Only include URL in follow-up 2 (email 3 in sequence)
    if followup_num == 2 and service_url:
        url_instruction = f'Naturally include this URL once in the body: {service_url}\nExample: "here\'s some of our recent work: {service_url}"'
    else:
        url_instruction = "Do NOT include any URLs or links in this email."

    prompt = FOLLOWUP_PROMPT.format(
        followup_num=followup_num,
        company_name=company_name,
        prev_subject=prev_subject,
        prev_body=prev_body[:500],
        pitch_type=pitch_type,
        url_instruction=url_instruction,
        sign_off=sign_off,
    )
    raw = call_llm(prompt)
    return _parse_email_json(raw)


def research_and_draft(company_name: str, website: str, email: str, description: str) -> tuple[str, dict, dict]:
    """
    Full pipeline: research → decide pitch → draft email.

    Returns:
        (pitch, research_result, email_draft)
        pitch: "website" or "ai_automation"
        email_draft: {"subject": str, "body": str}
    """
    print(f"  [Research] Scraping {website or '(no website)'}...")
    research = research_business(website, company_name) if website else {"signals": ["no website"], "main_content": "", "sub_pages": ""}

    print(f"  [Pitch]    Deciding pitch...")
    pitch = decide_pitch(company_name, website, description, research)

    print(f"  [Draft]    Writing {pitch} email...")
    draft = draft_initial_email(company_name, website, description, pitch, research)

    return pitch, research, draft


def _parse_email_json(raw: str) -> dict:
    """Extract JSON from LLM response, with fallback."""
    raw = raw.strip()
    # Strip markdown fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw.strip())
    # Find JSON object
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if "subject" in data and "body" in data:
                return data
        except json.JSONDecodeError:
            pass
    # Fallback: return raw as body
    return {"subject": "quick question", "body": raw[:500]}
