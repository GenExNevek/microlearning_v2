# scripts/extraction/tests/test_retry_coordinator.py

"""Unit tests for the RetryCoordinator."""

import unittest
from unittest.mock import MagicMock, patch 
from typing import Dict, Any

# Import the RetryCoordinator
from ..retry_coordinator import RetryCoordinator

# Mock configuration
MOCK_CONFIG = {
    "retry_failed_extractions": True,
    "max_extraction_retries": 3,
    # Include base config needed by strategies (min_width/height, dpi)
    "min_width": 50,
    "min_height": 50,
    "dpi": 150,
}

# Mock Strategy implementations (remain as blueprints for spec and self.strategies)
# Their actual extract methods won't be called in tests due to mocking.
class MockStrategyA:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self, pdf_document, img_info, page_num, extraction_info_details_dict):
        extraction_info_details_dict['dimensions'] = '100x100'
        extraction_info_details_dict['mode'] = 'RGB'
        mock_image = MagicMock()
        return mock_image, {'success': True, 'details': extraction_info_details_dict}


class MockStrategyB:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self, pdf_document, img_info, page_num, extraction_info_details_dict):
        extraction_info_details_dict['dimensions'] = '200x200'
        extraction_info_details_dict['mode'] = 'L'
        mock_image = MagicMock()
        return mock_image, {'success': True, 'details': extraction_info_details_dict}


class MockStrategyC:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self, pdf_document, img_info, page_num, extraction_info_details_dict):
        extraction_info_details_dict['dimensions'] = '300x300'
        extraction_info_details_dict['mode'] = 'CMYK'
        mock_image = MagicMock()
        return mock_image, {'success': True, 'details': extraction_info_details_dict}

# Path for patching these classes, assuming this file is scripts/extraction/tests/test_retry_coordinator.py
PATCH_PATH_PREFIX = "scripts.extraction.tests.test_retry_coordinator."

class TestRetryCoordinator(unittest.TestCase):

    def setUp(self):
        self.mock_pdf_document = MagicMock()
        self.mock_img_info = (10, 0, 100, 100, 8, 'RGB', '', 'jpeg', 'dct', b'data')
        self.page_num = 1
        self.img_index = 0
        self.initial_empty_extraction_info = {}

    @patch(f'{PATCH_PATH_PREFIX}MockStrategyC')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyB')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyA')
    def test_first_strategy_succeeds(self, PatchedMockStrategyA, PatchedMockStrategyB, PatchedMockStrategyC):
        """Test that coordinator stops after the first successful strategy."""
        mock_instance_a = MagicMock(spec=MockStrategyA)
        mock_instance_a.extract.return_value = (
            MagicMock(), 
            {'success': True, 'details': {'dimensions': '100x100', 'mode': 'RGB'}}
        )
        PatchedMockStrategyA.return_value = mock_instance_a

        mock_instance_b = MagicMock(spec=MockStrategyB) # This instance will be created
        PatchedMockStrategyB.return_value = mock_instance_b
        mock_instance_c = MagicMock(spec=MockStrategyC) # This instance will be created
        PatchedMockStrategyC.return_value = mock_instance_c

        strategies_for_coordinator = [
            (PatchedMockStrategyA, 'strategy_a'),
            (PatchedMockStrategyB, 'strategy_b'),
            (PatchedMockStrategyC, 'strategy_c'),
        ]

        coordinator = RetryCoordinator(strategies_for_coordinator, MOCK_CONFIG)
        extracted_image, extraction_info = coordinator.coordinate_extraction(
            self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, self.initial_empty_extraction_info
        )

        self.assertIsNotNone(extracted_image)
        self.assertTrue(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 1)
        self.assertEqual(len(extraction_info['attempts']), 1)
        self.assertEqual(extraction_info['attempts'][0]['strategy'], 'strategy_a')
        self.assertTrue(extraction_info['attempts'][0]['success'])
        self.assertEqual(extraction_info['extraction_method'], 'strategy_a') 
        self.assertEqual(extraction_info['dimensions'], '100x100')
        self.assertEqual(extraction_info['mode'], 'RGB')

        PatchedMockStrategyA.assert_called_once_with(MOCK_CONFIG) # Class A was instantiated
        mock_instance_a.extract.assert_called_once_with(
            self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY
        )
        
        # ---- MODIFIED ASSERTIONS ----
        PatchedMockStrategyB.assert_called_once_with(MOCK_CONFIG) # Class B was instantiated
        mock_instance_b.extract.assert_not_called()              # But its extract method was not
        PatchedMockStrategyC.assert_called_once_with(MOCK_CONFIG) # Class C was instantiated
        mock_instance_c.extract.assert_not_called()              # But its extract method was not
        # ---- END MODIFIED ASSERTIONS ----

    @patch(f'{PATCH_PATH_PREFIX}MockStrategyC')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyB')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyA')
    def test_second_strategy_succeeds_after_first_fails(self, PatchedMockStrategyA, PatchedMockStrategyB, PatchedMockStrategyC):
        """Test that coordinator moves to the next strategy if the first fails."""
        mock_instance_a = MagicMock(spec=MockStrategyA)
        mock_instance_a.extract.return_value = (None, {'success': False, 'error': 'A failed', 'details': {}})
        PatchedMockStrategyA.return_value = mock_instance_a

        mock_instance_b = MagicMock(spec=MockStrategyB)
        mock_instance_b.extract.return_value = (
            MagicMock(), 
            {'success': True, 'details': {'dimensions': '200x200', 'mode': 'L'}}
        )
        PatchedMockStrategyB.return_value = mock_instance_b

        mock_instance_c = MagicMock(spec=MockStrategyC) # This instance will be created
        PatchedMockStrategyC.return_value = mock_instance_c

        strategies_for_coordinator = [
            (PatchedMockStrategyA, 'strategy_a'),
            (PatchedMockStrategyB, 'strategy_b'),
            (PatchedMockStrategyC, 'strategy_c'),
        ]

        coordinator = RetryCoordinator(strategies_for_coordinator, MOCK_CONFIG)
        extracted_image, extraction_info = coordinator.coordinate_extraction(
            self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, self.initial_empty_extraction_info
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
        self.assertEqual(extraction_info['extraction_method'], 'strategy_b') 
        self.assertEqual(extraction_info['dimensions'], '200x200')
        self.assertEqual(extraction_info['mode'], 'L')

        PatchedMockStrategyA.assert_called_once_with(MOCK_CONFIG)
        mock_instance_a.extract.assert_called_once_with(self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY)
        PatchedMockStrategyB.assert_called_once_with(MOCK_CONFIG)
        mock_instance_b.extract.assert_called_once_with(self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY)
        
        # ---- MODIFIED ASSERTIONS ----
        PatchedMockStrategyC.assert_called_once_with(MOCK_CONFIG) # Class C was instantiated
        mock_instance_c.extract.assert_not_called()              # But its extract method was not
        # ---- END MODIFIED ASSERTIONS ----


    @patch(f'{PATCH_PATH_PREFIX}MockStrategyC')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyB')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyA')
    def test_all_strategies_fail(self, PatchedMockStrategyA, PatchedMockStrategyB, PatchedMockStrategyC):
        """Test that coordinator returns None if all strategies fail."""
        mock_instance_a = MagicMock(spec=MockStrategyA)
        mock_instance_a.extract.return_value = (None, {'success': False, 'error': 'A failed', 'details': {}})
        PatchedMockStrategyA.return_value = mock_instance_a

        mock_instance_b = MagicMock(spec=MockStrategyB)
        mock_instance_b.extract.return_value = (None, {'success': False, 'error': 'B failed', 'issue_type': 'size_issues', 'details': {}})
        PatchedMockStrategyB.return_value = mock_instance_b

        mock_instance_c = MagicMock(spec=MockStrategyC)
        mock_instance_c.extract.return_value = (None, {'success': False, 'error': 'C failed', 'issue_type': 'extraction_failed', 'details': {}})
        PatchedMockStrategyC.return_value = mock_instance_c

        strategies_for_coordinator = [
            (PatchedMockStrategyA, 'strategy_a'),
            (PatchedMockStrategyB, 'strategy_b'),
            (PatchedMockStrategyC, 'strategy_c'),
        ]
        
        # MOCK_CONFIG has retry_failed_extractions = True, so all strategies will be attempted if prior ones fail.
        # The break condition for retry_failed_extractions = False in RetryCoordinator will not trigger here.
        coordinator = RetryCoordinator(strategies_for_coordinator, MOCK_CONFIG)
        extracted_image, extraction_info = coordinator.coordinate_extraction(
            self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, self.initial_empty_extraction_info
        )

        self.assertIsNone(extracted_image) 
        self.assertFalse(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 3) # All 3 attempted
        self.assertEqual(len(extraction_info['attempts']), 3)


        self.assertEqual(extraction_info['attempts'][0]['strategy'], 'strategy_a')
        self.assertFalse(extraction_info['attempts'][0]['success'])
        self.assertEqual(extraction_info['attempts'][1]['strategy'], 'strategy_b')
        self.assertFalse(extraction_info['attempts'][1]['success'])
        self.assertEqual(extraction_info['attempts'][2]['strategy'], 'strategy_c')
        self.assertFalse(extraction_info['attempts'][2]['success'])

        self.assertIn('All 3 extraction attempts failed.', extraction_info['final_error'])
        self.assertEqual(extraction_info['issue_type'], 'extraction_failed') 

        PatchedMockStrategyA.assert_called_once_with(MOCK_CONFIG)
        mock_instance_a.extract.assert_called_once_with(self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY)
        PatchedMockStrategyB.assert_called_once_with(MOCK_CONFIG)
        mock_instance_b.extract.assert_called_once_with(self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY)
        PatchedMockStrategyC.assert_called_once_with(MOCK_CONFIG)
        mock_instance_c.extract.assert_called_once_with(self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY)

    @patch(f'{PATCH_PATH_PREFIX}MockStrategyC')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyB')
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyA')
    def test_retries_disabled(self, PatchedMockStrategyA, PatchedMockStrategyB, PatchedMockStrategyC):
        """Test that only the first strategy is tried if retries are disabled."""
        config_no_retry = MOCK_CONFIG.copy()
        config_no_retry['retry_failed_extractions'] = False # Key change for this test

        mock_instance_a = MagicMock(spec=MockStrategyA)
        
        the_extract_mock = MagicMock(return_value=(None, {'success': False, 'error': 'A failed', 'details': {}}))
        mock_instance_a.extract = the_extract_mock
        
        PatchedMockStrategyA.return_value = mock_instance_a

        mock_instance_b = MagicMock(spec=MockStrategyB) # This instance will be created
        PatchedMockStrategyB.return_value = mock_instance_b
        
        mock_instance_c = MagicMock(spec=MockStrategyC) # This instance will be created
        PatchedMockStrategyC.return_value = mock_instance_c
        
        strategies_for_coordinator = [
            (PatchedMockStrategyA, 'strategy_a'),
            (PatchedMockStrategyB, 'strategy_b'), 
            (PatchedMockStrategyC, 'strategy_c'), 
        ]

        coordinator = RetryCoordinator(strategies_for_coordinator, config_no_retry)
        extracted_image, extraction_info = coordinator.coordinate_extraction(
            self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, self.initial_empty_extraction_info
        )

        self.assertIsNone(extracted_image)
        self.assertFalse(extraction_info['success'])
        self.assertEqual(extraction_info['attempt_count'], 1) 
        self.assertEqual(len(extraction_info['attempts']), 1)
        self.assertEqual(extraction_info['attempts'][0]['strategy'], 'strategy_a')
        self.assertFalse(extraction_info['attempts'][0]['success'])

        PatchedMockStrategyA.assert_called_once_with(config_no_retry)
        the_extract_mock.assert_called_once_with(
            self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY
        )
        
        # ---- MODIFIED ASSERTIONS ----
        # Even though B and C are in the list, RetryCoordinator.__init__ instantiates them.
        # However, because retry_failed_extractions is False, the loop in coordinate_extraction
        # should break after the first strategy (A) is attempted.
        # So, B and C classes are instantiated, but their extract methods are not called.
        PatchedMockStrategyB.assert_called_once_with(config_no_retry) # Class B was instantiated
        mock_instance_b.extract.assert_not_called()                   # But its extract method was not
        PatchedMockStrategyC.assert_called_once_with(config_no_retry) # Class C was instantiated
        mock_instance_c.extract.assert_not_called()                   # But its extract method was not
        # ---- END MODIFIED ASSERTIONS ----


    @patch(f'{PATCH_PATH_PREFIX}MockStrategyB') 
    @patch(f'{PATCH_PATH_PREFIX}MockStrategyA') 
    def test_initial_extraction_info_is_merged(self, PatchedMockStrategyA, PatchedMockStrategyB):
        """Test that initial_extraction_info is included in the final result."""
        initial_info = {'global_image_counter': 5, 'custom_key': 'test'}

        mock_instance_a = MagicMock(spec=MockStrategyA)
        mock_instance_a.extract.return_value = (
            MagicMock(), 
            {'success': True, 'details': {'dimensions': '100x100', 'mode': 'RGB'}}
        )
        PatchedMockStrategyA.return_value = mock_instance_a

        mock_instance_b = MagicMock(spec=MockStrategyB) # This instance will be created
        PatchedMockStrategyB.return_value = mock_instance_b

        strategies_for_coordinator = [
            (PatchedMockStrategyA, 'strategy_a'),
            (PatchedMockStrategyB, 'strategy_b'),
        ]
        
        coordinator = RetryCoordinator(strategies_for_coordinator, MOCK_CONFIG) 
        extracted_image, extraction_info = coordinator.coordinate_extraction(
            self.mock_pdf_document, self.mock_img_info, self.page_num, self.img_index, initial_info
        )

        self.assertIsNotNone(extracted_image)
        self.assertTrue(extraction_info['success'])
        self.assertEqual(extraction_info['global_image_counter'], 5)
        self.assertEqual(extraction_info['custom_key'], 'test')
        self.assertEqual(extraction_info['xref'], self.mock_img_info[0])
        self.assertEqual(extraction_info['page'], self.page_num)
        self.assertEqual(extraction_info['index_on_page'], self.img_index)
        self.assertEqual(extraction_info['extraction_method'], 'strategy_a') 
        self.assertEqual(extraction_info['dimensions'], '100x100')
        self.assertEqual(extraction_info['mode'], 'RGB')

        PatchedMockStrategyA.assert_called_once_with(MOCK_CONFIG)
        mock_instance_a.extract.assert_called_once_with(
            self.mock_pdf_document, self.mock_img_info, self.page_num, unittest.mock.ANY
        )
        
        # ---- MODIFIED ASSERTIONS ----
        PatchedMockStrategyB.assert_called_once_with(MOCK_CONFIG) # Class B was instantiated
        mock_instance_b.extract.assert_not_called()              # But its extract method was not
        # ---- END MODIFIED ASSERTIONS ----

if __name__ == '__main__':
    unittest.main()