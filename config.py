import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# API Keys
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
YOUTUBE_CLIENT_SECRET_FILE = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "client_secret.json")

# Directory Paths
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"
TEMP_DIR = BASE_DIR / "temp"

for d in [OUTPUT_DIR, ASSETS_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Video Configurations
SHORTS_RES = (1080, 1920)
LONG_RES = (1920, 1080)
FPS = 30

# Edge-TTS Voice Options
DEFAULT_VOICE = "en-US-ChristopherNeural"  # Professional Male American Accent
ALTERNATIVE_VOICE = "en-US-JennyNeural"    # Professional Female American Accent

# US Target Peak Hours (TSI / Turkey Time equivalents)
SCHEDULE_TIMES_TSI = {
    "shorts_1": "15:30",
    "shorts_2": "20:00",
    "long_recap": "23:30"
}
