import unittest
from unittest.mock import patch
import dissemination_ai as ai


class SlideGenerationTests(unittest.TestCase):
    def test_valid_single_slide_does_not_repeat_call(self):
        payload = {'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', return_value=payload) as chat:
            self.assertEqual(ai.generate({}, 'facebook', 'curiosity'), payload)
            self.assertEqual(chat.call_count, 1)

    def test_invalid_slide_count_gets_one_correction(self):
        first, corrected = {'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}, {'heading': 'Outro título', 'body': 'Outro texto', 'claim_ids': [0]}]}, {'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', side_effect=[first, corrected]) as chat:
            self.assertEqual(ai.generate({}, 'facebook', 'infographic'), corrected)
            self.assertEqual(chat.call_count, 2)
            self.assertEqual(chat.call_args.args[1]['previous_material'], first)

    def test_carousel_accepts_three_to_five_slides(self):
        for count in (3, 4, 5):
            with patch.object(ai, 'chat', return_value={'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}] * count}) as chat:
                ai.generate({}, 'instagram', 'carousel')
                self.assertEqual(chat.call_count, 1)

    def test_still_invalid_result_is_returned_to_existing_validator(self):
        with patch.object(ai, 'chat', return_value={'slides': []}) as chat:
            self.assertEqual(ai.generate({}, 'facebook', 'text'), {'slides': []})
            self.assertEqual(chat.call_count, 2)
