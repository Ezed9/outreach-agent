"""
AI email drafter — researches each business, decides website vs AI automation pitch,
writes a fully personalised plain-text cold email (50–125 words).

Uses same LLM backend chain as leads-agent: Gemini → Groq → OpenRouter → Ollama.
Prompt engineering adapted from kaymen99/sales-outreach-automation-langgraph.
"""
import json
import os
import re

from agent import call_llm
from tools.website_researcher import research_business


# ── Spam word blocklist ──────────────────────────────────────────────────────

SPAM_WORDS = [
    "free", "guaranteed", "risk-free", "act now", "limited time",
    "earn money", "click here", "winner", "congratulations",
    "unsubscribe", "no obligation", "100%", "discount", "offer",
    "deal", "hurry", "exclusive", "instant",
]

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

## Framework (choose the best fit for this lead — do NOT name the framework in the email)
Pick ONE of these structures:
- AIDA: specific observation about them → insight that sparks interest → outcome they'd desire → clear ask
- PAS: name a pain they likely have → show consequences of ignoring it → present your solution
- BAB: describe their current situation → paint the better situation → bridge with what you offer

## Email Rules (CRITICAL — follow exactly)
- Plain text only. No HTML, no bullet points, no bold, no markdown.
- 50–125 words total (count carefully)
- Subject line: 2–4 words, all lowercase, no punctuation
  Good examples: "quick question", "{company_name_lower} website", "saw your work"
  Bad examples: "Exciting Opportunity!", "I can help you", "Hello there!"
- Opening line MUST reference something specific about THEIR business — not about you
- Do NOT start with "I noticed..." or "I came across..." — be more creative
- End with ONE clear question as your CTA. Pick the most natural style:
  - Binary: "Would this be useful for {company_name}?"
  - Specific time: "Open to a 15-min call Tues or Wed?"
  - Permission: "Mind if I send over how this would work for you?"
  Do NOT use: "Worth a chat?", "Let me know", "Would love to connect", "Thoughts?"
- NO spam words: free, guaranteed, risk-free, limited time, act now, click here, discount, exclusive
- Sign off with: {sign_off}
- Do NOT include your email, phone, or any URLs in the body

## Output Format
Return ONLY valid JSON, nothing else:
{{
  "subject": "lowercase subject here",
  "body": "full email body here with \\n for line breaks"
}}"""


FOLLOWUP_ANGLES = {
    2: """NEW VALUE — share one relevant stat, insight, or industry observation they'd find useful.
Do NOT say "following up", "bumping this", "checking in", or "just wanted to make sure".
Give them something new — a data point, a trend, a competitor observation.
Example angle: "most {industry} are losing X hours/week to {problem} — thought you'd want to know"
30–60 words.""",

    3: """PATTERN INTERRUPT — ultra-short, completely different energy from emails 1-2.
2–3 sentences maximum (20–40 words). Should feel like a quick text, not a business email.
Ask ONE direct question. No preamble, no recap of previous emails.
Example: "quick q — is {pain_point} something you're actively trying to solve, or is it on the back burner?"
20–40 words.""",

    4: """SOCIAL PROOF — brief case study or specific outcome for a similar type of business.
Format: "[Business type] in [location] used our [solution] and saw [specific plausible result]."
Make the result plausible and specific to their industry. No real company names.
End with: "happy to show you how — takes 15 min" or similar low-effort CTA.
30–50 words.""",

    5: """BREAKUP EMAIL — signal you're done reaching out. Zero pressure, warm close.
This is your LAST email. Do NOT pitch, do NOT sell, do NOT ask for a meeting.
Acknowledge they're busy. Wish them well. Leave the door open.
Example: "looks like the timing isn't right — totally get it. if things change, i'm around. wishing {company_name} the best."
25–40 words maximum.""",
}


FOLLOWUP_PROMPT = """Write follow-up email #{followup_num} for {company_name}.

## Context
Original email subject: {prev_subject}
Original email body (for reference): {prev_body}
Pitch type: {pitch_type}

## This Email's Angle
{angle_instruction}

## Rules
- Plain text only. No HTML, no bullet points, no bold.
- Lowercase subject starting with "re:" to appear as reply thread
- {url_instruction}
- NO spam words: free, guaranteed, risk-free, limited time, act now, click here, discount, exclusive
- Sign: {sign_off}

Return ONLY valid JSON:
{{
  "subject": "re: original subject",
  "body": "email body here"
}}"""


# ── Validation ───────────────────────────────────────────────────────────────

def _validate_email_draft(draft: dict, email_num: int = 1) -> list[str]:
    """Validate a drafted email. Returns list of warning strings (empty = all good)."""
    warnings = []
    subject = draft.get("subject", "")
    body = draft.get("body", "")
    combined = (subject + " " + body).lower()

    # Spam word check
    for word in SPAM_WORDS:
        if word in combined:
            warnings.append(f"Spam word detected: '{word}'")

    # Word count
    word_count = len(body.split())
    if email_num == 1:
        if word_count < 50:
            warnings.append(f"Too short: {word_count} words (min 50)")
        elif word_count > 125:
            warnings.append(f"Too long: {word_count} words (max 125)")
    else:
        if word_count < 20:
            warnings.append(f"Too short: {word_count} words (min 20)")
        elif word_count > 70:
            warnings.append(f"Too long: {word_count} words (max 70)")

    # Subject format
    if subject != subject.lower():
        warnings.append("Subject not lowercase")
    if len(subject.split()) > 6:
        warnings.append(f"Subject too long: {len(subject.split())} words (max 6)")
    if "!" in subject:
        warnings.append("Subject contains exclamation mark")

    # CTA check (email 1 only — follow-ups like breakup emails don't need a question)
    if email_num == 1:
        # Check if a question mark appears in the last ~200 chars of the body
        tail = body[-200:] if len(body) > 200 else body
        if "?" not in tail:
            warnings.append("No question/CTA found near end of email")

    # No links in email 1
    if email_num == 1:
        if re.search(r'https?://|www\.|\.com/', body):
            warnings.append("Email 1 contains a URL/link (should be link-free)")

    return warnings


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
    """Draft the first cold email. Returns {"subject": str, "body": str, "warnings": list}."""
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
        company_name_lower=company_name.lower(),
        website=website or "none",
        description=description,
        signals=signals,
        content_summary=content_summary,
        pitch_type=pitch_type,
        pitch_context=pitch_context,
    )

    raw = call_llm(prompt)
    draft = _parse_email_json(raw)

    # Validate and retry once if needed
    warnings = _validate_email_draft(draft, email_num=1)
    if warnings:
        retry_prompt = (
            f"The email you wrote has these issues:\n"
            + "\n".join(f"- {w}" for w in warnings)
            + "\n\nRewrite fixing ONLY these issues. Keep everything else identical.\n"
            "Return ONLY valid JSON: {\"subject\": \"...\", \"body\": \"...\"}"
        )
        raw2 = call_llm(retry_prompt)
        draft2 = _parse_email_json(raw2)
        warnings2 = _validate_email_draft(draft2, email_num=1)
        if len(warnings2) < len(warnings):
            draft = draft2
            warnings = warnings2

    if warnings:
        print(f"  [WARN] Draft has {len(warnings)} issue(s): {', '.join(warnings)}")
    draft["warnings"] = warnings
    return draft


def draft_followup_email(company_name: str, prev_subject: str, prev_body: str, followup_num: int, pitch: str = "") -> dict:
    """Draft a follow-up email. Returns {"subject": str, "body": str, "warnings": list}."""
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

    # Get the specific angle for this follow-up number
    angle_instruction = FOLLOWUP_ANGLES.get(followup_num, FOLLOWUP_ANGLES[5])

    prompt = FOLLOWUP_PROMPT.format(
        followup_num=followup_num,
        company_name=company_name,
        prev_subject=prev_subject,
        prev_body=prev_body[:500],
        pitch_type=pitch_type,
        angle_instruction=angle_instruction,
        url_instruction=url_instruction,
        sign_off=sign_off,
    )
    raw = call_llm(prompt)
    draft = _parse_email_json(raw)

    # Validate and retry once if needed
    warnings = _validate_email_draft(draft, email_num=followup_num)
    if warnings:
        retry_prompt = (
            f"The email you wrote has these issues:\n"
            + "\n".join(f"- {w}" for w in warnings)
            + "\n\nRewrite fixing ONLY these issues. Keep everything else identical.\n"
            "Return ONLY valid JSON: {\"subject\": \"...\", \"body\": \"...\"}"
        )
        raw2 = call_llm(retry_prompt)
        draft2 = _parse_email_json(raw2)
        warnings2 = _validate_email_draft(draft2, email_num=followup_num)
        if len(warnings2) < len(warnings):
            draft = draft2
            warnings = warnings2

    if warnings:
        print(f"  [WARN] Follow-up #{followup_num} has {len(warnings)} issue(s): {', '.join(warnings)}")
    draft["warnings"] = warnings
    return draft


def research_and_draft(company_name: str, website: str, email: str, description: str) -> tuple[str, dict, dict]:
    """
    Full pipeline: research → decide pitch → draft email.

    Returns:
        (pitch, research_result, email_draft)
        pitch: "website" or "ai_automation"
        email_draft: {"subject": str, "body": str, "warnings": list}
    """
    print(f"  [Research] Scraping {website or '(no website)'}...")
    research = research_business(website, company_name) if website else {"signals": ["no website"], "main_content": "", "sub_pages": ""}

    print(f"  [Pitch]    Deciding pitch...")
    pitch = decide_pitch(company_name, website, description, research)

    print(f"  [Draft]    Writing {pitch} email...")
    draft = draft_initial_email(company_name, website, description, pitch, research)

    return pitch, research, draft


def _parse_email_json(raw: str) -> dict:
    """Extract JSON from LLM response, with multiple fallbacks."""
    raw = raw.strip()
    # Strip markdown fences (```json ... ```)
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw.strip())

    # Try 1: valid JSON parse
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if "subject" in data and "body" in data:
                data["body"] = data["body"].replace("\\n", "\n").strip()
                return data
        except json.JSONDecodeError:
            pass

    # Try 2: LLM returned JSON with unescaped newlines in string values (invalid JSON)
    # Extract subject and body with regex instead
    subj_match = re.search(r'"subject"\s*:\s*"([^"]*)"', raw)
    body_match = re.search(r'"body"\s*:\s*"(.*?)(?:"\s*\}|"\s*$)', raw, re.DOTALL)
    if subj_match and body_match:
        subject = subj_match.group(1).strip()
        body = body_match.group(1).replace("\\n", "\n").strip()
        if subject and body:
            return {"subject": subject, "body": body}

    # Try 3: plain text with "Subject: ..." line
    subj_line = re.search(r'(?:subject|Subject):\s*(.+)', raw)
    if subj_line:
        subject = subj_line.group(1).strip().strip('"')
        body = raw[subj_line.end():].strip().strip('"')
        if subject and body:
            return {"subject": subject, "body": body}

    # Fallback: return raw as body but warn
    print("  [WARN] Could not parse LLM response as JSON — using raw text as body")
    return {"subject": "quick question", "body": raw[:500]}
