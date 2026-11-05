import os
import unittest
from unittest.mock import Mock, patch

import requests
import dissemination_ai as ai


SETTINGS = dict(OPENAI_API_KEY='test-only', DISSEMINATION_TEXT_MODEL='fixture',
    DISSEMINATION_REVIEW_MODEL='fixture', DISSEMINATION_IMAGE_MODEL='fixture',
    DISSEMINATION_JOB_UNITS='10', DISSEMINATION_DAILY_UNITS='100')


class DiagnosticsTests(unittest.TestCase):
    def test_text_does_not_require_image_model(self):
        with patch.dict(os.environ, SETTINGS, clear=True):
            del os.environ['DISSEMINATION_IMAGE_MODEL']
            self.assertTrue(ai.configured(require_images=False))
            self.assertFalse(ai.configured())
            self.assertIn('DISSEMINATION_IMAGE_MODEL', ' '.join(ai.configuration_issues()))

    def test_invalid_limits_are_not_reported_as_ready(self):
        for value in ('', 'zero', '0', '-1', '1000001'):
            with self.subTest(value=value), patch.dict(os.environ, {**SETTINGS,
                    'DISSEMINATION_DAILY_JOBS': value}, clear=True):
                self.assertFalse(ai.configured())

    def test_job_reservation_cannot_exceed_daily_budget(self):
        with patch.dict(os.environ, {**SETTINGS, 'DISSEMINATION_JOB_UNITS': '101'}, clear=True):
            self.assertFalse(ai.configured())

    def test_no_secret_values_in_configuration_errors(self):
        with patch.dict(os.environ, {**SETTINGS, 'DISSEMINATION_DAILY_UNITS': 'private-value'}, clear=True):
            self.assertNotIn('private-value', ' '.join(ai.configuration_issues()))

    def test_provider_failures_are_distinct_and_sanitized(self):
        messages = []
        for status in (400, 401, 403, 404, 429, 503, 302):
            response = Mock(status_code=status, text='private-provider-body')
            with self.subTest(status=status), patch.dict(os.environ, SETTINGS, clear=True), \
                    patch.object(ai.requests, 'post', return_value=response) as post:
                with self.assertRaises(ai.GenerationError) as error:
                    ai.api('chat/completions', {})
                message = str(error.exception)
                self.assertNotIn('private-provider-body', message)
                self.assertNotIn('test-only', message)
                if status < 500 and status != 302:
                    self.assertIn(str(status), message)
                messages.append(message)
                response.json.assert_not_called()
                self.assertFalse(post.call_args.kwargs['allow_redirects'])
                post.assert_called_once()
        self.assertEqual(len(set(messages)), len(messages))

    def test_timeout_is_not_retried(self):
        with patch.dict(os.environ, SETTINGS, clear=True), \
                patch.object(ai.requests, 'post', side_effect=requests.Timeout) as post:
            with self.assertRaisesRegex(ai.GenerationError, 'tempo de resposta'):
                ai.api('images/generations', {})
            post.assert_called_once()

    def test_api_requires_key_before_network_call(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(ai.requests, 'post') as post:
            with self.assertRaisesRegex(ai.GenerationError, 'OPENAI_API_KEY'):
                ai.api('chat/completions', {})
            post.assert_not_called()

    def test_missing_evidence_gets_one_bounded_correction(self):
        evidence = 'As plantas utilizam luz na fotossíntese.'
        bad = {'claims': [{'text': 'Afirmação', 'evidence': 'Uma paráfrase que não está no artigo.'}], 'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}]}
        good = {'claims': [{'text': 'Afirmação', 'evidence': evidence}], 'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', side_effect=[bad, good]) as chat:
            self.assertEqual(ai.generate({'body': evidence}, 'facebook', 'text'), good)
            self.assertEqual(chat.call_count, 2)
            self.assertIn('trecho literal', chat.call_args.args[0])

    def test_slide_and_evidence_errors_share_one_retry(self):
        bad = {'claims': [{'evidence': 'not in source'}], 'slides': []}
        with patch.object(ai, 'chat', return_value=bad) as chat:
            self.assertEqual(ai.generate({'body': 'Texto do artigo.'}, 'facebook', 'text'), bad)
            self.assertEqual(chat.call_count, 2)

    def test_literal_evidence_does_not_trigger_correction(self):
        evidence = 'As plantas utilizam luz na fotossíntese.'
        payload = {'claims': [{'evidence': evidence}], 'slides': [{'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', return_value=payload) as chat:
            ai.generate({'body': evidence}, 'facebook', 'text')
            chat.assert_called_once()

    def test_overlong_slide_gets_one_bounded_correction(self):
        evidence = 'As plantas utilizam luz na fotossíntese.'
        for key, maximum in (('heading', 70), ('body', 240)):
            good = {'claims': [{'evidence': evidence}], 'slides': [
                {'heading': 'Título', 'body': 'Texto breve', 'claim_ids': [0]}]}
            import copy
            bad = copy.deepcopy(good)
            bad['slides'][0][key] = 'x' * (maximum + 1)
            with self.subTest(key=key), patch.object(ai, 'chat', side_effect=[bad, good]) as chat:
                self.assertEqual(ai.generate({'body': evidence}, 'facebook', 'curiosity'), good)
                self.assertEqual(chat.call_count, 2)
                self.assertIn(f'no máximo {maximum} caracteres', chat.call_args.args[0])

    def test_slide_text_and_evidence_share_single_retry(self):
        payload = {'claims': [{'evidence': 'Ausente'}], 'slides': [
            {'heading': 'x' * 71, 'body': 'x' * 241, 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', return_value=payload) as chat:
            self.assertEqual(ai.generate({'body': 'Texto original do artigo.'}, 'facebook', 'curiosity'), payload)
            self.assertEqual(chat.call_count, 2)

    def test_slide_text_limits_accept_exact_boundary(self):
        evidence = 'As plantas utilizam luz na fotossíntese.'
        payload = {'claims': [{'evidence': evidence}], 'slides': [
            {'heading': 'x' * 70, 'body': 'x' * 240, 'claim_ids': [0]}]}
        with patch.object(ai, 'chat', return_value=payload) as chat:
            ai.generate({'body': evidence}, 'facebook', 'curiosity')
            chat.assert_called_once()


if __name__ == '__main__':
    unittest.main()
