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
HIGGSFIELD_API_KEY = os.getenv("HIGGSFIELD_API_KEY", "")
HIGGSFIELD_API_SECRET = os.getenv("HIGGSFIELD_API_SECRET", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
YOUTUBE_CLIENT_SECRET_FILE = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "client_secret.json")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")  # Data API key (outlier scanner)

# Persistent data (learned packaging patterns, etc.)
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PATTERNS_FILE = DATA_DIR / "packaging_patterns.json"

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
# Consistency beats "optimal" — fixed times win with the algorithm.
SCHEDULE_TIMES_TSI = {
    "shorts_1": "15:30",       # US pre-market scroll hours
    "shorts_2": "20:00",       # 4.5h gap (1-2 Shorts/day, 4-6h apart)
    "long_recap": "23:05",     # NYSE close is 23:00 TSI (16:00 ET) — speed moat:
                               # the recap must be live within 15 min of the close
    "shorts_us_evening": "03:30",  # experiment slot: US evening scroll (20:30 ET)
}
