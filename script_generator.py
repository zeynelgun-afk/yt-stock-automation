import requests
import json
import logging
from typing import Dict, Any
from config import OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScriptGenerationError(Exception):
    """Raised when no LLM could produce a script. The pipeline must stop —
    publishing a canned template script would be fake content."""


class ScriptGenerator:
    def __init__(self, openrouter_key: str = OPENROUTER_API_KEY, gemini_key: str = GEMINI_API_KEY, groq_key: str = GROQ_API_KEY):
        self.openrouter_key = openrouter_key
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        # Ultra economical & smart Chinese models on OpenRouter (DeepSeek V3 & Qwen 2.5)
        self.openrouter_models = [
            "deepseek/deepseek-chat",       # DeepSeek V3 (Ultra cheap & insanely smart)
            "qwen/qwen-2.5-72b-instruct",   # Alibaba Qwen 2.5 72B
            "google/gemini-2.0-flash-001"
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
"""
        return self._call_llm(prompt, default_title=topic)

    def generate_long_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates an 8+ minute (1100-1300 words) Daily Market Recap script.

        8+ minutes unlocks mid-roll ads — the long recap is the channel's
        revenue engine, the Shorts are the reach funnel."""
        prompt = f"""You are the lead financial anchor of "US Stock Market Daily". Write a comprehensive Daily Market Recap script for an 8-10 minute video.
Positioning: data-first, zero hype — real numbers, real reasons, original analysis (never a news-summary rehash).

Data Provided:
{json.dumps(market_data, indent=2, default=str)}

STRUCTURE (follow in order):
1. COLD-OPEN HOOK: the single most shocking number of the day, then a one-line promise of what's coming.
2. MARKET SUMMARY: S&P 500, Nasdaq, Dow, VIX with actual numbers; sector winners/losers; Fear & Greed context.
3. THE 3 BIG STORIES OF THE DAY: pick the three most consequential items from the data (selected_story first). For each: what happened, the concrete WHY (from the news/facts), and what it means for investors.
4. CONGRESS & INSIDER CORNER: notable congressional trades and insider buys/sells from the data — names, amounts, dates.
5. EARNINGS: today's surprises (estimate vs actual) and what's on deck this week.
6. WHAT TO WATCH TOMORROW: economic events and earnings from the data, each with why it can move the market.
7. OUTRO: one-sentence recap of the day's theme + short subscribe CTA (max 10 words).

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
"""
        return self._call_llm(prompt, default_title="US Stock Market Daily Recap")

    def _call_llm(self, prompt: str, default_title: str) -> Dict[str, Any]:
        """Calls DeepSeek V3 / Qwen 2.5 via OpenRouter API with fallbacks."""
        if self.openrouter_key:
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/zeynelgun-afk/yt-stock-automation",
                "X-Title": "US Stock Market Daily Engine"
            }

            for model_name in self.openrouter_models:
                try:
                    logger.info(f"Generating script using OpenRouter model: {model_name}...")
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": "You are a professional financial AI writer. Always respond with valid JSON only."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=25)
                    if res.status_code == 200:
                        content = res.json()["choices"][0]["message"]["content"]
                        # Clean markdown wrappers if returned
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                        
                        parsed = json.loads(content)
                        logger.info(f"Successfully generated script via {model_name}!")
                        return parsed
                except Exception as e:
                    logger.error(f"OpenRouter model {model_name} error: {e}")

        raise ScriptGenerationError(
            f"All OpenRouter models failed to generate a script for '{default_title}'. "
            "Aborting instead of publishing a canned template."
        )

if __name__ == "__main__":
    sg = ScriptGenerator()
    script = sg.generate_shorts_script("Nvidia Hits New Highs", "Nvidia up 6.85% today driven by AI chip demand.")
    print("Generated Title:", script["title"])
    print("Full Script:", script["full_script"])
