"""Deterministic eligibility for the September ten-Shorts experiment."""
import hashlib
import json
import re
from datetime import date, datetime
from urllib.parse import urlsplit

from narrative_scenes import tokens

EXPERIMENT_ID = 'growth-20261003'


def source_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def recent(value, today, days):
    day = source_date(value)
    return day is not None and 0 <= (today - day).days <= days


def linked_news(item, today):
    url = urlsplit(str(item.get('url') or ''))
    return bool(item.get('title') and url.scheme in ('https', 'http') and url.netloc
                and recent(item.get('publishedDate'), today, 3))


def qualify(candidate, *, today=None, minimum_score=55):
    """Return a rejection reason, or attach event identity and admit the candidate.

    A recent article is evidence of a reported event, not proof it caused a move.
    Editorial relevance is an explanation target, never new financial evidence.
    """
    today = today or datetime.now().date()
    facts = candidate.get('facts') or {}
    kind, ticker = candidate['franchise'], candidate.get('ticker', '')
    if candidate['score'] < minimum_score:
        return 'base score below editorial minimum'
    if not ticker or ticker.startswith('^'):
        return 'no single company event'
    if kind == 'congress_trade':
        if not (facts.get('politician') and facts.get('type') and
                recent(facts.get('disclosureDate'), today, 7) and
                source_date(facts.get('transactionDate')) and
                source_date(facts['transactionDate']) <= source_date(facts['disclosureDate'])):
            return 'missing or stale congressional disclosure'
        identity = [kind, ticker, facts['politician'], facts['type'], facts['transactionDate']]
        relevance = 'Explain the disclosed transaction and its reporting lag; it is not a buy or sell recommendation.'
    elif kind == 'insider_watch':
        if not (facts.get('insider') and facts.get('type') and recent(facts.get('transactionDate'), today, 7)):
            return 'missing or stale insider transaction'
        identity = [kind, ticker, facts['insider'], facts['type'], facts['transactionDate']]
        relevance = 'Explain who traded, their actual role and transaction date; a filing does not prove motive.'
    elif kind == 'earnings_shock':
        if not recent(facts.get('date'), today, 1):
            return 'missing or stale earnings date'
        identity = [kind, ticker, facts['date']]
        relevance = 'Explain reported earnings versus estimates and distinguish earnings from the share-price reaction.'
    elif kind == 'analyst_shock':
        if not (facts.get('headline') and facts.get('analyst') and recent(facts.get('publishedDate'), today, 3)):
            return 'missing or stale analyst news'
        identity = [kind, ticker, facts['analyst'], str(facts['publishedDate'])[:10], facts.get('priceTarget')]
        relevance = 'Explain the published analyst view; a target-price gap is not a forecast return or the size of a revision.'
    elif kind == 'market_close':
        news = [item for item in facts.get('news', []) if linked_news(item, today)]
        if not news:
            return 'price move without recent source-linked company news'
        facts['news'] = news
        # Stable if a provider reorders news or adds more recent coverage.
        candidate['event_ids'] = [_fingerprint(['company_news', ticker, item['url'].split('?')[0]]) for item in news]
        identity = None
        relevance = 'Explain the recent reported company event; do not assert it caused the price move unless the source establishes that.'
    else:
        return 'mention counts or generic market readings alone are not an eligible event'
    if identity:
        candidate['event_ids'] = [_fingerprint(identity)]
    candidate['editorial_relevance'] = relevance
    return ''


def _fingerprint(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=True).lower().encode()).hexdigest()[:24]


def publication_tags(story, is_shorts):
    tags = [f"ev:{event}" for event in story.get('event_ids', [])]
    if story.get('ticker'):
        tags.append(f"sym:{story['ticker']}")
    if is_shorts:
        tags.append(f'exp:{EXPERIMENT_ID}')
    return tags


def repeated_event(candidate, upload):
    # Multiple ev tags are stored separately by the history reader.
    return bool(set(candidate.get('event_ids', [])) & set(upload.get('event_ids', [])))


def _excerpt_error(script, field, max_words, label):
    """Engagement fields are quotable in isolation, so they are held to the same
    rule as scene emphasis: an exact consecutive run of the spoken script. A line
    that travels on its own must not be able to carry a claim the video never made.
    """
    value = script.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        return ''  # optional field; absence is not a distortion
    if not isinstance(value, str):
        return f'{label} must be text'
    if len(value.split()) > max_words:
        return f'{label} exceeds {max_words} words'
    phrase, spoken = tokens(value), tokens(script.get('full_script', ''))
    if not phrase:
        return f'{label} must contain spoken words'
    if not any(spoken[i:i + len(phrase)] == phrase
               for i in range(len(spoken) - len(phrase) + 1)):
        return f'{label} must be an exact consecutive excerpt of the spoken script'
    return ''


def _discussion_question_error(script):
    """An open question is the comment lever, but it must not become a request for
    trading advice or a prediction the channel would be seen to act on."""
    question = script.get('discussion_question')
    if question is None or (isinstance(question, str) and not question.strip()):
        return ''
    if not isinstance(question, str):
        return 'discussion_question must be text'
    if not question.strip().endswith('?'):
        return 'discussion_question must be a question'
    if len(question.split()) > 30:
        return 'discussion_question exceeds 30 words'
    if re.search(r'\b(?:should (?:i|you|we) (?:buy|sell|hold)|buy or sell|price target for|'
                 r'where (?:will|is) .*? (?:headed|going)|what should i do with)\b', question, re.I):
        return 'discussion_question solicits trading advice or a price prediction'
    # Every figure it quotes has to exist in the spoken script; a question is not
    # a place to introduce a number the video never supported.
    spoken = set(tokens(script.get('full_script', '')))
    for figure in re.findall(r'\d[\d,]*(?:\.\d+)?', question):
        if figure.lower() not in spoken and figure.replace(',', '') not in {t.replace(',', '') for t in spoken}:
            return 'discussion_question introduces a figure absent from the script'
    return ''


def validate_editorial_script(script, story):
    """Catch concrete known distortions before voice/render; not a full fact check.

    Tone rules (suspense, open loops, a stated disagreement, addressing the
    viewer's own situation) are deliberately NOT enforced here — those are
    editorial choices. What stays enforced is the narrow set that protects
    against false statements about real named people, implied returns, and
    claims the supplied facts do not support.
    """
    headline = f"{script.get('title', '')} {script.get('thumbnail_hook', '')}"
    text = f"{headline} {script.get('full_script', '')}"
    errors = []
    if story.get('ticker') and not story['ticker'].startswith('^') and re.search(
            r'\b(?:VIX|Nasdaq|Dow|S&P\s*500)\b', text, re.I):
        errors.append('unrelated index comparison in single-company experiment')
    # Narrowed from the former blanket ban: suspense and open questions are now
    # allowed, but insinuating that a named real person traded on undisclosed
    # knowledge, or implying a guaranteed outcome, is a factual/legal claim.
    if re.search(r'\b(?:secret knowledge|inside information|guaranteed returns?|'
                 r"knows? something (?:you|we) don'?t|can'?t lose|risk[- ]free)\b", text, re.I):
        errors.append('unsupported privileged-knowledge or guaranteed-return implication')
    for field, limit, label in (('memorable_line', 12, 'memorable_line'),
                                ('next_checkpoint', 15, 'next_checkpoint')):
        problem = _excerpt_error(script, field, limit, label)
        if problem:
            errors.append(problem)
    problem = _discussion_question_error(script)
    if problem:
        errors.append(problem)
    if story['franchise'] == 'congress_trade' and re.search(
            r'\b(?:\d+\s+days?\s+late|overdue|hid|hidden|concealed)\b', headline, re.I):
        errors.append('a disclosure lag does not establish a late filing or concealment')
    if story['franchise'] == 'reddit_radar' and re.search(r'\b(?:bought|buying|sold|selling)\b', text, re.I):
        errors.append('mention counts do not establish actual trades')
    return errors
