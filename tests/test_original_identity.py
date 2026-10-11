import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from config import VOICE_TAG
from editorial_policy import validate_editorial_script
from learning_engine import _measure_narration
from thumbnail_design import create_story_thumbnail


class OriginalIdentityTests(unittest.TestCase):
    def test_story_families_are_visually_distinct_and_keep_real_chart(self):
        candles = [{'close': 100 + i * .2 + (i % 5)} for i in range(20)]
        with tempfile.TemporaryDirectory() as directory:
            images = []
            for franchise in ('congress_trade', 'earnings_shock', 'analyst_shock', 'market_close'):
                path = Path(directory) / f'{franchise}.png'
                create_story_thumbnail(
                    ticker='TEST', change_pct='+2.50', hook_words='SOURCE DATE MATTERS',
                    intraday=candles, output_path=str(path), franchise=franchise,
                    hero_number='$500K', hero_label='REPORTED AMOUNT')
                with Image.open(path) as image:
                    self.assertEqual(image.size, (1280, 720))
                    images.append(image.copy())
            for a, b in zip(images, images[1:]):
                self.assertIsNotNone(ImageChops.difference(a, b).getbbox())
            with self.assertRaises(ValueError):
                create_story_thumbnail(ticker='TEST', change_pct='+2.50',
                                       hook_words='SOURCE DATE MATTERS', intraday=[],
                                       output_path=str(Path(directory) / 'invalid.png'),
                                       franchise='earnings_shock')

    def test_old_voice_does_not_calibrate_new_voice(self):
        old = {'machine': {'w': '70', 'v': '11l'}, 'duration_s': 35}
        self.assertIsNone(_measure_narration([old] * 5))
        current = {'machine': {'w': '84', 'v': VOICE_TAG}, 'duration_s': 35}
        result = _measure_narration([old] * 5 + [current] * 3)
        self.assertEqual(result['engine'], VOICE_TAG)
        self.assertEqual(result['samples'], 3)

    def test_cover_hook_gets_same_known_claim_checks_as_title(self):
        story = {'ticker': 'MSFT', 'franchise': 'congress_trade'}
        script = {'title': 'MSFT trade disclosed', 'full_script': 'The trade was disclosed.',
                  'thumbnail_hook': 'HIDDEN FOR 32 DAYS'}
        self.assertTrue(validate_editorial_script(script, story))


if __name__ == '__main__':
    unittest.main()
