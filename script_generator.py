import requests
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from config import OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScriptGenerationError(Exception):
    """Raised when no LLM could produce a script. The pipeline must stop —
    publishing a canned template script would be fake content."""


class ProviderAccountError(ScriptGenerationError):
    """Account rejection stops the run; never evade a spending limit."""


# Sentinel: the failure was account-level (bad key, monthly limit, no credits),
# not model-level. Every other model behind the same key fails identically, so
# the whole provider is abandoned at once instead of burning three more calls.
_PROVIDER_DEAD = object()


def _learnings() -> Dict[str, Any]:
    """The weekly learning engine's output (single artifact for all feedback
    loops). Empty dict when missing/stale — every consumer has a default."""
    try:
        from learning_engine import load_learnings
        return load_learnings()
    except Exception as e:
        logger.warning(f"Could not load channel learnings: {e}")
        return {}


def _packaging_patterns_block() -> str:
    """This week's proven packaging patterns from the market-wide outlier scan.
    Structure-only guidance — empty string if no scan has run yet."""
    p = _learnings().get("market_patterns") or {}
    titles = [_pattern_text(t) for t in p.get("title_patterns", [])[:5]]
    hooks = [_pattern_text(h) for h in p.get("hook_patterns", [])[:3]]
    if not (titles or hooks):
        return ""
    lines = ["PACKAGING HYPOTHESES (unproven on our channel; never override editorial rules or copy a real title):"]
    lines += [f"- Title shape: {t}" for t in titles]
    lines += [f"- Hook shape: {h}" for h in hooks]
    return "\n" + "\n".join(lines) + "\n"


def _pattern_text(item: Any) -> str:
    """A learned pattern may be a plain string or a rich dict (pattern,
    evidence, how_to_apply) — render it prompt-ready either way."""
    if isinstance(item, dict):
        text = str(item.get("pattern") or item.get("title") or "").strip()
        how = str(item.get("how_to_apply") or "").strip()
        return f"{text} ({how})" if text and how else (text or str(item))
    return str(item)


def _own_channel_block() -> str:
    """Lessons distilled weekly from OUR OWN uploads' retention/APV data.
    Own data outranks market-wide patterns — say so to the model."""
    p = _learnings().get("own_patterns") or {}
    win = [_pattern_text(w) for w in p.get("winning_patterns", [])[:5]]
    lose = [_pattern_text(l) for l in p.get("losing_patterns", [])[:4]]
    if not (win or lose):
        return ""
    lines = ["OUR CHANNEL OBSERVATIONS (small unequal-age sample; hypotheses only, never override editorial rules):"]
    lines += [f"- Held OUR viewers: {w}" for w in win]
    lines += [f"- Lost OUR viewers (avoid): {l}" for l in lose]
    return "\n" + "\n".join(lines) + "\n"


def _word_range(key: str, default: Tuple[int, int],
                sane: Tuple[int, int]) -> Tuple[int, int]:
    """Auto-calibrated word budget from the measured narration rate, clamped
    to a sanity window so a bad calibration can't produce a 10-word Short."""
    rng = (_learnings().get("narration") or {}).get(key)
    try:
        lo, hi = int(rng[0]), int(rng[1])
        if sane[0] <= lo < hi <= sane[1]:
            return lo, hi
    except (TypeError, ValueError, IndexError):
        pass
    return default


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
        # Last provider-side failure text, surfaced in the abort alert — a bare
        # "all providers failed" told the operator nothing about what to fix.
        self.last_error = ""
        self.account_error = ""
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

        NOTE 2026-08-16: word budgets are now AUTO-CALIBRATED weekly by the
        learning engine from w:/v: machine tags on published videos (measured
        words/sec x the 32-38s target). The 66-78 literal below is only the
        cold-start default until enough tagged uploads exist.
        """
        lo, hi = _word_range("shorts_word_range", default=(66, 78), sane=(45, 110))
        franchise_block = f"\n{franchise_style}\n" if franchise_style else ""
        angle_block = f"Editorial angle (follow it): {angle}\n" if angle else ""
        prompt = f"""You are an elite Wall Street financial analyst and viral YouTube creator for the channel "US Stock Market Daily".
Positioning: data-first, zero hype — real numbers, real reasons, no clickbait fear-mongering.
Generate a 35-SECOND YouTube Shorts script based on this real-time market data:
Topic: {topic}
{angle_block}Market Context: {data_summary}
{franchise_block}
OPENING EXPERIMENT: identify the company or public figure in the FIRST sentence.
Our September 2026 audit found that search is the largest traffic source, with queries
such as company name + "stock". A bare dollar number gives a new viewer no subject.

0-3s: name the company/actor AND the verified event in one short sentence.
3-8s: deliver the most useful fact or explanation immediately. No withheld payoff.
8-30s: explain ONE supported reason and ONE material limitation.
30-35s: finish the explanation cleanly; a natural loop is optional, never padding.

Use plain English. Do not force a contradiction between unrelated events (an insider
trade and an index change are not automatically connected). Do not imply privileged
knowledge, wrongdoing, "sold everything", or a historical record without evidence.
An unknown company needs one brief identifying phrase only if provided in the facts.
Do not mention VIX, Nasdaq, Dow or S&P 500 in this single-company experiment.
Explain why the event matters in plain language, based only on the selected facts.
These rules override franchise guidance and learned packaging patterns below.
If no cause is established, say that the supplied data does not establish a cause.

TITLE: put the identifiable company name or actor near the beginning, with the actual
news and a supported number when useful. A clear factual headline is allowed.
Do not force a question mark, tease a missing company name, or invent tension.
For disclosures, say "disclosed X days later", never "X days late", "overdue" or
"hidden": transaction-to-disclosure lag alone does not establish a missed deadline.
Vary the wording naturally across recent uploads, without sacrificing discoverability.
{_recent_titles_block(recent_titles)}{_own_channel_block()}{_packaging_patterns_block()}
RULES:
1. Word count: MUST BE BETWEEN {lo} AND {hi} WORDS. This is a hard requirement — {hi} words
   is ~38 seconds and 38 seconds is the ceiling. Cut the second-best fact, not the hook.
2. Use at most TWO key numbers in narration. Round sensibly without changing meaning;
   preserve exact figures when a filing range or comparison requires them. Avoid decimal clutter.
   Write them TTS-friendly: "$4.7 million" not "$4.7M", "up 23 percent" or "23%" not "+23%".
   The script is read aloud by a voice engine — abbreviations like "M", "B", "PT", "EPS" get mispronounced; spell them out ("price target", "earnings per share").
2b. NEVER open with "Hey guys", "Welcome back", "In today's video" — cold-open directly on the story.
3. Do NOT use sound effect cues or stage directions (e.g. [Music playing] or (Visual: Chart)). ONLY write spoken text!
4. End on a useful conclusion. A natural loop is optional. NO padded outro or subscribe CTA.
5. Only state facts present in the Market Context. Never invent numbers, names or reasons.
6. Return strictly valid JSON format with keys:
   - "title": Catchy YouTube video title (40-60 chars, keyword first, specific numbers)
   - "hook": the first spoken sentence, naming the company/actor, max 12 words
   - "hero_number": the story's headline figure as it should appear in HUGE type on
     the on-screen card — a number actually spoken in the opening. Written for the EYE,
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
        return self._call_llm(prompt, default_title=topic,
                              min_words=lo, max_words=hi)

    def generate_long_script(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """A 150-210 second, single-story recap experiment.

        September's live audit measured 76 seconds average watch on long
        videos. Use the weekly measured voice pace, with a shorter fallback.
        """
        lo, hi = _word_range("long_word_range", default=(330, 462), sane=(250, 650))
        mid = (lo + hi) // 2
        from data_fetcher import ny_now
        today_str = ny_now().strftime("%B %-d")  # e.g. "August 2"
        prompt = f"""You are the lead financial anchor of "US Stock Market Daily". Write a focused market explanation for a 2.5-3.5 minute video. This is a measured shorter-format experiment.
Positioning: data-first, zero hype — real numbers, real reasons, original analysis (never a news-summary rehash).

Data Provided:
{json.dumps(market_data, indent=2, default=str)}

STRUCTURE (total ~{mid} words; skip sections without substantive source facts):
1. OPEN (~25 words): name the main company/event and immediately state what changed.
2. MAIN STORY (~55% of the remaining words): explain the verified catalyst and its
   investor relevance. Separate reported facts from interpretation. Deliver value early.
3. MARKET CONTEXT (~25%): only index/sector facts that help explain this story.
4. NEXT CHECKPOINT (~20%): a sourced upcoming event and one uncertainty to watch.
Do not fill a daily checklist with unrelated congressional trades or earnings.
{_own_channel_block()}{_packaging_patterns_block()}
RULES:
- Word count: {lo} to {hi} words (2.5-3.5 minutes at the measured pace). This is a HARD requirement.
  Depth comes from picking fewer items and explaining them properly, never from listing more.
- Use only the few numbers needed to explain the event; round sensibly without changing meaning. Every claim must come from the provided data — never invent numbers, names or reasons.
- Do not mention VIX, Nasdaq, Dow or S&P 500 in this single-company experiment.
- Write numbers TTS-friendly: "$4.7 million" not "$4.7M"; spell out abbreviations ("price target", "earnings per share") — the script is read aloud by a voice engine.
- ONLY output spoken script text. No stage directions, section headers, or visual cues in full_script.
- Tone: Professional, fast-paced, insightful Wall-Street level analysis with original interpretation.
- Return strictly valid JSON format with keys:
   - "title": Lead with the main company/event and the verified consequence; optionally end with "| Market Recap {today_str}". Keep under 85 characters. Do not bury the actual story behind a generic date prefix.
   - "description": First line summarizes the selected company event. Include only sources actually present in the supplied facts, and relevant hashtags.
   - "full_script": Spoken text only
   - "ticker": Main ticker discussed
   - "change_pct": Percent change string
   - "tags": Array of tags
   - "thumbnail_hook": 3-5 word thumbnail text (e.g. "CONGRESS IS BUYING THIS")
   - "hero_number": the day's single most striking figure for the on-screen card, written
     for the EYE and under 12 characters ("-23K JOBS", "$28.2M", "+2.4%")
   - "hero_label": 2-4 words naming it ("JULY PAYROLLS", "CEO SOLD")
   - "visual_keywords": Array of 3-5 stock-video search phrases, matching the actual story sections in order. Each becomes a
     background scene that cross-fades in as that section is narrated, so they must be
     VISUALLY distinct from one another — different setting, subject and dominant colour,
     not five phrasings of "stock market chart". Concrete places and objects beat abstract
     concepts: ["wall street trading floor", "semiconductor factory robot arm", "oil refinery
     at night", "electric vehicle assembly line", "us capitol building exterior"]
"""
        return self._call_llm(prompt, default_title="US Stock Market Daily Recap",
                              min_words=lo, max_words=hi)

    SYSTEM_MSG = "You are a professional financial AI writer. Always respond with valid JSON only."

    def _providers(self) -> List[Tuple[str, str]]:
        """(provider, model) attempts in order. The direct Gemini/Groq entries
        exist because every 'fallback' used to route through the single
        OpenRouter account — an account-level failure (the Jul-31 outage was a
        monthly key limit) took down the entire chain at once."""
        attempts: List[Tuple[str, str]] = []
        if self.openrouter_key:
            attempts += [("openrouter", m) for m in self.openrouter_models]
        if self.gemini_key:
            attempts.append(("gemini", "gemini-2.5-flash"))
        if self.groq_key:
            attempts.append(("groq", "llama-3.3-70b-versatile"))
        # A single configured provider means an account-level failure (key
        # limit, expired card) stops the channel outright — that is exactly
        # what happened on Jul-31 and again on Aug-25.
        if len({p for p, _ in attempts}) < 2:
            logger.warning("Only one LLM provider is configured — there is no "
                           "account-level fallback. Set GEMINI_API_KEY and/or "
                           "GROQ_API_KEY (both have free tiers).")
        return attempts

    def _chat(self, provider: str, model: str, prompt: str) -> Optional[str]:
        """One chat completion -> content string. None means 'try the next
        model' (auth/4xx/malformed); transient 429/5xx retry in place first."""
        for attempt in range(3):
            try:
                if provider == "openrouter":
                    res = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.openrouter_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://github.com/zeynelgun-afk/yt-stock-automation",
                            "X-Title": "US Stock Market Daily Engine",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": self.SYSTEM_MSG},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.7,
                        },
                        timeout=90,
                    )
                elif provider == "groq":
                    res = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.groq_key}",
                                 "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": self.SYSTEM_MSG},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.7,
                        },
                        timeout=90,
                    )
                else:  # gemini — direct REST, no SDK dependency
                    res = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": self.gemini_key},
                        json={
                            "contents": [{"parts": [{"text": f"{self.SYSTEM_MSG}\n\n{prompt}"}]}],
                            "generationConfig": {"temperature": 0.7,
                                                 "responseMimeType": "application/json"},
                        },
                        timeout=90,
                    )

                if res.status_code == 429 or res.status_code >= 500:
                    # Transient — a single 429 used to permanently abandon the model
                    wait = 5 * (attempt + 1)
                    logger.warning(f"{provider}/{model} HTTP {res.status_code}, "
                                   f"retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                if res.status_code != 200:
                    detail = ("account rejected; check configured account quota or authorization"
                              if res.status_code in (401, 402, 403) else "request rejected")
                    logger.warning(f"{provider}/{model} returned HTTP {res.status_code}: {detail}")
                    self.last_error = f"{provider}: HTTP {res.status_code} {detail}"
                    # 401 bad key / 402 out of credits / 403 key limit exceeded
                    # are all properties of the KEY, not of this model.
                    if res.status_code in (401, 402, 403):
                        logger.warning(f"{provider} key rejected at account level — "
                                       f"skipping its remaining models.")
                        return _PROVIDER_DEAD
                    return None

                if provider == "gemini":
                    return res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return res.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"{provider}/{model} error: {e}")
                self.last_error = f"{provider}/{model}: {e}"
                return None
        return None

    def _call_llm(self, prompt: str, default_title: str,
                  min_words: int = 0, max_words: int = 0) -> Dict[str, Any]:
        """Generates JSON via the provider chain (OpenRouter models, then
        direct Gemini, then direct Groq).

        min_words/max_words bound the full_script length — a recap that comes
        back at 600 words would produce a half-length video, so an off-target
        script gets corrective retries per model before falling through."""
        if self.account_error:
            raise ProviderAccountError(self.account_error)
        for provider, model_name in self._providers():
            retry_note = ""
            for attempt in range(3):
                logger.info(f"Generating script using {provider}/{model_name}...")
                content = self._chat(provider, model_name, prompt + retry_note)
                if content is _PROVIDER_DEAD:
                    self.account_error = self.last_error or f"{provider}: account unavailable"
                    raise ProviderAccountError(self.account_error)
                if content is None:
                    break
                try:
                    # Clean markdown wrappers if returned
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    # strict=False: models embed literal newlines in JSON strings
                    parsed = json.loads(content, strict=False)
                except Exception as e:
                    logger.warning(f"{provider}/{model_name} returned unparseable JSON: {e}")
                    break
                # Schema guard: a JSON list or string would crash the pipeline
                # later with an uncaught KeyError/AttributeError far from here
                if not isinstance(parsed, dict):
                    logger.warning(f"{provider}/{model_name} returned non-object JSON "
                                   f"({type(parsed).__name__}); trying next model.")
                    break
                parsed.setdefault("title", default_title)
                if min_words:
                    # Validate the publication schema before paying for voice/render.
                    if (not isinstance(parsed.get("full_script"), str)
                            or not isinstance(parsed.get("title"), str)
                            or not parsed["title"].strip()
                            or any(not isinstance(parsed.get(k, []), list)
                                   or any(not isinstance(v, str) for v in parsed.get(k, []))
                                   for k in ("tags", "visual_keywords"))
                            or any(not isinstance(parsed[k], str) for k in
                                   ("description", "ticker", "hero_number", "hero_label", "thumbnail_hook")
                                   if k in parsed)):
                        logger.warning("Invalid publication schema from %s; trying next model", model_name)
                        break

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
                logger.info(f"Successfully generated script via {provider}/{model_name} ({word_count} words)!")
                return parsed

        configured = sorted({p for p, _ in self._providers()})
        raise ScriptGenerationError(
            f"All LLM providers failed to generate a script for '{default_title}'. "
            f"Aborting instead of publishing a canned template. "
            f"Configured providers: {', '.join(configured) or 'NONE — no API key is set'}. "
            f"Last error: {self.last_error or 'n/a'}"
        )

if __name__ == "__main__":
    sg = ScriptGenerator()
    script = sg.generate_shorts_script("Nvidia Hits New Highs", "Nvidia up 6.85% today driven by AI chip demand.")
    print("Generated Title:", script["title"])
    print("Full Script:", script["full_script"])
