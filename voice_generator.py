import asyncio
import base64
import edge_tts
import logging
import requests
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from config import DEFAULT_VOICE, TEMP_DIR, ELEVENLABS_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _srt_timestamp(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class VoiceGenerator:
    def __init__(self, voice: str = DEFAULT_VOICE,
                 elevenlabs_key: str = ELEVENLABS_API_KEY):
        self.voice = voice
        self.elevenlabs_key = elevenlabs_key
        # Which engine actually produced the last voiceover — stamped onto the
        # upload as a v: machine tag so weekly analytics can calibrate pacing
        # per engine instead of mixing two different speaking rates
        self.engine_used = ""

    def _generate_elevenlabs(self, text: str, output_path: str,
                             subtitle_path: Optional[str]) -> bool:
        """ElevenLabs multilingual_v2 (most natural model) via the
        /with-timestamps endpoint: one call returns both the audio and
        character-level alignment, so the SRT is built from the MEASURED word
        timings of the actual published voiceover.

        This replaced the old scheme (turbo model + Edge-TTS reference audio +
        linear SRT stretch), which drifted several hundred ms mid-video on
        5-6 minute recaps because ElevenLabs places pauses differently than
        Edge-TTS — endpoint-matched stretching can't fix the middle.
        """
        if not self.elevenlabs_key:
            return False
        try:
            logger.info("Generating studio-quality voice via ElevenLabs (multilingual_v2)...")
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel - Professional Female Voice
            url = (f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                   f"/with-timestamps?output_format=mp3_44100_128")
            headers = {
                "xi-api-key": self.elevenlabs_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.8,
                    "style": 0.25,
                    "use_speaker_boost": True,
                    # 1.1 (old turbo setting) audibly rushed the read; 1.05 keeps
                    # the pace brisk without the sped-up artifact. Word budgets in
                    # script_generator were measured at the old pace — re-measure
                    # from the duration line in the Telegram FYI after changes here.
                    "speed": 1.05,
                },
            }
            # A 5-6 minute recap takes a while to synthesize — 30s timed out
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            if resp.status_code != 200:
                logger.warning(f"ElevenLabs API status {resp.status_code}: {resp.text[:300]}")
                return False

            body = resp.json()
            audio_b64 = body.get("audio_base64")
            alignment = body.get("alignment") or {}
            if not audio_b64:
                logger.warning("ElevenLabs response carried no audio_base64.")
                return False
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_b64))

            if subtitle_path:
                words = self._words_from_alignment(text, alignment)
                if not words:
                    # No measured timings -> downstream ASS conversion would fail
                    # or drift. Treat as a full failure so Edge-TTS (which times
                    # its own audio) takes over.
                    logger.error("ElevenLabs returned no usable alignment — "
                                 "falling back so subtitles stay in sync.")
                    Path(output_path).unlink(missing_ok=True)
                    return False
                self._write_word_srt(words, subtitle_path)

            logger.info(f"ElevenLabs audio + measured word timings generated: {output_path}")
            return True
        except Exception as e:
            logger.warning(f"ElevenLabs TTS failed: {e}")
            Path(output_path).unlink(missing_ok=True)
        return False

    @staticmethod
    def _words_from_alignment(text: str, alignment: dict) -> List[Tuple[str, float, float]]:
        """(word, start_s, end_s) list from character-level alignment."""
        chars = alignment.get("characters") or []
        starts = alignment.get("character_start_times_seconds") or []
        ends = alignment.get("character_end_times_seconds") or []
        if not (chars and len(chars) == len(starts) == len(ends)):
            return []
        words: List[Tuple[str, float, float]] = []
        cur, cur_start, cur_end = "", 0.0, 0.0
        for ch, st, et in zip(chars, starts, ends):
            if ch.isspace():
                if cur:
                    words.append((cur, cur_start, cur_end))
                    cur = ""
                continue
            if not cur:
                cur_start = st
            cur += ch
            cur_end = et
        if cur:
            words.append((cur, cur_start, cur_end))
        return words

    @staticmethod
    def _write_word_srt(words: List[Tuple[str, float, float]], srt_path: str) -> None:
        """One cue per word — the format subtitle_generator groups into phrases."""
        lines = []
        for i, (word, st, et) in enumerate(words, start=1):
            lines.append(f"{i}\n{_srt_timestamp(st)} --> {_srt_timestamp(max(et, st + 0.05))}\n{word}\n")
        Path(srt_path).write_text("\n".join(lines), encoding="utf-8")

    async def _generate_edge_tts_async(self, text: str, output_path: str, subtitle_path: Optional[str] = None) -> bool:
        """Generates voice via Edge-TTS and word-boundary SRT subtitles."""
        try:
            # boundary must be requested explicitly: edge-tts defaults to
            # SentenceBoundary, and this code used to feed only "WordBoundary"
            # chunks — so nothing was ever fed, get_srt() returned "", and every
            # video shipped with an empty SRT and therefore no subtitles at all.
            communicate = edge_tts.Communicate(text, self.voice, boundary="WordBoundary")
            submaker = edge_tts.SubMaker()

            with open(output_path, "wb") as file:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        file.write(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        # Accept either so a future default change can't silently
                        # empty the subtitles again
                        submaker.feed(chunk)

            srt_text = submaker.get_srt()
            if not srt_text.strip():
                # Silent empty subtitles are the failure mode this guards against
                logger.error("Edge-TTS returned no subtitle cues — SRT would be empty.")
                Path(output_path).unlink(missing_ok=True)
                return False

            if subtitle_path:
                with open(subtitle_path, "w", encoding="utf-8") as sub_file:
                    sub_file.write(srt_text)

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

    def generate_audio(self, text: str, output_filename: str = "voiceover.mp3",
                       srt_filename: str = "subtitles.srt") -> Tuple[str, str]:
        """Voiceover + word-level SRT. Chain: ElevenLabs -> Edge-TTS.

        Both engines time the SRT against the audio they actually produced, so
        neither path can drift. There is deliberately no engine without word
        timings in the chain (the old OpenAI middle step shipped stretched
        Edge-TTS timings over a different voice's pacing).
        """
        out_audio = str(TEMP_DIR / output_filename)
        out_srt = str(TEMP_DIR / srt_filename) if srt_filename else None

        if self._generate_elevenlabs(text, out_audio, out_srt):
            self.engine_used = "11l"
            return out_audio, out_srt

        logger.info("Falling back to Edge-TTS for voiceover + subtitles.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(
                self._generate_edge_tts_async(text, out_audio, out_srt))
        finally:
            loop.close()

        if success:
            self.engine_used = "edge"
            return out_audio, out_srt
        return "", ""

if __name__ == "__main__":
    vg = VoiceGenerator()
    audio_path, srt_path = vg.generate_audio("Hello Wall Street investors! Nvidia stock surges six percent today.", "test_voice.mp3", "test_sub.srt")
    print("Audio path:", audio_path)
    print("SRT path:", srt_path)
