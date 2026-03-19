"""
LLM backend — Gemini → Groq → OpenRouter → Ollama fallback chain.
Used by drafter.py for all AI calls.
"""
import os


def call_llm(prompt: str, temperature: float = 0.7) -> str:
    """
    Call LLM with automatic fallback chain.

    Order: Gemini → Groq → OpenRouter → Ollama (local)

    Returns:
        Raw text response

    Raises:
        RuntimeError if all backends exhausted
    """
    # Gemini (primary — 1500 free req/day)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            return response.text.strip()
        except Exception as e:
            if "RESOURCE_EXHAUSTED" not in str(e) and "429" not in str(e):
                raise

    # Groq (fast, generous free tier)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1024,
                        temperature=temperature,
                    )
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    if "429" not in str(e) and "rate" not in str(e).lower():
                        raise
        except Exception:
            pass

    # OpenRouter (free models available)
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if or_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
            for model in ["meta-llama/llama-3.3-70b-instruct:free", "mistralai/mistral-7b-instruct:free"]:
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1024,
                        temperature=temperature,
                    )
                    return resp.choices[0].message.content.strip()
                except Exception:
                    continue
        except Exception:
            pass

    # Ollama (local, no rate limits)
    try:
        import httpx
        httpx.get("http://localhost:11434", timeout=2)
        from openai import OpenAI
        client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
        resp = client.chat.completions.create(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        pass

    raise RuntimeError(
        "All LLM backends exhausted. "
        "Set GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY in .env — "
        "or start Ollama locally."
    )
