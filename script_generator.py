import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import llm_transport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScriptGenerationError(Exception):
    """Raised when no LLM could produce a script. The pipeline must stop —
    publishing a canned template script would be fake content."""


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
    def __init__(self, openrouter_key: str = "", gemini_key: str = "", groq_key: str = ""):
        # Legacy positional/keyword arguments accepted but never stored or used.
        self.last_error = ""

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
VOICE: informative and lightly funny. After the opening fact, include at most one
brief original dry joke or everyday analogy when it fits naturally. Joke about
paperwork, market mechanics or everyday frustrations; never invent financial facts,
accuse a person, mock losses or weaken an important caveat. No joke is better than
a forced one. Keep the same word budget and return to the explanation immediately.
If no cause is established, say that the supplied data does not establish a cause.

TITLE: put the identifiable company name or actor near the beginning, followed by
one concrete verified event. Use at most ONE supported numeric quantity in the title.
Do not append a generic recap/date suffix. Keep caveats in the narration while
ensuring the title remains accurate; never remove a qualifier needed for accuracy. A clear factual headline is allowed.
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
- Tone: clear, lively and informative, with up to two brief original dry jokes or
  everyday analogies after factual payoffs. Humor should explain the mechanics,
  never invent claims, accuse people or mock financial losses. Avoid forced jokes.
  Keep the existing word budget and make factual limitations clear.
- Return strictly valid JSON format with keys:
   - "title": Lead with the main company/event and the verified consequence; use at most one supported numeric quantity and omit generic recap/date suffixes. Keep under 85 characters. Do not bury the actual story behind a generic date prefix.
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
        return [(llm_transport.PROVIDER, llm_transport.MODEL)]

    def _chat(self, provider: str, model: str, prompt: str) -> Optional[str]:
        # Compatibility routing arguments cannot override the fixed transport.
        try:
            return llm_transport.complete([
                {"role": "system", "content": self.SYSTEM_MSG},
                {"role": "user", "content": prompt},
            ])
        except llm_transport.InferenceError:
            self.last_error = "Local Hermes unavailable or invalid structured output"
            logger.warning(self.last_error)
            return None

    def _call_llm(self, prompt: str, default_title: str,
                  min_words: int = 0, max_words: int = 0) -> Dict[str, Any]:
        """Bounded correction requests on the same subscription model.

        Preserve script schema and length validation. Inference failures abort
        immediately; at most three fresh contexts correct a word-count miss.
        """
        for provider, model_name in self._providers():
            retry_note = ""
            for attempt in range(3):
                logger.info(f"Generating script using {provider}/{model_name}...")
                content = self._chat(provider, model_name, prompt + retry_note)
                if content is None:
                    break
                try:
                    parsed = llm_transport.strict_json(content)
                except Exception as e:
                    logger.warning(f"{provider}/{model_name} returned unparseable JSON: {e}")
                    break
                # Schema guard: a JSON list or string would crash the pipeline
                # later with an uncaught KeyError/AttributeError far from here
                if not isinstance(parsed, dict):
                    logger.warning(f"{provider}/{model_name} returned non-object JSON "
                                   f"({type(parsed).__name__}); aborting.")
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
                        logger.warning("Invalid publication schema from %s; aborting", model_name)
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

        raise ScriptGenerationError(
            "Local Hermes failed to generate validated JSON; publishing aborted. "
            + (self.last_error or "Invalid schema or word budget")
        )

if __name__ == "__main__":
    sg = ScriptGenerator()
    script = sg.generate_shorts_script("Nvidia Hits New Highs", "Nvidia up 6.85% today driven by AI chip demand.")
    print("Generated Title:", script["title"])
    print("Full Script:", script["full_script"])
