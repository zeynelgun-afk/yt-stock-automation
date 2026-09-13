import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from presenter_workflow import (finish_package, plan_segments, prepare_package,
                                probe, run, sha, validate_clip)
from voice_generator import VoiceGenerator


class PresenterPlanTests(unittest.TestCase):
    def test_limits_and_sentence_boundaries(self):
        words = [dict(start=float(i), end=i+.8, text='word.' if i % 4 == 3 else 'word')
                 for i in range(60)]
        short = plan_segments(words, 60, True)
        long = plan_segments(words, 60, False)
        self.assertEqual(len(short), 1)
        self.assertLessEqual(short[0]['end'], 6)
        self.assertEqual(len(long), 2)
        self.assertLessEqual(long[0]['end'], 8)
        self.assertGreaterEqual(long[1]['start'], 30)
        self.assertLessEqual(long[1]['end']-long[1]['start'], 5)
        self.assertTrue(all(s['text'].endswith('.') for s in long))

    def test_long_without_midpoint_sentence_gets_no_arbitrary_transition(self):
        words = [dict(start=float(i), end=i+.8, text='word') for i in range(60)]
        self.assertEqual(len(plan_segments(words, 60, False)), 1)
        with self.assertRaises(ValueError):
            plan_segments(words, 10, False)

    def test_main_voice_can_fail_without_edge_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch('voice_generator.TEMP_DIR', Path(tmp)):
            vg = VoiceGenerator(elevenlabs_key='')
            with patch.object(vg, '_generate_elevenlabs', return_value=False), \
                    patch.object(vg, '_generate_edge_tts_async') as edge:
                self.assertEqual(vg.generate_audio('test', allow_fallback=False), ('', ''))
                edge.assert_not_called()
                self.assertEqual(vg.engine_used, '')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class PresenterMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='deniz test ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Non-periodic waveform makes a wrong segment or offset distinguishable.
        t = np.arange(160000) / 16000
        signal = (.15 * np.sin(2*np.pi*(180*t + 25*t*t))).astype(np.float32)
        self.audio = self.root/'voice.wav'
        with wave.open(str(self.audio), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
            f.writeframes((signal * 32767).astype('<i2').tobytes())
        self.srt = self.root/'voice.srt'
        self.srt.write_text('1\n00:00:00,000 --> 00:00:02,500\nHello.\n\n'
                            '2\n00:00:02,500 --> 00:00:09,500\nCharts.\n')
        self.base = self.root/'base.mp4'
        self.make_video(self.base, self.audio, 10, 'blue')
        self.package = prepare_package(self.base, self.audio, self.srt,
                                       self.root/'portable package', is_shorts=True)

    @staticmethod
    def make_video(dest, audio, duration, color):
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
             f'color=c={color}:s=160x240:r=25', '-i', str(audio), '-t', str(duration),
             '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-b:a', '128k', str(dest)])

    def test_no_clip_preserves_base_and_is_not_marked_as_avatar(self):
        result = finish_package(self.package)
        self.assertEqual(sha(result), sha(self.base))
        publication = json.loads((self.package/'publication.json').read_text())
        self.assertFalse(publication['contains_synthetic_media'])
        self.assertFalse(publication['published'])

    def test_real_overlay_only_in_intro_and_continuous_audio(self):
        self.make_video(self.package/'intro.mp4', self.package/'intro.wav', 2.5, 'red')
        result = finish_package(self.package)
        self.assertAlmostEqual(float(probe(result)['format']['duration']), 10, delta=.1)
        for seconds, dominant in [(1, 0), (4, 2)]:
            frame = run(['ffmpeg', '-v', 'error', '-ss', str(seconds), '-i', str(result),
                         '-frames:v', '1', '-vf', 'crop=80:80:0:0', '-f', 'rawvideo',
                         '-pix_fmt', 'rgb24', '-'])
            mean = np.frombuffer(frame, dtype=np.uint8).reshape(-1, 3).mean(axis=0)
            self.assertEqual(int(mean.argmax()), dominant)
        def audio_hash(p):
            return run(['ffmpeg', '-v', 'error', '-i', str(p), '-map', '0:a',
                        '-c', 'copy', '-f', 'hash', '-'])
        self.assertEqual(audio_hash(self.base), audio_hash(result))
        publication = json.loads((self.package/'publication.json').read_text())
        self.assertTrue(publication['contains_synthetic_media'])
        self.assertEqual(len(publication['presenter_segments']), 1)

    def test_wrong_speech_and_changed_sources_rejected(self):
        wrong_audio = self.root/'wrong.wav'
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(self.audio), '-ss', '5',
             '-t', '2.5', str(wrong_audio)])
        clip = self.package/'intro.mp4'
        self.make_video(clip, wrong_audio, 2.5, 'red')
        with self.assertRaisesRegex(ValueError, 'speech mismatch'):
            finish_package(self.package)
        self.assertFalse((self.package/'final.mp4').exists())
        (self.package/'narration.srt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed since preparation'):
            finish_package(self.package)

    def test_manifest_cannot_expand_paid_scene_budget(self):
        manifest_path = self.package/'presenter.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['segments'][0]['end'] = 9
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Scene timings differ'):
            finish_package(self.package)

    def test_clip_cannot_be_stretched_or_looped(self):
        clip = self.package/'intro.mp4'
        self.make_video(clip, self.package/'intro.wav', 1, 'red')
        with self.assertRaisesRegex(ValueError, 'duration differs'):
            validate_clip(clip, self.package/'intro.wav', 2.5)

    def test_long_transition_appears_at_its_original_audio_time(self):
        audio = self.root/'long.wav'
        run(['ffmpeg', '-v', 'error', '-y', '-stream_loop', '-1', '-i', str(self.audio),
             '-t', '60', str(audio)])
        base = self.root/'long.mp4'
        self.make_video(base, audio, 60, 'blue')
        srt = self.root/'long.srt'
        srt.write_text('1\n00:00:00,000 --> 00:00:02,500\nOpening.\n\n'
                       '2\n00:00:02,500 --> 00:00:32,000\nFirst story.\n\n'
                       '3\n00:00:32,500 --> 00:00:34,500\nNext story.\n\n'
                       '4\n00:00:34,500 --> 00:00:59,500\nDetails.\n')
        package = prepare_package(base, audio, srt, self.root/'long package', is_shorts=False)
        self.make_video(package/'transition.mp4', package/'transition.wav', 2, 'green')
        result = finish_package(package)
        for seconds, dominant in [(1, 2), (33, 1), (36, 2)]:
            frame = run(['ffmpeg', '-v', 'error', '-ss', str(seconds), '-i', str(result),
                         '-frames:v', '1', '-vf', 'crop=80:80:0:0', '-f', 'rawvideo',
                         '-pix_fmt', 'rgb24', '-'])
            mean = np.frombuffer(frame, dtype=np.uint8).reshape(-1, 3).mean(axis=0)
            self.assertEqual(int(mean.argmax()), dominant)


if __name__ == '__main__':
    unittest.main()
