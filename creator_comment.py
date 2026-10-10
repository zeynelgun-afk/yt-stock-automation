"""Selective, source-backed owner comments. Pinning is not exposed by Data API."""
import argparse
from datetime import date
import json
import logging
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs
from comment_responder import CHANNEL_ID, WRITE_SCOPE
from delivery_claims import DeliveryClaims

logger = logging.getLogger(__name__)


def public_source(story):
    facts = story.get('facts') or {}
    items = [facts] + [r for r in facts.get('news', []) if isinstance(r, dict)]
    for item in items:
        url = item.get('url') or item.get('sourceUrl')
        if not isinstance(url, str) or len(url) > 1000:
            continue
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or any(c.isspace() for c in url) or parsed.hostname.endswith('financialmodelingprep.com')
                or any(k.lower() in {'apikey', 'api_key', 'token', 'access_token', 'key'} for k in parse_qs(parsed.query))):
            continue
        return url
    return None


def build_comment(story):
    """No generated facts, correction guesses, trading advice or generic CTA."""
    ticker = story.get('ticker', '')
    if not isinstance(ticker, str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,9}', ticker):
        return None
    facts, kind = story.get('facts') or {}, story.get('franchise')
    question = None
    if kind == 'congress_trade':
        try:
            trade = date.fromisoformat(facts['transactionDate'])
            disclosure = date.fromisoformat(facts['disclosureDate'])
            lag = (disclosure - trade).days
        except (KeyError, ValueError, TypeError):
            lag = -1
        if lag >= 7:
            question = (f"This {ticker} trade was disclosed {lag} days after the transaction. "
                        "Does that reporting lag make disclosures useful context, or mainly historical records to you?")
    elif kind == 'insider_watch' and facts.get('insider') and facts.get('transactionDate'):
        question = (f"For the {ticker} insider trade covered here, which context matters more to you: "
                    "the transaction size or the insider's existing ownership?")
    elif kind == 'earnings_shock' and facts.get('paradox') is True:
        question = (f"When {ticker}'s earnings and share-price reaction point in different directions, "
                    "which detail would you examine first: operating results or expectations?")
    source = public_source(story)
    parts = ([f"Source for the event covered in this video: {source}"] if source else [])
    if question:
        parts.append(question)
    return '\n\n'.join(parts) if parts else None


def post_comment(youtube, video_id, text, *, claims=None):
    channels = youtube.channels().list(part='id', mine=True).execute(num_retries=2).get('items', [])
    if len(channels) != 1 or channels[0]['id'] != CHANNEL_ID:
        raise RuntimeError('Unexpected YouTube channel')
    video = youtube.videos().list(part='snippet,status', id=video_id).execute(num_retries=2).get('items', [])
    if (len(video) != 1 or video[0]['snippet']['channelId'] != CHANNEL_ID
            or video[0]['status']['privacyStatus'] != 'public'):
        raise RuntimeError('Owner comment requires a public channel video')
    page = None
    for _ in range(10):
        response = youtube.commentThreads().list(part='snippet', videoId=video_id, maxResults=100,
            textFormat='plainText', **({'pageToken': page} if page else {})).execute(num_retries=2)
        for item in response.get('items', []):
            top = item['snippet']['topLevelComment']
            if top['snippet'].get('authorChannelId', {}).get('value') == CHANNEL_ID:
                return {'status': 'existing_owner_comment', 'comment_id': top['id'], 'pin_status': 'manual'}
        page = response.get('nextPageToken')
        if not page:
            break
    else:
        raise RuntimeError('Incomplete comment history; no comment posted')
    claims = claims or DeliveryClaims()
    attempt, receipt = claims.start('comment', [f'{CHANNEL_ID}:owner-video:{video_id}'])
    if receipt:
        return {'status': 'already_posted', 'comment_id': receipt, 'pin_status': 'manual'}
    result = youtube.commentThreads().insert(part='snippet', body={'snippet': {
        'channelId': CHANNEL_ID, 'videoId': video_id,
        'topLevelComment': {'snippet': {'textOriginal': text}}}}).execute(num_retries=0)
    comment_id = result.get('snippet', {}).get('topLevelComment', {}).get('id')
    if not isinstance(comment_id, str) or not comment_id.strip():
        raise RuntimeError('Ambiguous creator comment delivery; no automatic retry')
    claims.complete(attempt, comment_id)
    logger.info('Creator comment posted: %s', comment_id)
    return {'status': 'posted', 'comment_id': comment_id, 'pin_status': 'manual'}


def publish_for_story(video_id, story):
    text = build_comment(story)
    if not text:
        return {'status': 'not_applicable'}
    from googleapiclient.discovery import build
    from publication_history import youtube_credentials
    creds = youtube_credentials()
    if WRITE_SCOPE not in (creds.scopes or []):
        raise RuntimeError('YouTube comment write permission unavailable')
    result = post_comment(build('youtube', 'v3', credentials=creds, cache_discovery=False), video_id, text)
    return {**result, 'text': text, 'url': f"https://www.youtube.com/watch?v={video_id}&lc={result['comment_id']}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video_id')
    parser.add_argument('story_file', type=Path)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    payload = json.loads(args.story_file.read_text())
    story = payload.get('story', payload)
    result = publish_for_story(args.video_id, story) if args.publish else {'text': build_comment(story)}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
