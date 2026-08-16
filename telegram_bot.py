import requests
import logging
import subprocess
from pathlib import Path
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TEMP_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram Bot API rejects uploads over 50 MB — long recaps routinely exceed
# it, which used to mean the operator never got a preview of exactly the
# videos most worth reviewing.
TELEGRAM_MAX_UPLOAD_BYTES = 48 * 1024 * 1024


class TelegramApprovalBot:
    """Operator notification channel. The channel publishes FULLY AUTONOMOUSLY
    (deliberate decision, 2026-08-16): there is no approval gate — the old
    inline-button approve/reject flow was removed as dead code. Everything here
    is FYI/alerting and must never block a publish."""

    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    def send_text(self, message: str) -> bool:
        """Sends a plain text notification (e.g. pipeline failure alerts)."""
        if not self.token or not self.chat_id:
            logger.warning("Telegram not configured; cannot send text notification.")
            return False
        try:
            res = requests.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": message},
                timeout=15,
            )
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Telegram sendMessage error: {e}")
            return False

    def _preview_within_limit(self, video_path: str) -> str:
        """Path to a sendable preview: the original if under the API cap, else
        a quick low-bitrate 720p transcode. Empty string if neither works."""
        try:
            if Path(video_path).stat().st_size <= TELEGRAM_MAX_UPLOAD_BYTES:
                return video_path
        except OSError:
            return ""

        preview = str(TEMP_DIR / f"tg_preview_{Path(video_path).stem}.mp4")
        cmd = ["ffmpeg", "-y", "-i", video_path,
               "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "30", "-c:a", "aac", "-b:a", "96k", preview]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if res.returncode == 0 and Path(preview).stat().st_size <= TELEGRAM_MAX_UPLOAD_BYTES:
                return preview
            logger.warning("Could not produce a Telegram-sized preview.")
        except Exception as e:
            logger.warning(f"Preview transcode failed: {e}")
        return ""

    def send_video_notification(self, video_path: str, title: str,
                                is_shorts: bool = True,
                                duration_s: float = 0.0) -> bool:
        """Sends the rendered video to Telegram as an FYI — no buttons, no waiting.

        The pipeline publishes regardless of the outcome; a Telegram failure
        must never block a YouTube upload. Caption is plain text on purpose:
        parse_mode Markdown made any unbalanced */_ in an LLM title bounce the
        whole notification with a 400.
        """
        if not self.token or not self.chat_id:
            logger.warning("Telegram BOT Token or Chat ID not configured. Skipping notification.")
            return False

        dur_line = f"\n⏱ Süre: {duration_s:.0f}sn" if duration_s else ""
        caption = (f"🎬 {'SHORTS' if is_shorts else 'LONG RECAP'} — YouTube'a yükleniyor"
                   f"{dur_line}\n\n📌 {title}")

        preview_path = self._preview_within_limit(video_path)
        if not preview_path:
            return self.send_text(caption + "\n\n(Önizleme 50MB Telegram sınırına sığdırılamadı.)")

        try:
            with open(preview_path, "rb") as video_file:
                res = requests.post(
                    f"{self.api_url}/sendVideo",
                    data={"chat_id": self.chat_id, "caption": caption},
                    files={"video": video_file},
                    timeout=180,
                )
            if res.status_code != 200:
                logger.error(f"Failed to send video to Telegram: {res.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

if __name__ == "__main__":
    bot = TelegramApprovalBot()
    print("Telegram notification bot ready.")
