import asyncio
import edge_tts
import logging
from pathlib import Path
from config import DEFAULT_VOICE, TEMP_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceGenerator:
    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice

    async def _generate_audio_async(self, text: str, output_path: str, subtitle_path: str = None) -> bool:
        """Asynchronously converts text to speech MP3 using Edge-TTS and saves optional VTT subtitles."""
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

            logger.info(f"Audio generated successfully: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to generate voice: {e}")
            return False

    def generate_audio(self, text: str, output_filename: str = "voiceover.mp3", srt_filename: str = "subtitles.srt") -> tuple[str, str]:
        """Synchronous wrapper for text-to-speech generation."""
        out_audio = str(TEMP_DIR / output_filename)
        out_srt = str(TEMP_DIR / srt_filename) if srt_filename else None

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(self._generate_audio_async(text, out_audio, out_srt))
        loop.close()

        if success:
            return out_audio, out_srt
        return "", ""

if __name__ == "__main__":
    vg = VoiceGenerator()
    audio_path, srt_path = vg.generate_audio("Hello Wall Street investors! Nvidia stock surges six percent today.", "test_voice.mp3", "test_sub.srt")
    print("Audio path:", audio_path)
    print("SRT path:", srt_path)
