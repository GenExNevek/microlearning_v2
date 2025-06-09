# scripts/extraction/image_processing/tests/test_extraction_strategies/test_standard_strategy.py
import unittest
from unittest.mock import MagicMock, patch, call
from PIL import Image
import fitz # For fitz.csRGB etc.

from scripts.extraction.image_processing.extraction_strategies.standard_strategy import StandardExtractionStrategy
from ._test_helpers import BaseStrategyTestCase, MOCK_CONFIG, create_mock_pixmap_helper

class TestStandardExtractionStrategy(BaseStrategyTestCase):

    @patch('scripts.extraction.image_processing.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_rgb(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_fitz_pixmap_instance = create_mock_pixmap_helper(self.dummy_image.convert('RGB'))
        mock_fitz_pixmap_constructor.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap_constructor.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_cmyk(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_cmyk_image = self.dummy_image.convert('CMYK')
        mock_fitz_pixmap_instance = create_mock_pixmap_helper(mock_cmyk_image)
        mock_fitz_pixmap_constructor.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)
        
        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB') 
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB') 
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap_constructor.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_gray(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_gray_image = self.dummy_image.convert('L')
        mock_fitz_pixmap_instance = create_mock_pixmap_helper(mock_gray_image)
        mock_fitz_pixmap_constructor.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'L')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'L')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap_constructor.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_rgba(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_rgba_image = self.dummy_image.convert('RGBA') # Original dummy_image is RGB, convert it
        mock_fitz_pixmap_instance = create_mock_pixmap_helper(mock_rgba_image)
        # create_mock_pixmap_helper already sets n=4, alpha=1 for RGBA
        mock_fitz_pixmap_constructor.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGBA')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGBA')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap_constructor.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_too_small(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_fitz_pixmap_instance = create_mock_pixmap_helper(self.small_image.convert('RGB'))
        mock_fitz_pixmap_constructor.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertIn(f'Image too small: 30x30 (min: {MOCK_CONFIG["min_width"]}x{MOCK_CONFIG["min_height"]})', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        mock_fitz_pixmap_instance.close.assert_called_once()

    @patch('scripts.extraction.image_processing.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_failure(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_fitz_pixmap_constructor.side_effect = RuntimeError("Mock Pixmap error")

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertIn('Standard extraction failed for xref 10: Mock Pixmap error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        mock_fitz_pixmap_constructor.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

if __name__ == '__main__':
    unittest.main()