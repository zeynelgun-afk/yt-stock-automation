"""Higgsfield platform API client — AI-generated video backgrounds.

Two-step generation on https://platform.higgsfield.ai:
  1. text-to-image  (higgsfield-ai/soul/standard)  -> hosted image URL
  2. image-to-video (higgsfield-ai/dop/standard)   -> hosted mp4 URL

Auth: `Authorization: Key {HIGGSFIELD_API_KEY}:{HIGGSFIELD_API_SECRET}`.
Keys come from https://cloud.higgsfield.ai (platform account, separate from
the consumer higgsfield.ai subscription).

Every call fails soft (returns None) so the pipeline falls back to Pexels.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

import requests

from config import HIGGSFIELD_API_KEY, HIGGSFIELD_API_SECRET, TEMP_DIR

logger = logging.getLogger(__name__)

BASE_URL = "https://platform.higgsfield.ai"
TEXT2IMAGE_MODEL = "higgsfield-ai/soul/standard"
IMAGE2VIDEO_MODEL = "higgsfield-ai/dop/standard"

IMAGE_TIMEOUT_S = 180
VIDEO_TIMEOUT_S = 480
POLL_INTERVAL_S = 10

# Cinematic finance b-roll prompt; {theme} comes from the script's visual keywords
IMAGE_PROMPT_TEMPLATE = (
    "Cinematic photorealistic shot of {theme}, moody Wall Street atmosphere, "
    "glowing stock tickers and market data reflections, dramatic teal and "
    "amber lighting, shallow depth of field, high detail, no text overlays"
)
MOTION_PROMPT = (
    "Slow cinematic push-in with subtle parallax, flickering ticker lights, "
    "smooth professional camera movement"
)


class HiggsfieldClient:
    def __init__(self, api_key: str = HIGGSFIELD_API_KEY, api_secret: str = HIGGSFIELD_API_SECRET):
        self.api_key = api_key
        self.api_secret = api_secret

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.api_secret)

    # ------------------------------------------------------------------ http

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _submit(self, model_path: str, payload: dict) -> Optional[str]:
        """Submits a generation job, returns request_id or None."""
        try:
            resp = requests.post(
                f"{BASE_URL}/{model_path}", json=payload,
                headers=self._headers(), timeout=30,
            )
            if resp.status_code >= 400:
                logger.warning(f"Higgsfield submit failed ({model_path}): "
                               f"{resp.status_code} {resp.text[:300]}")
                return None
            request_id = resp.json().get("request_id")
            if not request_id:
                logger.warning(f"Higgsfield submit response has no request_id: {resp.text[:300]}")
            return request_id
        except Exception as e:
            logger.warning(f"Higgsfield submit error ({model_path}): {e}")
            return None

    def _wait(self, request_id: str, timeout_s: int) -> Optional[dict]:
        """Polls job status until completed/failed/timeout. Returns final status JSON."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{BASE_URL}/requests/{request_id}/status",
                    headers=self._headers(), timeout=30,
                )
                data = resp.json()
                status = data.get("status", "")
                if status == "completed":
                    return data
                if status in ("failed", "nsfw"):
                    logger.warning(f"Higgsfield job {request_id} ended with status: {status}")
                    return None
            except Exception as e:
                logger.warning(f"Higgsfield poll error for {request_id}: {e}")
            time.sleep(POLL_INTERVAL_S)
        logger.warning(f"Higgsfield job {request_id} timed out after {timeout_s}s")
        return None

    @staticmethod
    def _find_url(obj, extensions: tuple) -> Optional[str]:
        """Recursively finds the first URL with a matching extension in a status
        payload — schema-tolerant, since the docs don't pin the result format."""
        if isinstance(obj, str):
            base = obj.split("?", 1)[0].lower()
            if obj.startswith("http") and base.endswith(extensions):
                return obj
            return None
        if isinstance(obj, dict):
            values = obj.values()
        elif isinstance(obj, list):
            values = obj
        else:
            return None
        for v in values:
            found = HiggsfieldClient._find_url(v, extensions)
            if found:
                return found
        return None

    def _run_job(self, model_path: str, payload: dict, extensions: tuple,
                 timeout_s: int) -> Optional[str]:
        request_id = self._submit(model_path, payload)
        if not request_id:
            return None
        result = self._wait(request_id, timeout_s)
        if not result:
            return None
        url = self._find_url(result, extensions)
        if not url:
            logger.warning(f"Higgsfield job {request_id} completed but no asset URL found")
        return url

    # ------------------------------------------------------------------ api

    def generate_background_video(self, keywords: List[str], is_shorts: bool = True) -> Optional[str]:
        """Generates an AI background clip for the given theme keywords.
        Returns a local mp4 path, or None on any failure (caller falls back)."""
        if not self.enabled:
            return None

        theme = keywords[0] if keywords else "stock market trading floor"
        aspect_ratio = "9:16" if is_shorts else "16:9"

        logger.info(f"Higgsfield: generating background for theme '{theme}' ({aspect_ratio})...")
        image_url = self._run_job(
            TEXT2IMAGE_MODEL,
            {
                "prompt": IMAGE_PROMPT_TEMPLATE.format(theme=theme),
                "aspect_ratio": aspect_ratio,
                "resolution": "720p",
            },
            (".png", ".jpg", ".jpeg", ".webp"),
            IMAGE_TIMEOUT_S,
        )
        if not image_url:
            return None

        video_url = self._run_job(
            IMAGE2VIDEO_MODEL,
            {
                "image_url": image_url,
                "prompt": MOTION_PROMPT,
                "duration": 5,
            },
            (".mp4", ".mov", ".webm"),
            VIDEO_TIMEOUT_S,
        )
        if not video_url:
            return None

        safe_name = "".join([c if c.isalnum() else "_" for c in theme])[:40]
        out_path = str(TEMP_DIR / f"higgsfield_{safe_name}_{'shorts' if is_shorts else 'long'}.mp4")
        try:
            r = requests.get(video_url, stream=True, timeout=60)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=16384):
                    f.write(chunk)
        except Exception as e:
            logger.warning(f"Higgsfield video download failed: {e}")
            return None

        logger.info(f"Higgsfield AI background ready: {out_path}")
        return out_path
