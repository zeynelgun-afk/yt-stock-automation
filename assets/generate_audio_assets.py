import os
import math
import wave
import struct
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MUSIC_DIR = BASE_DIR / "assets" / "music"
SFX_DIR = BASE_DIR / "assets" / "sfx"

MUSIC_DIR.mkdir(parents=True, exist_ok=True)
SFX_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 44100

def generate_whoosh_sfx(output_path: str, duration: float = 0.4):
    """Synthesizes a clean white noise pitch sweep 'whoosh' sound effect for scene cuts."""
    num_samples = int(SAMPLE_RATE * duration)
    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        
        import random
        for i in range(num_samples):
            t = i / num_samples
            # Envelope: Gaussian-like rise and fall
            envelope = math.sin(t * math.pi) ** 2
            # Frequency modulation sweep
            freq = 200 + 1200 * math.sin(t * math.pi)
            noise = (random.random() * 2.0 - 1.0)
            sine = math.sin(2 * math.pi * freq * (i / SAMPLE_RATE))
            val = (noise * 0.6 + sine * 0.4) * envelope * 0.7
            sample = int(val * 32767)
            sample = max(-32768, min(32767, sample))
            wav_file.writeframes(struct.pack('<h', sample))

def generate_background_music(output_path: str, duration: float = 60.0):
    """Synthesizes a lo-fi ambient stock market synth pad background track."""
    num_samples = int(SAMPLE_RATE * duration)
    chord_freqs = [130.81, 164.81, 196.00, 246.94]  # C Major 7 chord
    
    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        
        for i in range(num_samples):
            t = i / SAMPLE_RATE
            # Slow subtle pulse modulation
            lfo = 0.8 + 0.2 * math.sin(2 * math.pi * 0.5 * t)
            
            sample_val = 0.0
            for idx, f in enumerate(chord_freqs):
                # Detune & harmonic oscillation
                detune = 1.0 + 0.002 * math.sin(t * (idx + 1))
                sample_val += math.sin(2 * math.pi * f * detune * t)
            
            sample_val = (sample_val / len(chord_freqs)) * lfo * 0.25
            sample = int(sample_val * 32767)
            sample = max(-32768, min(32767, sample))
            wav_file.writeframes(struct.pack('<h', sample))

if __name__ == "__main__":
    whoosh_path = str(SFX_DIR / "whoosh.wav")
    music_path = str(MUSIC_DIR / "bg_music.wav")
    
    print("Generating audio assets...")
    generate_whoosh_sfx(whoosh_path)
    generate_background_music(music_path)
    print("Audio assets generated successfully:")
    print("SFX:", whoosh_path)
    print("Music:", music_path)
