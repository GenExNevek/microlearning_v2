# scripts/extraction/image_processing/tests/test_extraction_strategies/test_page_based_strategy.py
import unittest
from unittest.mock import MagicMock, patch, call
from PIL import Image
import fitz # For fitz.Matrix

from scripts.extraction.image_processing.extraction_strategies.page_based_strategy import PageBasedExtractionStrategy
from ._test_helpers import BaseStrategyTestCase, MOCK_CONFIG, create_mock_rendered_pixmap_helper

class TestPageBasedExtractionStrategy(BaseStrategyTestCase):

    @patch('scripts.extraction.image_processing.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_success(self, mock_fitz_matrix_constructor: MagicMock) -> None:
        # self.mock_doc and self.mock_page are set up in BaseStrategyTestCase
        mock_rendered_pixmap_instance = create_mock_rendered_pixmap_helper(width=200, height=300, mode='RGB')
        self.mock_page.get_pixmap.return_value = mock_rendered_pixmap_instance

        mock_matrix_instance = MagicMock()
        mock_fitz_matrix_constructor.return_value = mock_matrix_instance

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (200, 300))
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        self.assertEqual(info['dimensions'], '200x300')
        self.assertEqual(info['mode'], 'RGB')
        self.assertIn('warning', info)
        self.assertIn('whole page rendering', info['warning'])
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        expected_zoom = MOCK_CONFIG['dpi'] / 72.0
        mock_fitz_matrix_constructor.assert_called_once_with(expected_zoom, expected_zoom)
        self.mock_page.get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)
        mock_rendered_pixmap_instance.close.assert_called_once()
        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_failure_rendering(self, mock_fitz_matrix_constructor: MagicMock) -> None:
        self.mock_page.get_pixmap.side_effect = RuntimeError("Mock rendering error")

        mock_matrix_instance = MagicMock()
        mock_fitz_matrix_constructor.return_value = mock_matrix_instance

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        self.assertIn(f'Page-based extraction failed for page {self.page_num} during pixmap rendering: Mock rendering error', info['error'])
        self.assertEqual(info['issue_type'], 'rendering_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.assertNotIn('warning', info)

        expected_zoom = MOCK_CONFIG['dpi'] / 72.0
        mock_fitz_matrix_constructor.assert_called_once_with(expected_zoom, expected_zoom)
        self.mock_page.get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)

    @patch('scripts.extraction.image_processing.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_invalid_page_num(self, mock_fitz_matrix_constructor: MagicMock) -> None:
        self.mock_doc.__len__.return_value = 0 # Doc has 0 pages

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        # page_num is 1 (0-indexed would be 0)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        # Page index is page_num - 1
        self.assertIn(f'Page index {self.page_num - 1} requested (corresponds to page {self.page_num}), but document only has 0 pages (0-0).', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.assertNotIn('warning', info)

        mock_fitz_matrix_constructor.assert_not_called()
        self.mock_page.get_pixmap.assert_not_called()
        self.mock_doc.__getitem__.assert_not_called() # Should fail before trying to get item
        self.mock_doc.__len__.assert_called_once()


if __name__ == '__main__':
    unittest.main()