import os
import json
import logging
from pathlib import Path
from config import YOUTUBE_CLIENT_SECRET_FILE, BASE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YouTubePublisher:
    def __init__(self, client_secret_file: str = YOUTUBE_CLIENT_SECRET_FILE):
        self.client_secret_path = BASE_DIR / client_secret_file
        self.token_path = BASE_DIR / "token.json"
        self._ensure_credentials()

    def _ensure_credentials(self):
        """Creates client_secret.json and token.json from environment variables if missing on disk."""
        if not self.client_secret_path.exists():
            env_secret = os.getenv("YOUTUBE_CLIENT_SECRET_JSON", "")
            if env_secret:
                try:
                    with open(self.client_secret_path, "w", encoding="utf-8") as f:
                        f.write(env_secret)
                    logger.info("Created client_secret.json from environment variable.")
                except Exception as e:
                    logger.error(f"Failed to write client_secret.json: {e}")

        if not self.token_path.exists():
            env_token = os.getenv("YOUTUBE_TOKEN_JSON", "")
            if env_token:
                try:
                    with open(self.token_path, "w", encoding="utf-8") as f:
                        f.write(env_token)
                    logger.info("Created token.json from environment variable.")
                except Exception as e:
                    logger.error(f"Failed to write token.json: {e}")

    def upload_video(self, video_path: str, title: str, description: str, tags: list[str], is_shorts: bool = True, privacy_status: str = "public") -> str:
        """Uploads video to YouTube channel using YouTube Data API v3 and OAuth 2.0."""
        if not self.client_secret_path.exists():
            logger.warning(f"YouTube client_secret.json missing at {self.client_secret_path}. Skipping live YouTube upload.")
            return "MOCK_YOUTUBE_VIDEO_ID_12345"

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
            creds = None

            # Load saved OAuth token if available
            if self.token_path.exists():
                try:
                    creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
                except Exception as e:
                    logger.warning(f"Failed to load token.json: {e}")

            # Refresh token if expired or authenticate
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_path), SCOPES)
                    creds = flow.run_local_server(port=0)

                # Save token for future automatic uploads
                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())

            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description + ("\n\n#shorts #stocks #finance" if is_shorts else "\n\n#stocks #investing"),
                    "tags": tags,
                    "categoryId": "27"  # Education / Finance
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            
            logger.info("Uploading video to YouTube channel...")
            response = request.execute()
            video_id = response.get("id")
            logger.info(f"Successfully uploaded! Video URL: https://youtu.be/{video_id}")
            return video_id
        except Exception as e:
            logger.error(f"YouTube Upload Failed: {e}")
            return ""

if __name__ == "__main__":
    yp = YouTubePublisher()
    print("YouTube Publisher ready.")
