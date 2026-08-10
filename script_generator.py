import requests
import json
import logging
from typing import Any, Dict, List, Optional
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


def _recent_titles_block(titles: Optional[List[str]]) -> str:
    """The channel's own recent titles, so the model can avoid reusing their shape.

    The story selector already fetches these for name-level dedup; reusing the
    list here costs no extra API call and catches the other kind of repetition —
    same skeleton, different ticker."""
    if not titles:
        return ""
    lines = ["\nRECENT TITLES ON THIS CHANNEL (do not reuse their sentence shape):"]
    lines += [f"- {t}" for t in titles[:6]]
    return "\n".join(lines) + "\n"


class ScriptGenerator:
    def __init__(self, openrouter_key: str = OPENROUTER_API_KEY, gemini_key: str = GEMINI_API_KEY, groq_key: str = GROQ_API_KEY):
        self.openrouter_key = openrouter_key
        self.gemini_key = gemini_key
        self.groq_key = groq_key
        # Verified-live OpenRouter slugs (dead slugs 404 and silently ate the
        # fallback chain — check https://openrouter.ai/api/v1/models when editing)
        self.openrouter_models = [
            "anthropic/claude-opus-5",      # strongest storyteller — scripts are cheap, quality compounds
            "anthropic/claude-sonnet-5",    # first fallback, proven on this channel
            "google/gemini-3.6-flash",      # fast + cheap, reliable long output
            "deepseek/deepseek-v4-pro",     # cheap last resort
        ]

    def generate_shorts_script(self, topic: str, data_summary: str,
                               franchise_style: str = "", angle: str = "",
                               recent_titles: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generates a ~35-second (66-78 word) English YouTube Shorts script.

        Length is set by retention data, not by how much there is to say. The
        channel's audience-retention curves flatten at ~22 seconds watched on
        every video; at 70 seconds that reads as 31% average-view-percentage
        and YouTube stops distributing. The same 22 seconds inside a 35-second
        Short reads as ~63% and earns the feed.

        Word budget comes from the production voice's MEASURED rate, taken from
        CI logs against published durations: 130/131/150-word scripts rendered
        as 64-76 second videos, i.e. ~2.05 words/sec (ElevenLabs, incl. pauses).
        66-78 words therefore lands at 32-38 seconds. Re-measure before changing
        this — a generic words-per-minute figure is roughly 40% too fast here.
        """
        franchise_block = f"\n{franchise_style}\n" if franchise_style else ""
        angle_block = f"Editorial angle (follow it): {angle}\n" if angle else ""
        prompt = f"""You are an elite Wall Street financial analyst and viral YouTube creator for the channel "US Stock Market Daily".
Positioning: data-first, zero hype — real numbers, real reasons, no clickbait fear-mongering.
Generate a 35-SECOND YouTube Shorts script based on this real-time market data:
Topic: {topic}
{angle_block}Market Context: {data_summary}
{franchise_block}
THE FIRST TEN SECONDS ARE THE WHOLE JOB. This channel's retention data shows 60% of
viewers leave between second 3 and second 14 — always at the point where the hook ends
and background explanation begins. There is no "setup" in a 35-second Short. Build the
opening as three hard beats with NO connective tissue between them:

  BEAT 1 (0-3s, ~6 words): the single hardest number, standing alone as its own sentence.
      "Twenty-eight point two million dollars."
  BEAT 2 (3-6s, ~6 words): the contradiction that makes it strange.
      "The CEO sold it all Tuesday."
  BEAT 3 (6-10s, ~7 words): what is at stake for the viewer, as an unresolved question.
      "Two weeks before earnings. Here's what he knew."

BANNED in the first ten seconds: company background, sector context, "let's take a look",
any sentence whose job is to prepare a later sentence. If a line could be deleted without
losing a fact, delete it.

BODY (10-30s, ~45 words): ONE concrete WHY, drawn only from the data. One idea, not three.
CLOSE (30-35s, ~10 words): land on the exact number from BEAT 1 so the loop is seamless.

TENSION REQUIREMENT (non-negotiable): the title must pose a tension, contradiction or
open question — never a plain restatement of the news. "X happened" is a headline, not a
hook; "X happened, and the timing is the story" is a hook.

TITLE SHAPE ROTATION (this channel's failure mode — read carefully): our last four videos
were all titled "TICKER Did X — A or B?" and all four underperformed. A viewer who sees
the same sentence skeleton twice stops seeing the channel. Pick a DIFFERENT shape from
every recent title below, choosing from:
  - Hard number first:      "$28.2 Million Sold Two Weeks Before Earnings"
  - Flat declarative:       "The CEO Sold Everything. Nobody Noticed."
  - Named-actor action:     "Pelosi's Fund Bought This Before the Vote"
  - Original-research:      "We Read 400 Filings. One Name Kept Appearing."
  - Consequence/stakes:     "This Insider Sale Broke a Three-Year Pattern"
Question-mark titles are allowed at most once every four videos — prefer a declarative
that states something and makes the viewer need the proof.
{_recent_titles_block(recent_titles)}{_packaging_patterns_block()}
RULES:
1. Word count: MUST BE BETWEEN 66 AND 78 WORDS. This is a hard requirement — 78 words is
   38 seconds and 38 seconds is the ceiling. Cut the second-best fact, not the hook.
2. Use specific, unrounded numbers from the data — never vague words like "millions" or "a lot".
   Write them TTS-friendly: "$4.7 million" not "$4.7M", "up 23 percent" or "23%" not "+23%".
   The script is read aloud by a voice engine — abbreviations like "M", "B", "PT", "EPS" get mispronounced; spell them out ("price target", "earnings per share").
2b. NEVER open with "Hey guys", "Welcome back", "In today's video" — cold-open directly on the story.
3. Do NOT use sound effect cues or stage directions (e.g. [Music playing] or (Visual: Chart)). ONLY write spoken text!
4. LOOP DESIGN: the final sentence must connect back to the opening hook so the video rewatches seamlessly. NO outro and NO subscribe CTA — at 35 seconds there is no room for one, and it costs the loop.
5. Only state facts present in the Market Context. Never invent numbers, names or reasons.
6. Return strictly valid JSON format with keys:
   - "title": Catchy YouTube video title (40-60 chars, keyword first, specific numbers)
   - "hook": BEAT 1 only — the standalone opening line, max 8 words
   - "hero_number": the story's headline figure as it should appear in HUGE type on
     the on-screen card — the same number BEAT 1 says out loud. Written for the EYE,
     not the voice, so abbreviate hard and keep it under 12 characters: "$28.2M",
     "+290%", "6,297%", "$1.56M". Never the daily change % unless the move itself
     IS the story.
   - "hero_label": 2-4 words naming that figure, e.g. "CEO SOLD", "IN ONE DAY",
     "MENTIONS SURGE", "INSIDER BOUGHT"
   - "full_script": Spoken text only
   - "ticker": Primary stock symbol (e.g. "NVDA")
   - "change_pct": Numeric percent change string (e.g. "+6.85")
   - "tags": Array of 6 relevant tags
   - "visual_keywords": Array of 3-4 stock video search phrases (e.g. ["stock market trading", "nvidia microchip", "wall street traders"])
"""
        return self._call_llm(prompt, default_title=topic, min_words=58, max_words=88)

    def generate_long_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates a 5-6 minute (660-780 word) Daily Market Recap script.

        Word budgets here are set from this pipeline's measured narration rate
        of ~2.18 words/sec, measured from CI: a 1465-word recap rendered as an
        11.2-minute video. A generic words-per-minute figure would have said
        ~2.5 and is why the old 1200-word budget shipped as 11 minutes.

        The recap used to target 8+ minutes to clear the mid-roll ad threshold,
        but the channel is not monetized yet and the 11-minute cuts averaged
        16% view percentage on 27 views — an ad slot nobody reaches is worth
        nothing. Reach first: a 5-6 minute recap that holds viewers earns the
        distribution that makes the 8-minute version worth restoring later.
        """
        from datetime import datetime
        today_str = datetime.now().strftime("%B %-d")  # e.g. "August 2"
        prompt = f"""You are the lead financial anchor of "US Stock Market Daily". Write a tight Daily Market Recap script for a 5-6 minute video.
Positioning: data-first, zero hype — real numbers, real reasons, original analysis (never a news-summary rehash).

Data Provided:
{json.dumps(market_data, indent=2, default=str)}

STRUCTURE (follow in order — the per-section word budgets are mandatory, they add up to ~720 words):
1. COLD-OPEN HOOK (~50 words): the single most shocking number of the day as a standalone
   opening line, then the three things this video will resolve. No throat-clearing, no
   "welcome back", no restating the date before the number.
2. MARKET SUMMARY (~105 words): S&P 500, Nasdaq, Dow, VIX with actual numbers; sector winners/losers; Fear & Greed context.
3. THE 3 BIG STORIES OF THE DAY (~315 words, ~105 each): pick the three most consequential items from the data (selected_story first). For each: what happened, the concrete WHY (from the news/facts), and what it means for investors. Open each story on its own hard number — these are the re-hook points where viewers decide to stay.
4. CONGRESS & INSIDER CORNER (~105 words): notable congressional trades and insider buys/sells from the data — names, amounts, dates.
5. EARNINGS (~80 words): today's surprises (estimate vs actual) and what's on deck this week.
6. WHAT TO WATCH TOMORROW (~45 words): the two or three events from the data most likely to move the market, each with why.
7. OUTRO (~20 words): one line recapping the day's theme + a five-word subscribe CTA.
{_packaging_patterns_block()}
RULES:
- Word count: 660 to 780 words (5-6 minutes of narration at this channel's pace). This is a HARD requirement.
  Depth comes from picking fewer items and explaining them properly, never from listing more.
- Use specific, unrounded numbers from the data. Every claim must come from the provided data — never invent numbers, names or reasons.
- Write numbers TTS-friendly: "$4.7 million" not "$4.7M"; spell out abbreviations ("price target", "earnings per share") — the script is read aloud by a voice engine.
- ONLY output spoken script text. No stage directions, section headers, or visual cues in full_script.
- Tone: Professional, fast-paced, insightful Wall-Street level analysis with original interpretation.
- Return strictly valid JSON format with keys:
   - "title": MUST follow this exact search-optimized format: "Stock Market Today: {today_str} — <the day's most shocking specific event with a number>". Search traffic is this format's entire purpose — people search "stock market today", never "Dow jumps as CEO sells".
   - "description": First line MUST be search bait: "Stock market recap for {today_str}: <one-sentence summary with the key index moves>." Then the comprehensive description with hashtags (#stockmarket #stockmarkettoday #marketrecap among them) and a data-source transparency line ("Data: Financial Modeling Prep, CNN Fear & Greed")
   - "full_script": Spoken text only
   - "ticker": Main ticker discussed
   - "change_pct": Percent change string
   - "tags": Array of tags
   - "thumbnail_hook": 3-5 word thumbnail text (e.g. "CONGRESS IS BUYING THIS")
   - "hero_number": the day's single most striking figure for the on-screen card, written
     for the EYE and under 12 characters ("-23K JOBS", "$28.2M", "+2.4%")
   - "hero_label": 2-4 words naming it ("JULY PAYROLLS", "CEO SOLD")
   - "visual_keywords": Array of 3-4 stock video search phrases (e.g. ["wall street trading floor", "stock market rally", "financial news"])
"""
        return self._call_llm(prompt, default_title="US Stock Market Daily Recap",
                              min_words=600, max_words=850)

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
                                # Same trick in reverse: models compress a draft
                                # they can see far more reliably than they hit a
                                # ceiling from scratch. Overshooting is the normal
                                # failure mode on the 35-second Shorts budget.
                                retry_note = (
                                    f"\n\nIMPORTANT: Your previous draft (below) was {word_count} words — too long. "
                                    f"The full_script MUST be {min_words}-{max_words} words. Rewrite it by CUTTING, "
                                    f"not by rephrasing: keep the opening beats and the single strongest fact intact, "
                                    f"and delete whole supporting sentences until it fits. Never shorten the opening "
                                    f"to make room for the body. Return the same JSON structure.\n\n"
                                    f"PREVIOUS DRAFT:\n{parsed.get('full_script', '')}")
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
