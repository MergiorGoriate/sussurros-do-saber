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

    def test_persistent_overlength_gets_targeted_summary(self):
        from copy import deepcopy

        original = {'claims': [{'evidence': 'As plantas utilizam luz na fotossíntese.'}],
                    'slides': [{'heading': 'Fotossíntese', 'body': 'x' * 241, 'claim_ids': [0]}],
                    'layout': 'balanced'}
        corrected = deepcopy(original)
        summary = 'A luz fornece energia à fotossíntese.'
        with patch.object(ai, 'chat', side_effect=[original, corrected, {'texts': [summary]}]) as chat:
            result = ai.generate({'body': original['claims'][0]['evidence']}, 'instagram', 'infographic')
        self.assertEqual(chat.call_count, 3)
        self.assertEqual(result['slides'], [
            {'heading': 'Fotossíntese', 'body': summary, 'claim_ids': [0]}])
        self.assertEqual(result['claims'], original['claims'])
        self.assertEqual(result['layout'], original['layout'])
        self.assertEqual(chat.call_args.args[1]['fields'][0]['maximum'], 240)

    def test_invalid_summary_stops_after_one_attempt(self):
        draft = {'slides': [{'heading': 'Fotossíntese', 'body': 'x' * 241, 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', side_effect=[draft, draft, {'texts': ['x' * 241]}]) as chat:
            with self.assertRaisesRegex(ai.GenerationError, '240 caracteres'):
                ai.generate({}, 'instagram', 'infographic')
        self.assertEqual(chat.call_count, 3)

    def test_overlength_summary_reuses_linked_claim_with_literal_support(self):
        evidence = 'As plantas utilizam luz na fotossíntese.'
        claim = {'text': 'As plantas usam luz na fotossíntese.', 'evidence': evidence}
        draft = {'claims': [
            {'text': 'Afirmação alheia ao slide.', 'evidence': evidence},
            {'text': 'Afirmação sem trecho literal.', 'evidence': 'Trecho inexistente no artigo.'},
            claim,
        ], 'slides': [{'heading': 'Fotossíntese', 'body': 'x' * 241, 'claim_ids': [1, 2]}]}
        with patch.object(ai, 'chat', side_effect=[draft, draft, {'texts': ['x' * 241]}]) as chat:
            result = ai.generate({'body': evidence}, 'instagram', 'infographic')
        self.assertEqual(result['slides'][0]['body'], claim['text'])
        self.assertEqual(result['slides'][0]['claim_ids'], [1, 2])
        self.assertEqual(chat.call_count, 3)
