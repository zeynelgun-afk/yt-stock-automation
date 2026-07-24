import requests
import json
import logging
from typing import Dict, Any
from config import OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, PATTERNS_FILE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScriptGenerationError(Exception):
    """Raised when no LLM could produce a script. The pipeline must stop —
    publishing a canned template script would be fake content."""


def _packaging_patterns_block() -> str:
    """This week's proven packaging patterns from the outlier scanner (Faz 2.5).
    Structure-only guidance — empty string if no scan has run yet."""
    try:
        if PATTERNS_FILE.exists():
            p = json.loads(PATTERNS_FILE.read_text())
            titles = p.get("title_patterns", [])[:5]
            hooks = p.get("hook_patterns", [])[:3]
            if titles or hooks:
                lines = ["PROVEN PACKAGING THIS WEEK (structural patterns only — NEVER copy a real title):"]
                lines += [f"- Title shape: {t}" for t in titles]
                lines += [f"- Hook shape: {h}" for h in hooks]
                return "\n" + "\n".join(lines) + "\n"
    except Exception as e:
        logger.warning(f"Could not load packaging patterns: {e}")
    return ""


class ScriptGenerator:
    def __init__(self, openrouter_key: str = OPENROUTER_API_KEY, gemini_key: str = GEMINI_API_KEY, groq_key: str = GROQ_API_KEY):
        self.openrouter_key = openrouter_key
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        # Verified-live OpenRouter slugs (dead slugs 404 and silently ate the
        # fallback chain — check https://openrouter.ai/api/v1/models when editing)
        self.openrouter_models = [
            "anthropic/claude-sonnet-5",    # strongest long-form storyteller
            "google/gemini-3.5-flash",      # fast + cheap, reliable long output
            "openai/gpt-4o",                # proven on this account
            "deepseek/deepseek-chat-v3.1",  # cheap last resort
        ]

    def generate_shorts_script(self, topic: str, data_summary: str,
                               franchise_style: str = "", angle: str = "") -> Dict[str, Any]:
        """Generates a viral ~45-second (110-130 words) English YouTube Shorts script using DeepSeek/Qwen via OpenRouter."""
        franchise_block = f"\n{franchise_style}\n" if franchise_style else ""
        angle_block = f"Editorial angle (follow it): {angle}\n" if angle else ""
        prompt = f"""You are an elite Wall Street financial analyst and viral YouTube creator for the channel "US Stock Market Daily".
Positioning: data-first, zero hype — real numbers, real reasons, no clickbait fear-mongering.
Generate an engaging 45-second YouTube Shorts script based on this real-time market data:
Topic: {topic}
{angle_block}Market Context: {data_summary}
{franchise_block}
HOOK — the first sentence decides whether the viewer swipes away. Use one of these proven patterns:
- Bold claim: "NVIDIA just did something no company has ever done."
- Curiosity gap: "This chart predicted the last 3 crashes — it just flashed again."
- Direct question: "Why is a US senator suddenly buying this stock?"
- Specific shock number up front: "$4.7 million. That's what one insider just bet."
{_packaging_patterns_block()}
RULES:
1. Word count: MUST BE BETWEEN 110 AND 130 WORDS (approx 45 seconds of natural speech).
2. Use specific, unrounded numbers from the data ("$4.7M", "23%") — never vague words like "millions" or "a lot".
3. Do NOT use sound effect cues or stage directions (e.g. [Music playing] or (Visual: Chart)). ONLY write spoken text!
4. LOOP DESIGN: the final sentence must connect back to the opening hook so the video rewatches seamlessly. NO long outro; at most 5 words of subscribe CTA woven in ("more daily — subscribe."), never a full sentence of it.
5. Only state facts present in the Market Context. Never invent numbers, names or reasons.
6. Return strictly valid JSON format with keys:
   - "title": Catchy YouTube video title (40-60 chars, keyword first, specific numbers)
   - "hook": First 3-second hook
   - "full_script": Spoken text only
   - "ticker": Primary stock symbol (e.g. "NVDA")
   - "change_pct": Numeric percent change string (e.g. "+6.85")
   - "tags": Array of 6 relevant tags
   - "visual_keywords": Array of 3-4 stock video search phrases (e.g. ["stock market trading", "nvidia microchip", "wall street traders"])
"""
        return self._call_llm(prompt, default_title=topic, min_words=100, max_words=170)

    def generate_long_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates an 8+ minute (1100-1300 words) Daily Market Recap script.

        8+ minutes unlocks mid-roll ads — the long recap is the channel's
        revenue engine, the Shorts are the reach funnel."""
        prompt = f"""You are the lead financial anchor of "US Stock Market Daily". Write a comprehensive Daily Market Recap script for an 8-10 minute video.
Positioning: data-first, zero hype — real numbers, real reasons, original analysis (never a news-summary rehash).

Data Provided:
{json.dumps(market_data, indent=2, default=str)}

STRUCTURE (follow in order — the per-section word budgets are mandatory, they add up to ~1200 words):
1. COLD-OPEN HOOK (~60 words): the single most shocking number of the day, then a one-line promise of what's coming.
2. MARKET SUMMARY (~180 words): S&P 500, Nasdaq, Dow, VIX with actual numbers; sector winners/losers; Fear & Greed context.
3. THE 3 BIG STORIES OF THE DAY (~450 words, ~150 each): pick the three most consequential items from the data (selected_story first). For each: what happened, the concrete WHY (from the news/facts), and what it means for investors.
4. CONGRESS & INSIDER CORNER (~180 words): notable congressional trades and insider buys/sells from the data — names, amounts, dates.
5. EARNINGS (~150 words): today's surprises (estimate vs actual) and what's on deck this week.
6. WHAT TO WATCH TOMORROW (~150 words): economic events and earnings from the data, each with why it can move the market.
7. OUTRO (~30 words): one-sentence recap of the day's theme + short subscribe CTA (max 10 words).
{_packaging_patterns_block()}
RULES:
- Word count: 1100 to 1300 words (8+ minutes of natural speech). This is a HARD requirement.
- Use specific, unrounded numbers from the data. Every claim must come from the provided data — never invent numbers, names or reasons.
- ONLY output spoken script text. No stage directions, section headers, or visual cues in full_script.
- Tone: Professional, fast-paced, insightful Wall-Street level analysis with original interpretation.
- Return strictly valid JSON format with keys:
   - "title": Video title (40-60 chars, keyword first, specific numbers)
   - "description": Comprehensive YouTube description with hashtags and a data-source transparency line ("Data: Financial Modeling Prep, CNN Fear & Greed")
   - "full_script": Spoken text only
   - "ticker": Main ticker discussed
   - "change_pct": Percent change string
   - "tags": Array of tags
   - "thumbnail_hook": 3-5 word thumbnail text (e.g. "CONGRESS IS BUYING THIS")
   - "visual_keywords": Array of 3-4 stock video search phrases (e.g. ["wall street trading floor", "stock market rally", "financial news"])
"""
        return self._call_llm(prompt, default_title="US Stock Market Daily Recap",
                              min_words=1000, max_words=1600)

    def _call_llm(self, prompt: str, default_title: str,
                  min_words: int = 0, max_words: int = 0) -> Dict[str, Any]:
        """Calls DeepSeek V3 / Qwen 2.5 via OpenRouter API with fallbacks.

        min_words/max_words bound the full_script length — a recap that comes
        back at 600 words would produce a half-length video, so an off-target
        script gets one corrective retry per model before falling through."""
        if self.openrouter_key:
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/zeynelgun-afk/yt-stock-automation",
                "X-Title": "US Stock Market Daily Engine"
            }

            for model_name in self.openrouter_models:
                retry_note = ""
                for attempt in range(3):
                    try:
                        logger.info(f"Generating script using OpenRouter model: {model_name}...")
                        url = "https://openrouter.ai/api/v1/chat/completions"
                        payload = {
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": "You are a professional financial AI writer. Always respond with valid JSON only."},
                                {"role": "user", "content": prompt + retry_note}
                            ],
                            "temperature": 0.7
                        }
                        res = requests.post(url, headers=headers, json=payload, timeout=60)
                        if res.status_code != 200:
                            logger.warning(f"{model_name} returned HTTP {res.status_code}: {res.text[:200]}")
                            break
                        content = res.json()["choices"][0]["message"]["content"]
                        # Clean markdown wrappers if returned
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()

                        # strict=False: models embed literal newlines in JSON strings
                        parsed = json.loads(content, strict=False)
                        word_count = len(str(parsed.get("full_script", "")).split())
                        if min_words and not min_words <= word_count <= (max_words or 10 ** 6):
                            logger.warning(
                                f"{model_name} script is {word_count} words "
                                f"(need {min_words}-{max_words}), retrying...")
                            if word_count < min_words:
                                # Models expand an existing draft far more reliably
                                # than they hit a word count from scratch
                                retry_note = (
                                    f"\n\nIMPORTANT: Your previous draft (below) was only {word_count} words — "
                                    f"the full_script MUST be {min_words}-{max_words} words. Rewrite it, keeping "
                                    f"every fact, but EXPAND each section to its word budget with deeper analysis "
                                    f"of the same data. Return the same JSON structure.\n\n"
                                    f"PREVIOUS DRAFT:\n{parsed.get('full_script', '')}")
                            else:
                                retry_note = (
                                    f"\n\nIMPORTANT: Your previous attempt was {word_count} words — too long. "
                                    f"The full_script MUST be between {min_words} and {max_words} words.")
                            continue
                        logger.info(f"Successfully generated script via {model_name} ({word_count} words)!")
                        return parsed
                    except Exception as e:
                        logger.error(f"OpenRouter model {model_name} error: {e}")
                        break

        raise ScriptGenerationError(
            f"All OpenRouter models failed to generate a script for '{default_title}'. "
            "Aborting instead of publishing a canned template."
        )

if __name__ == "__main__":
    sg = ScriptGenerator()
    script = sg.generate_shorts_script("Nvidia Hits New Highs", "Nvidia up 6.85% today driven by AI chip demand.")
    print("Generated Title:", script["title"])
    print("Full Script:", script["full_script"])
