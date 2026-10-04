import os
import sys
import json
import logging
from pathlib import Path
from delivery_claims import DeliveryClaims
from comment_responder import CHANNEL_ID
from config import YOUTUBE_CLIENT_SECRET_FILE, BASE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RECONSENT_RECIPE = (
    "token.json geçersiz — lokalde OAuth akışını yeniden çalıştırıp "
    "`gh secret set YT_LOCAL_TOKEN_JSON < token.json` ile secret'ı güncelle."
)


class YouTubePublisher:
    def __init__(self, client_secret_file: str = YOUTUBE_CLIENT_SECRET_FILE):
        self.client_secret_path = BASE_DIR / client_secret_file
        self.token_path = BASE_DIR / "token.json"
        self.last_error = ""   # human-readable reason for the last failed upload
        self._ensure_credentials()

    def _ensure_credentials(self):
        """Creates client_secret.json and token.json from environment variables if missing on disk."""
        if not self.client_secret_path.exists():
            env_secret = os.getenv("YT_LOCAL_CLIENT_SECRET_JSON", "")
            if env_secret:
                try:
                    with open(self.client_secret_path, "w", encoding="utf-8") as f:
                        f.write(env_secret)
                    logger.info("Created client_secret.json from environment variable.")
                except Exception as e:
                    logger.error(f"Failed to write client_secret.json: {e}")

        if not self.token_path.exists():
            env_token = os.getenv("YT_LOCAL_TOKEN_JSON", "")
            if env_token:
                try:
                    with open(self.token_path, "w", encoding="utf-8") as f:
                        f.write(env_token)
                    logger.info("Created token.json from environment variable.")
                except Exception as e:
                    logger.error(f"Failed to write token.json: {e}")

    def upload_video(self, video_path: str, title: str, description: str, tags: list[str], is_shorts: bool = True, privacy_status: str = "public", thumbnail_path: str = "", extra_tags: list[str] | None = None, contains_synthetic_media: bool = False) -> str:
        """Uploads video to YouTube channel using YouTube Data API v3 and OAuth 2.0.

        Returns the video ID, or "" on failure (reason in self.last_error).
        This used to return a mock ID when credentials were missing, which made
        the pipeline Telegram a false '✅ Yayında' while nothing was published.

        `contains_synthetic_media` sets status.containsSyntheticMedia (YouTube's
        "Altered or synthetic content" disclosure, required since the platform's
        Jul-2025 inauthentic-content policy update whenever AI-generated video
        could be mistaken for real footage). Pass True when the render used any
        Higgsfield/Seedance AI-generated background clip; leave False for
        Pexels stock footage, gradients, or solid-color backgrounds.
        """
        self.last_error = ""
        if not self.client_secret_path.exists():
            self.last_error = (f"client_secret.json missing at {self.client_secret_path} "
                               "(YT_LOCAL_CLIENT_SECRET_JSON secret unset?)")
            logger.error(self.last_error)
            return ""

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
            # readonly + analytics ride along so one OAuth consent also covers
            # the analytics feedback loop (analytics_reporter.py). Only used for
            # NEW consent flows — an existing token keeps its granted scopes,
            # forcing the new list onto it would make refresh fail (invalid_scope).
            SCOPES = [
                UPLOAD_SCOPE,
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.force-ssl",
            ]
            creds = None

            # Load saved OAuth token with the scopes it was actually granted
            if self.token_path.exists():
                try:
                    creds = Credentials.from_authorized_user_file(str(self.token_path))
                    if UPLOAD_SCOPE not in (creds.scopes or []):
                        logger.warning("token.json lacks the upload scope; re-consent needed.")
                        creds = None
                except Exception as e:
                    logger.warning(f"Failed to load token.json: {e}")

            # Refresh token if expired or authenticate
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        # invalid_grant = the refresh token itself died (the
                        # Jul-31 failure mode) — the operator must re-consent
                        raise RuntimeError(f"OAuth refresh failed ({e}). {RECONSENT_RECIPE}") from e
                elif os.getenv("CI") or not sys.stdin.isatty():
                    # Never open the interactive browser flow on a headless
                    # runner — it used to block waiting for a browser callback
                    # until the job timeout, silently burning the slot
                    raise RuntimeError(f"No usable OAuth token on headless runner. {RECONSENT_RECIPE}")
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_path), SCOPES)
                    creds = flow.run_local_server(port=0)

                # Save token for future automatic uploads
                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())

            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
            channels = youtube.channels().list(part='id', mine=True).execute(num_retries=2).get('items', [])
            if len(channels) != 1 or channels[0].get('id') != CHANNEL_ID:
                raise RuntimeError('Unexpected YouTube channel; no upload sent')

            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description + ("\n\n#shorts #stocks #finance" if is_shorts else "\n\n#stocks #investing"),
                    # extra_tags = machine metadata (fr:/w:/v:) — tags are not
                    # shown to viewers, but the weekly self-improvement loop
                    # reads them back for exact franchise + pacing calibration
                    "tags": list(tags) + list(extra_tags or []),
                    "categoryId": "27",  # Education / Finance
                    "defaultLanguage": "en",
                    "defaultAudioLanguage": "en",
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": contains_synthetic_media
                }
            }

            # Business-event identities survive regenerated media/title and
            # checkout changes. Reject missing identity rather than hash a draft.
            identities = [f'{CHANNEL_ID}:{tag}' for tag in (extra_tags or [])
                          if isinstance(tag, str) and tag.startswith('ev:') and len(tag) > 3]
            claims = DeliveryClaims()
            attempt, receipt = claims.start('upload', identities)
            if receipt:
                return receipt
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            logger.info("Uploading video to YouTube channel...")
            # Even a timeout/5xx can mean a video was created. Never retry the
            # insertion or reconstruct a resumable request after ambiguity.
            response = request.execute(num_retries=0)
            video_id = response.get("id")
            if not isinstance(video_id, str) or not video_id.strip():
                raise RuntimeError('Ambiguous upload; operator reconciliation required')
            claims.complete(attempt, video_id)  # durable before thumbnails/alerts
            logger.info("Successfully uploaded video %s", video_id)

            if thumbnail_path and Path(thumbnail_path).exists():
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path)
                    ).execute()
                    logger.info("Custom thumbnail set.")
                except Exception as e:
                    # Non-fatal: video is live, YouTube just keeps an auto-frame
                    logger.warning(f"Thumbnail upload failed: {e}")

            return video_id
        except Exception as e:
            self.last_error = f"YouTube upload stopped ({type(e).__name__}); inspect durable delivery claims"
            logger.error(self.last_error)
            return ""

if __name__ == "__main__":
    yp = YouTubePublisher()
    print("YouTube Publisher ready.")
