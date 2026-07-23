import os
import logging
from pathlib import Path
from config import YOUTUBE_CLIENT_SECRET_FILE, BASE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YouTubePublisher:
    def __init__(self, client_secret_file: str = YOUTUBE_CLIENT_SECRET_FILE):
        self.client_secret_file = BASE_DIR / client_secret_file

    def upload_video(self, video_path: str, title: str, description: str, tags: list[str], is_shorts: bool = True, privacy_status: str = "public") -> str:
        """Uploads video to YouTube channel using YouTube Data API v3."""
        if not self.client_secret_file.exists():
            logger.warning(f"YouTube client_secret.json missing at {self.client_secret_file}. Skipping live YouTube upload.")
            return "MOCK_YOUTUBE_VIDEO_ID_12345"

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google_auth_oauthlib.flow import InstalledAppFlow

            SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
            flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)

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
            
            logger.info("Uploading video to YouTube...")
            response = request.execute()
            video_id = response.get("id")
            logger.info(f"Successfully uploaded! Video URL: https://youtu.be/{video_id}")
            return video_id
        except Exception as e:
            logger.error(f"YouTube Upload Failed: {e}")
            return ""

if __name__ == "__main__":
    yp = YouTubePublisher()
    print("YouTube Publisher initialized.")
