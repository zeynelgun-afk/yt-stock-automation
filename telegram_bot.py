import requests
import json
import logging
from pathlib import Path
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramApprovalBot:
    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    def send_video_for_approval(self, video_path: str, title: str, description: str, is_shorts: bool = True) -> bool:
        """Sends the rendered video file with title, description, and Inline Approval Buttons to Telegram."""
        if not self.token or not self.chat_id:
            logger.warning("Telegram BOT Token or Chat ID not configured. Skipping Telegram notification.")
            return False

        caption = f"🎬 **NEW {'SHORTS' if is_shorts else 'LONG RECAP'} VIDEO READY FOR APPROVAL** 🎬\n\n" \
                  f"📌 **Title:** {title}\n\n" \
                  f"📝 **Description:** {description[:200]}...\n\n" \
                  f"👇 *Click below to approve and publish to YouTube:* "

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Onayla & YouTube'a Yükle", "callback_data": f"approve_{Path(video_path).name}"},
                    {"text": "❌ Reddet", "callback_data": f"reject_{Path(video_path).name}"}
                ]
            ]
        }

        try:
            with open(video_path, "rb") as video_file:
                files = {"video": video_file}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown",
                    "reply_markup": json.dumps(reply_markup)
                }
                res = requests.post(f"{self.api_url}/sendVideo", data=data, files=files, timeout=60)
                if res.status_code == 200:
                    logger.info("Video successfully sent to Telegram for user approval!")
                    return True
                else:
                    logger.error(f"Failed to send video to Telegram: {res.text}")
        except Exception as e:
            logger.error(f"Telegram approval bot error: {e}")
        return False

if __name__ == "__main__":
    bot = TelegramApprovalBot()
    print("Telegram approval bot initialized.")
