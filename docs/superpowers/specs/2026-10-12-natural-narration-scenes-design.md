# Natural narration and speech-aligned scenes

The approved design replaces the single persistent dashboard with scenes that
follow the explanation. Hermes/GPT 6.1 generates spoken English and an ordered
scene plan in one JSON response. Shorts use 4–7 scenes; long videos use 8–32.
The Shorts opening is limited to 14 words. A measured 83-word conversational
sample took 41.3 seconds, so the initial Shorts budget is 66–76 words with a
78-word calibration ceiling. Emphasis is limited to 7 words and 65 characters.
Every scene contains at most 28 words. Text is fitted to a fixed content area
so narration, emphasis and progress cannot overlap, including in long videos.

Each scene has a fixed kind (event, comparison, explanation, caveat, takeaway),
an exact consecutive excerpt of the spoken script and optional exact emphasis.
The concatenated excerpts must reproduce the complete script. A comparison
must contain at least two numeric quantities. No independently generated
headlines, figures, dates, or claims enter the renderer.

Conversational examples guide short sentences, contractions and natural pauses
while preserving source attribution and uncertainty. The existing selected
ElevenLabs voice synthesizes the whole script in one request. Its measured word
SRT determines scene boundaries, phrase emphasis and captions. No guessed time
division or silent static-layout fallback is used when alignment is invalid.

Remotion renders a distinct layout for each kind, with restrained entrances,
readable text, paired figures for comparisons, a visible limitation scene and
captions grouped within each scene. Market context remains explicitly labelled
and uses real candles. A timeline artifact records the actual boundaries.

Verification covers malformed scene partitions, invented emphasis, altered
numbers, subtitle mismatch, pauses and final-scene coverage. A real subscription
script, selected voice and complete local render verify the integration before
shipping. Internal review does not upload or send messages. CI remains offline.

## Local verification on 2026-10-12

- 167 offline tests passed, including changed numeric claims, partial emphasis,
  subtitle mismatches, pauses, shared subtitle cues and bounded plan correction.
- Real Hermes/GPT 6.1 produced the scripts. The selected Deniz voice generated
  measured word subtitles. All review facts are explicitly fictional.
- Shorts: 70 words, 6 scenes, 34.37-second voice, 34.67-second rendered video.
- Long: 411 words, 25 scenes, 199.32-second voice, 199.64-second rendered video.
- H.264/AAC outputs at 1080×1920 and 1920×1080. No review content was published.
