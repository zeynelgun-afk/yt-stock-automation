import asyncio
import edge_tts
import logging
import re
import requests
import subprocess
from pathlib import Path
from typing import Tuple, Optional
from config import DEFAULT_VOICE, TEMP_DIR, ELEVENLABS_API_KEY, OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceGenerator:
    def __init__(self, voice: str = DEFAULT_VOICE,
                 elevenlabs_key: str = ELEVENLABS_API_KEY,
                 openai_key: str = OPENAI_API_KEY):
        self.voice = voice
        self.elevenlabs_key = elevenlabs_key
        self.openai_key = openai_key

    def _generate_elevenlabs(self, text: str, output_path: str) -> bool:
        """Generates hyper-realistic human voice via ElevenLabs API (Adam/Rachel voice)."""
        if not self.elevenlabs_key:
            return False
        try:
            logger.info("Generating studio-quality voice via ElevenLabs...")
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel - Professional Female Voice
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": self.elevenlabs_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.1}
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"ElevenLabs audio generated: {output_path}")
                return True
            logger.warning(f"ElevenLabs API status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"ElevenLabs TTS failed: {e}")
        return False

    def _generate_openai(self, text: str, output_path: str) -> bool:
        """Generates natural voice via OpenAI TTS-1-HD (Onyx voice)."""
        if not self.openai_key:
            return False
        try:
            logger.info("Generating voice via OpenAI tts-1-hd...")
            url = "https://api.openai.com/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "tts-1-hd",
                "input": text,
                "voice": "onyx"
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"OpenAI TTS audio generated: {output_path}")
                return True
            logger.warning(f"OpenAI TTS status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"OpenAI TTS failed: {e}")
        return False

    async def _generate_edge_tts_async(self, text: str, output_path: str, subtitle_path: Optional[str] = None) -> bool:
        """Generates voice via Edge-TTS and word-boundary SRT subtitles."""
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            submaker = edge_tts.SubMaker()

            with open(output_path, "wb") as file:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        file.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        submaker.feed(chunk)

            if subtitle_path:
                with open(subtitle_path, "w", encoding="utf-8") as sub_file:
                    sub_file.write(submaker.get_srt())

            logger.info(f"Edge-TTS audio generated: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Edge-TTS failed: {e}")
            # A partially written file must not survive — generate_audio treats
            # any existing temp file as a usable voiceover during fallback
            Path(output_path).unlink(missing_ok=True)
            return False

    @staticmethod
    def _audio_duration(audio_path: str) -> float:
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True, timeout=30,
            )
            return float(out.stdout.strip())
        except Exception as e:
            logger.warning(f"Could not probe audio duration: {e}")
            return 0.0

    @staticmethod
    def _rescale_srt(srt_path: str, factor: float) -> None:
        """Stretches every SRT timestamp by `factor`. Word timings come from the
        Edge-TTS reference audio; the premium voiceover speaks at a different
        pace, so timings must be scaled to its real duration or subtitles drift."""
        def scale(match):
            h, m, s, ms = (int(g) for g in match.groups())
            total_ms = int(round(((h * 3600 + m * 60 + s) * 1000 + ms) * factor))
            h2, rem = divmod(total_ms, 3600000)
            m2, rem = divmod(rem, 60000)
            s2, ms2 = divmod(rem, 1000)
            return f"{h2:02d}:{m2:02d}:{s2:02d},{ms2:03d}"

        content = Path(srt_path).read_text(encoding="utf-8")
        content = re.sub(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", scale, content)
        Path(srt_path).write_text(content, encoding="utf-8")

    def generate_audio(self, text: str, output_filename: str = "voiceover.mp3",
                       srt_filename: str = "subtitles.srt") -> Tuple[str, str]:
        """Generates audio voiceover with fallback order: ElevenLabs -> OpenAI -> Edge-TTS.
        Always generates SRT subtitles via Edge-TTS to maintain word-level ASS subtitle sync.
        """
        out_audio = str(TEMP_DIR / output_filename)
        out_srt = str(TEMP_DIR / srt_filename) if srt_filename else None

        # 1. Always generate SRT subtitles via Edge-TTS
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        temp_edge_audio = str(TEMP_DIR / f"temp_edge_{output_filename}")
        loop.run_until_complete(self._generate_edge_tts_async(text, temp_edge_audio, out_srt))
        loop.close()

        # 2. Try Premium TTS (ElevenLabs -> OpenAI TTS -> fallback to Edge-TTS)
        success = self._generate_elevenlabs(text, out_audio)
        if not success:
            success = self._generate_openai(text, out_audio)
        if not success:
            logger.info("Falling back to Edge-TTS for primary voiceover.")
            if Path(temp_edge_audio).exists():
                Path(temp_edge_audio).replace(out_audio)
                success = True
            else:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(self._generate_edge_tts_async(text, out_audio, out_srt))
                loop.close()
        else:
            # Premium voice pacing differs from the Edge-TTS reference the SRT
            # was timed against — stretch the SRT to the real voiceover length.
            if out_srt and Path(temp_edge_audio).exists():
                edge_dur = self._audio_duration(temp_edge_audio)
                premium_dur = self._audio_duration(out_audio)
                if edge_dur > 0 and premium_dur > 0:
                    factor = premium_dur / edge_dur
                    self._rescale_srt(out_srt, factor)
                    logger.info(f"Rescaled SRT timings by {factor:.3f}x to match premium voiceover.")
            # Clean up temp edge audio if premium voice succeeded
            if Path(temp_edge_audio).exists():
                Path(temp_edge_audio).unlink()

        if success:
            return out_audio, out_srt
        return "", ""

if __name__ == "__main__":
    vg = VoiceGenerator()
    audio_path, srt_path = vg.generate_audio("Hello Wall Street investors! Nvidia stock surges six percent today.", "test_voice.mp3", "test_sub.srt")
    print("Audio path:", audio_path)
    print("SRT path:", srt_path)
