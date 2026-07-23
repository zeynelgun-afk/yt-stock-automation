import requests
import json
import time
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

    def send_video_and_wait_for_approval(self, video_path: str, title: str, description: str, tags: list[str], is_shorts: bool = True, timeout_seconds: int = 300) -> bool:
        """Sends the rendered video file to Telegram and waits for user's inline button response."""
        if not self.token or not self.chat_id:
            logger.warning("Telegram BOT Token or Chat ID not configured. Skipping Telegram approval.")
            return False

        file_name = Path(video_path).name
        caption = f"🎬 **NEW {'SHORTS' if is_shorts else 'LONG RECAP'} VIDEO READY FOR APPROVAL** 🎬\n\n" \
                  f"📌 **Title:** {title}\n\n" \
                  f"📝 **Description:** {description[:200]}...\n\n" \
                  f"👇 *Lütfen aşağıdaki butonla onaylayın:* "

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Onayla & YouTube'a Yükle", "callback_data": f"approve_{file_name}"},
                    {"text": "❌ Reddet", "callback_data": f"reject_{file_name}"}
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
                if res.status_code != 200:
                    logger.error(f"Failed to send video to Telegram: {res.text}")
                    return False

                sent_msg = res.json().get("result", {})
                msg_id = sent_msg.get("message_id")
                logger.info(f"Video sent to Telegram (Msg ID: {msg_id}). Waiting up to {timeout_seconds}s for your approval...")

        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

        # Listen for user's inline button click (callback_query)
        start_time = time.time()
        last_update_id = 0

        # Flush old updates first
        try:
            updates_res = requests.get(f"{self.api_url}/getUpdates?offset=-1", timeout=5).json()
            if updates_res.get("result"):
                last_update_id = updates_res["result"][-1]["update_id"] + 1
        except Exception:
            pass

        while time.time() - start_time < timeout_seconds:
            try:
                up_url = f"{self.api_url}/getUpdates?offset={last_update_id}&timeout=5"
                up_res = requests.get(up_url, timeout=10)
                if up_res.status_code == 200:
                    results = up_res.json().get("result", [])
                    for update in results:
                        last_update_id = update["update_id"] + 1
                        cb = update.get("callback_query")
                        if cb:
                            cb_id = cb["id"]
                            cb_data = cb.get("data", "")

                            if cb_data == f"approve_{file_name}":
                                logger.info("User APPROVED the video!")
                                # Answer Telegram callback popup
                                requests.post(f"{self.api_url}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "✅ Video onaylandı! YouTube'a yükleniyor..."})
                                # Update Telegram message caption
                                edit_caption = f"✅ **VİDEO ONAYLANDI VE YOUTUBE'A YÜKLENİYOR!**\n\n📌 **Title:** {title}"
                                requests.post(f"{self.api_url}/editMessageCaption", json={"chat_id": self.chat_id, "message_id": msg_id, "caption": edit_caption, "parse_mode": "Markdown"})
                                return True

                            elif cb_data == f"reject_{file_name}":
                                logger.info("User REJECTED the video.")
                                requests.post(f"{self.api_url}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "❌ Video reddedildi."})
                                edit_caption = f"❌ **VİDEO REDDEDİLDİ**\n\n📌 **Title:** {title}"
                                requests.post(f"{self.api_url}/editMessageCaption", json={"chat_id": self.chat_id, "message_id": msg_id, "caption": edit_caption, "parse_mode": "Markdown"})
                                return False

            except Exception as e:
                logger.error(f"Error polling Telegram updates: {e}")

            time.sleep(2)

        logger.warning("Timeout reached waiting for Telegram approval.")
        return False

if __name__ == "__main__":
    bot = TelegramApprovalBot()
    print("Telegram approval bot ready.")
