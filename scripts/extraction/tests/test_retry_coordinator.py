# scripts/extraction/tests/test_retry_coordinator.py

"""Unit tests for the RetryCoordinator."""

import unittest
from unittest.mock import MagicMock, patch, call
import time
from typing import Dict, Any

# Import the RetryCoordinator and BaseStrategy
from ..retry_coordinator import RetryCoordinator
from ..extraction_strategies.base_strategy import BaseExtractionStrategy

# Mock configuration
MOCK_CONFIG = {
    "retry_failed_extractions": True,
    "max_extraction_retries": 3,
    # Include base config needed by strategies (min_width/height, dpi)
    "min_width": 50,
    "min_height": 50,
    "dpi": 150,
}

# Mock Strategy implementations
class MockStrategyA(BaseExtractionStrategy):
    def extract(self, pdf_document, img_info, page_num, extraction_info):
        extraction_info['strategy'] = 'A'
        # Default to success, can be overridden for specific tests
        extraction_info['success'] = True
        extraction_info['details']['dimensions'] = '100x100'
        extraction_info['details']['mode'] = 'RGB'
        mock_image = MagicMock() # Return a mock image
        return mock_image, extraction_info

class MockStrategyB(BaseExtractionStrategy):
    def extract(self, pdf_document, img_info, page_num, extraction_info):
        extraction_info['strategy'] = 'B'
        extraction_info['success'] = True
        extraction_info['details']['dimensions'] = '200x200'
        extraction_info['details']['mode'] = 'L'
        mock_image = MagicMock()
        return mock_image, extraction_info

class MockStrategyC(BaseExtractionStrategy):
    def extract(self, pdf_document, img_info, page_num, extraction_info):
        extraction_info['strategy'] = 'C'
        extraction_info['success'] = True
        extraction_info['details']['dimensions'] = '300x300'
        extraction_info['details']['mode'] = 'CMYK'
        mock_image = MagicMock()
        return mock_image, extraction_info


class TestRetryCoordinator(unittest.TestCase):

    def setUp(self):
        # Mock dependencies for the coordinator
        self.mock_pdf_document = MagicMock()
        self.mock_img_info = (10, 0, 100, 100, 8, 'RGB', '', 'jpeg', 'dct', b'data')
        self.page_num = 1
        self.img_index = 0

        # Define the sequence of strategies to use in the coordinator
        self.strategies = [
            (MockStrategyA, 'strategy_a'),
            (MockStrategyB, 'strategy_b'),
            (MockStrategyC, 'strategy_c'),
        ]

    def test_first_strategy_succeeds(self):
        """Test that coordinator stops after the first successful strategy."""
        # Configure StrategyA to succeed, B and C don't matter
        mock_strategy_a_instance = MockStrategyA(MOCK_CONFIG)
        mock_strategy_a_instance.extract = MagicMock(return_value=(MagicMock(), {'success': True, 'details': {'dimensions': '100x100'}}))

        mock_strategy_b_instance = MockStrategyB(MOCK_CONFIG)
        mock_strategy_b_instance.extract = MagicMock() # Will not be called

        mock_strategy_c_instance = MockStrategyC(MOCK_CONFIG)
        mock_strategy_c_instance.extract = MagicMock() # Will not be called

        # Patch the strategy instantiation within the coordinator
        with patch.object(MockStrategyA, '__new__', return_value=mock_strategy_a_instance), \
             patch.object(MockStrategyB, '__new__', return_value=mock_strategy_b_instance), \
             patch.object(MockStrategyC, '__new__', return_value=mock_strategy_c_instance):

            coordinator = RetryCoordinator(self.strategies, MOCK_CONFIG)
            extracted_image, extraction_info = coordinator.coordinate_extraction(
                self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, {}
            )

        self.assertIsNotNone(extracted_image)
        self.assertTrue(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 1)
        self.assertEqual(len(extraction_info['attempts']), 1)
        self.assertEqual(extraction_info['attempts'][0]['strategy'], 'strategy_a')
        self.assertTrue(extraction_info['attempts'][0]['success'])
        self.assertEqual(extraction_info['extraction_method'], 'strategy_a') # Final method should be the successful one
        self.assertEqual(extraction_info['dimensions'], '100x100') # Final dimensions from success

        mock_strategy_a_instance.extract.assert_called_once()
        mock_strategy_b_instance.extract.assert_not_called()
        mock_strategy_c_instance.extract.assert_not_called()


    def test_second_strategy_succeeds_after_first_fails(self):
        """Test that coordinator moves to the next strategy if the first fails."""
        # Configure StrategyA to fail, B to succeed, C doesn't matter
        mock_strategy_a_instance = MockStrategyA(MOCK_CONFIG)
        mock_strategy_a_instance.extract = MagicMock(return_value=(None, {'success': False, 'error': 'A failed'}))

        mock_strategy_b_instance = MockStrategyB(MOCK_CONFIG)
        mock_strategy_b_instance.extract = MagicMock(return_value=(MagicMock(), {'success': True, 'details': {'dimensions': '200x200'}}))

        mock_strategy_c_instance = MockStrategyC(MOCK_CONFIG)
        mock_strategy_c_instance.extract = MagicMock() # Will not be called

        with patch.object(MockStrategyA, '__new__', return_value=mock_strategy_a_instance), \
             patch.object(MockStrategyB, '__new__', return_value=mock_strategy_b_instance), \
             patch.object(MockStrategyC, '__new__', return_value=mock_strategy_c_instance):

            coordinator = RetryCoordinator(self.strategies, MOCK_CONFIG)
            extracted_image, extraction_info = coordinator.coordinate_extraction(
                self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, {}
            )

        self.assertIsNotNone(extracted_image)
        self.assertTrue(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 2)
        self.assertEqual(len(extraction_info['attempts']), 2)

        self.assertEqual(extraction_info['attempts'][0]['strategy'], 'strategy_a')
        self.assertFalse(extraction_info['attempts'][0]['success'])
        self.assertIn('A failed', extraction_info['attempts'][0]['error'])

        self.assertEqual(extraction_info['attempts'][1]['strategy'], 'strategy_b')
        self.assertTrue(extraction_info['attempts'][1]['success'])
        self.assertEqual(extraction_info['extraction_method'], 'strategy_b') # Final method should be the successful one
        self.assertEqual(extraction_info['dimensions'], '200x200') # Final dimensions from success

        mock_strategy_a_instance.extract.assert_called_once()
        mock_strategy_b_instance.extract.assert_called_once()
        mock_strategy_c_instance.extract.assert_not_called()

    def test_all_strategies_fail(self):
        """Test that coordinator returns None if all strategies fail."""
        # Configure all strategies to fail
        mock_strategy_a_instance = MockStrategyA(MOCK_CONFIG)
        mock_strategy_a_instance.extract = MagicMock(return_value=(None, {'success': False, 'error': 'A failed'}))

        mock_strategy_b_instance = MockStrategyB(MOCK_CONFIG)
        mock_strategy_b_instance.extract = MagicMock(return_value=(None, {'success': False, 'error': 'B failed', 'issue_type': 'size_issues'})) # Simulate different issue type

        mock_strategy_c_instance = MockStrategyC(MOCK_CONFIG)
        mock_strategy_c_instance.extract = MagicMock(return_value=(None, {'success': False, 'error': 'C failed', 'issue_type': 'extraction_failed'}))


        with patch.object(MockStrategyA, '__new__', return_value=mock_strategy_a_instance), \
             patch.object(MockStrategyB, '__new__', return_value=mock_strategy_b_instance), \
             patch.object(MockStrategyC, '__new__', return_value=mock_strategy_c_instance):

            coordinator = RetryCoordinator(self.strategies, MOCK_CONFIG)
            extracted_image, extraction_info = coordinator.coordinate_extraction(
                self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, {}
            )

        self.assertIsNone(extracted_image)
        self.assertFalse(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 3)
        self.assertEqual(len(extraction_info['attempts']), 3)

        self.assertFalse(extraction_info['attempts'][0]['success'])
        self.assertFalse(extraction_info['attempts'][1]['success'])
        self.assertFalse(extraction_info['attempts'][2]['success'])

        self.assertIn('All 3 extraction attempts failed.', extraction_info['final_error'])
        # The final issue_type should be the one from the last failed attempt
        self.assertEqual(extraction_info['issue_type'], 'extraction_failed')

        mock_strategy_a_instance.extract.assert_called_once()
        mock_strategy_b_instance.extract.assert_called_once()
        mock_strategy_c_instance.extract.assert_called_once()

    def test_retries_disabled(self):
        """Test that only the first strategy is tried if retries are disabled."""
        config_no_retry = MOCK_CONFIG.copy()
        config_no_retry['retry_failed_extractions'] = False

        # Configure StrategyA to fail, B and C won't be reached
        mock_strategy_a_instance = MockStrategyA(config_no_retry)
        mock_strategy_a_instance.extract = MagicMock(return_value=(None, {'success': False, 'error': 'A failed'}))

        mock_strategy_b_instance = MockStrategyB(config_no_retry)
        mock_strategy_b_instance.extract = MagicMock()

        mock_strategy_c_instance = MockStrategyC(config_no_retry)
        mock_strategy_c_instance.extract = MagicMock()

        with patch.object(MockStrategyA, '__new__', return_value=mock_strategy_a_instance), \
             patch.object(MockStrategyB, '__new__', return_value=mock_strategy_b_instance), \
             patch.object(MockStrategyC, '__new__', return_value=mock_strategy_c_instance):

            coordinator = RetryCoordinator(self.strategies, config_no_retry)
            extracted_image, extraction_info = coordinator.coordinate_extraction(
                self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, {}
            )

        self.assertIsNone(extracted_image)
        self.assertFalse(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 1) # Only one attempt recorded
        self.assertEqual(len(extraction_info['attempts']), 1)
        self.assertEqual(extraction_info['attempts'][0]['strategy'], 'strategy_a')
        self.assertFalse(extraction_info['attempts'][0]['success'])

        mock_strategy_a_instance.extract.assert_called_once()
        mock_strategy_b_instance.extract.assert_not_called()
        mock_strategy_c_instance.extract.assert_not_called()

    def test_initial_extraction_info_is_merged(self):
        """Test that initial_extraction_info is included in the final result."""
        initial_info = {'global_image_counter': 5, 'custom_key': 'test'}

        # Configure StrategyA to succeed
        mock_strategy_a_instance = MockStrategyA(MOCK_CONFIG)
        mock_strategy_a_instance.extract = MagicMock(return_value=(MagicMock(), {'success': True, 'details': {'dimensions': '100x100'}}))

        mock_strategy_b_instance = MockStrategyB(MOCK_CONFIG) # Won't be called
        mock_strategy_b_instance.extract = MagicMock()


        with patch.object(MockStrategyA, '__new__', return_value=mock_strategy_a_instance), \
             patch.object(MockStrategyB, '__new__', return_value=mock_strategy_b_instance): # Only need to patch strategies that *could* be instantiated

            # Use only first two strategies to simplify
            coordinator = RetryCoordinator(self.strategies[:2], MOCK_CONFIG)
            extracted_image, extraction_info = coordinator.coordinate_extraction(
                self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, initial_info
            )

        self.assertIsNotNone(extracted_image)
        self.assertTrue(extraction_info['success'])
        self.assertEqual(extraction_info['global_image_counter'], 5)
        self.assertEqual(extraction_info['custom_key'], 'test')
        self.assertEqual(extraction_info['xref'], self.mock_img_info[0]) # Base info should still be there
        self.assertEqual(extraction_info['page'], self.page_num)
        self.assertEqual(extraction_info['index_on_page'], self.img_index)


if __name__ == '__main__':
    unittest.main()