import requests
import json
import logging
from typing import Dict, Any
from config import GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScriptGenerator:
    def __init__(self, gemini_key: str = GEMINI_API_KEY, groq_key: str = GROQ_API_KEY, openrouter_key: str = OPENROUTER_API_KEY):
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        self.openrouter_key = openrouter_key

    def generate_shorts_script(self, topic: str, data_summary: str) -> Dict[str, str]:
        """Generates a viral ~45-second (110-130 words) English YouTube Shorts script."""
        prompt = f"""You are an elite financial journalist and YouTube creator for the channel "US Stock Market Daily".
Generate a high-energy, engaging 45-second YouTube Shorts script based on this data:
Topic: {topic}
Data Context: {data_summary}

RULES:
1. Start with an insane HOOK in the first 3 seconds that catches attention immediately.
2. Word count: MUST BE BETWEEN 110 AND 130 WORDS (approx 45 seconds of natural speech).
3. Do NOT use sound effect cues (e.g. [Upbeat music playing] or (Visuals: Chart)). ONLY write the spoken text!
4. End with a crisp Call-To-Action to subscribe to "US Stock Market Daily".
5. Return JSON format with keys: "title", "hook", "full_script", "tags".
"""
        return self._call_llm(prompt, default_title=topic)

    def generate_long_script(self, market_data: Dict[str, Any]) -> Dict[str, str]:
        """Generates a 3-minute (450-550 words) detailed English Daily Market Recap script."""
        prompt = f"""You are the lead anchor of "US Stock Market Daily". Write a comprehensive 3-minute Daily Market Recap script.

Data Provided:
{json.dumps(market_data, indent=2)}

STRUCTURE:
1. HOOK & MARKET SUMMARY (S&P 500, Nasdaq, Market Sentiment / Fear & Greed)
2. TOP GAINERS & LOSERS BREAKDOWN
3. HOT NEWS & INSIDER MOVES
4. WHAT TO WATCH TOMORROW & OUTRO

RULES:
- Word count: 450 to 550 words.
- ONLY output the spoken script text. No stage directions or visual cues.
- Tone: Professional, fast-paced, insightful, Wall-Street level analysis.
- Return JSON with keys: "title", "description", "full_script", "tags".
"""
        return self._call_llm(prompt, default_title="US Stock Market Daily Recap")

    def _call_llm(self, prompt: str, default_title: str) -> Dict[str, str]:
        """Calls OpenRouter, Gemini, or Groq API."""
        # 1. Try OpenRouter API if present
        if self.openrouter_key:
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "google/gemini-2.0-flash-lite-001",
                    "messages": [
                        {"role": "system", "content": "You output strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ]
                }
                res = requests.post(url, headers=headers, json=payload, timeout=20)
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"]
                    # Extract JSON if wrapped in markdown codeblocks
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"OpenRouter API call failed: {e}")

        # 2. Try Gemini API
        if self.gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt + "\nProvide valid JSON output."}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                }
                res = requests.post(url, json=payload, timeout=20)
                if res.status_code == 200:
                    text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")

        # Fallback template if no LLM key provided
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
            "tags": ["stocks", "investing", "nvidia", "tesla", "finance", "wallstreet"]
        }

if __name__ == "__main__":
    sg = ScriptGenerator()
    script = sg.generate_shorts_script("Nvidia Hits New Highs", "Nvidia up 6.8% today driven by AI chip demand.")
    print("Generated Title:", script["title"])
