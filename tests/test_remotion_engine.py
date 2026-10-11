import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remotion_engine import RemotionVideoEngine, read_words


class RemotionInputTests(unittest.TestCase):
    def test_measured_words_and_invalid_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'words.srt'
            path.write_text('1\n00:00:00,000 --> 00:00:00,500\nFirst\n\n'
                            '2\n00:00:00,650 --> 00:00:01,100\nsecond\n')
            self.assertEqual(read_words(path), [
                {'start': 0, 'end': .5, 'text': 'First'},
                {'start': .65, 'end': 1.1, 'text': 'second'},
            ])
            path.write_text('1\n00:00:00,000 --> 00:00:00,500\nFirst\n\n'
                            '2\n00:00:00,400 --> 00:00:01,100\nsecond\n')
            with self.assertRaises(ValueError):
                read_words(path)

    def test_invalid_real_chart_stops_before_render(self):
        engine = RemotionVideoEngine()
        with patch.object(engine, '_probe_duration', return_value=10), \
             patch('remotion_engine.subprocess.run') as render:
            with self.assertRaisesRegex(RuntimeError, 'Invalid intraday chart'):
                engine.render_video('voice.mp3', 'words.srt', 'out.mp4',
                                    title='Test', ticker='TEST', change_pct='1',
                                    intraday=[{'open': 10, 'close': 10},
                                              {'open': 10, 'close': float('nan')}])
            render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
