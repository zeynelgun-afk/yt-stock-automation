import requests
import json
import logging
from typing import Dict, Any
from config import OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    def generate_shorts_script(self, topic: str, data_summary: str) -> Dict[str, Any]:
        """Generates a viral ~45-second (110-130 words) English YouTube Shorts script using DeepSeek/Qwen via OpenRouter."""
        prompt = f"""You are an elite Wall Street financial analyst and viral YouTube creator for the channel "US Stock Market Daily".
Generate a high-energy, engaging 45-second YouTube Shorts script based on this real-time market data:
Topic: {topic}
Market Context: {data_summary}

RULES:
1. Start with an insane viral HOOK in the first 3 seconds that catches investor attention immediately.
2. Word count: MUST BE BETWEEN 110 AND 130 WORDS (approx 45 seconds of natural speech).
3. Do NOT use sound effect cues or stage directions (e.g. [Music playing] or (Visual: Chart)). ONLY write spoken text!
4. End with a crisp Call-To-Action to subscribe to "US Stock Market Daily".
5. Return strictly valid JSON format with keys:
   - "title": Catchy YouTube video title (max 70 chars)
   - "hook": First 3-second hook
   - "full_script": Spoken text only
   - "ticker": Primary stock symbol (e.g. "NVDA")
   - "change_pct": Numeric percent change string (e.g. "+6.85")
   - "tags": Array of 6 relevant tags
"""
        return self._call_llm(prompt, default_title=topic)

    def generate_long_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates a 3-minute (450-550 words) detailed English Daily Market Recap script."""
        prompt = f"""You are the lead financial anchor of "US Stock Market Daily". Write a comprehensive 3-minute Daily Market Recap script.

Data Provided:
{json.dumps(market_data, indent=2)}

STRUCTURE:
1. HOOK & MARKET SUMMARY (S&P 500, Nasdaq, Market Sentiment / Fear & Greed)
2. TOP GAINERS & LOSERS BREAKDOWN
3. HOT NEWS & INSIDER MOVES
4. WHAT TO WATCH TOMORROW & OUTRO

RULES:
- Word count: 450 to 550 words.
- ONLY output spoken script text. No stage directions or visual cues.
- Tone: Professional, fast-paced, insightful Wall-Street level analysis.
- Return strictly valid JSON format with keys:
   - "title": Video title
   - "description": Comprehensive YouTube description with hashtags
   - "full_script": Spoken text only
   - "ticker": Main ticker discussed
   - "change_pct": Percent change string
   - "tags": Array of tags
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

        # Fallback template if APIs are unavailable
        logger.warning("Using fallback script generator template.")
        return {
            "title": f"US Stock Market Alert: {default_title}",
            "description": "Daily US Stock Market updates, top gainers, and Wall Street analysis.",
            "hook": "Wall Street just delivered a massive shock to investors today!",
            "full_script": (
                "Wall Street just delivered a massive shock to investors today! "
                "Tech stocks like Nvidia and Tesla saw huge volume spikes, while market sentiment shifted rapidly. "
                "The Fear and Greed Index is currently signaling high activity as traders digest the latest economic data. "
                "Are you holding these top movers or taking profits before tomorrow's opening bell? "
                "Subscribe to US Stock Market Daily for real-time market updates every single day!"
            ),
            "ticker": "NVDA",
            "change_pct": "+6.85",
            "tags": ["stocks", "investing", "nvidia", "tesla", "finance", "wallstreet"]
        }

if __name__ == "__main__":
    sg = ScriptGenerator()
    script = sg.generate_shorts_script("Nvidia Hits New Highs", "Nvidia up 6.85% today driven by AI chip demand.")
    print("Generated Title:", script["title"])
    print("Full Script:", script["full_script"])
