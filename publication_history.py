"""Authenticated upload history. An unavailable history must never mean empty."""
import json
import os
from datetime import datetime, timedelta, timezone

from config import BASE_DIR


class HistoryUnavailable(RuntimeError):
    pass


def youtube_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = BASE_DIR / 'token.json'
    if path.exists():
        creds = Credentials.from_authorized_user_file(str(path))
    elif os.getenv('YT_LOCAL_TOKEN_JSON'):
        creds = Credentials.from_authorized_user_info(json.loads(os.environ['YT_LOCAL_TOKEN_JSON']))
    else:
        raise HistoryUnavailable('YouTube credentials unavailable')
    if 'https://www.googleapis.com/auth/youtube.readonly' not in (creds.scopes or []):
        raise HistoryUnavailable('YouTube readonly scope unavailable')
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Publication timestamp has no timezone')
    return parsed.astimezone(timezone.utc)


def fetch_upload_history(days=30, *, client=None, now=None):
    """Read all pages, then filter by actual video publication time, not playlist time.

    All privacy states participate in dedup. Metadata failures fail closed;
    no partial page is returned as if it were a complete history.
    """
    try:
        if client is None:
            from googleapiclient.discovery import build
            client = build('youtube', 'v3', credentials=youtube_credentials(), cache_discovery=False)
        channels = client.channels().list(part='contentDetails', mine=True).execute()['items']
        if len(channels) != 1:
            raise HistoryUnavailable('Could not identify one authenticated channel')
        playlist = channels[0]['contentDetails']['relatedPlaylists']['uploads']
        ids, page, pages = [], None, set()
        while True:
            response = client.playlistItems().list(
                part='contentDetails', playlistId=playlist, maxResults=50,
                **({'pageToken': page} if page else {})).execute()
            ids.extend(item['contentDetails']['videoId'] for item in response['items'])
            page = response.get('nextPageToken')
            if not page:
                break
            if page in pages or len(pages) >= 100:
                raise HistoryUnavailable('Upload pagination did not complete')
            pages.add(page)
        ids = list(dict.fromkeys(ids))
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
        result = []
        for offset in range(0, len(ids), 50):
            batch = ids[offset:offset + 50]
            items = client.videos().list(part='snippet,status,contentDetails,statistics',
                                        id=','.join(batch)).execute()['items']
            if {item['id'] for item in items} != set(batch):
                raise HistoryUnavailable('Upload metadata incomplete; dedup cannot be verified')
            for item in items:
                snippet = item['snippet']
                if parse_time(snippet['publishedAt']) < cutoff:
                    continue
                tags = dict(tag.split(':', 1) for tag in snippet.get('tags', []) if ':' in tag)
                result.append(dict(video_id=item['id'], title=snippet['title'],
                                   published_at=snippet['publishedAt'], machine=tags,
                                   event_ids=[t[3:] for t in snippet.get('tags', []) if t.startswith('ev:')],
                                   privacy=item['status']['privacyStatus'],
                                   duration=item['contentDetails']['duration'],
                                   views=int(item.get('statistics', {}).get('viewCount', 0))))
        return sorted(result, key=lambda row: row['published_at'], reverse=True)
    except HistoryUnavailable:
        raise
    except Exception as exc:
        # OAuth/HTTP exception bodies can contain credentials or request URLs.
        raise HistoryUnavailable(f'Upload history failed ({type(exc).__name__})') from None
