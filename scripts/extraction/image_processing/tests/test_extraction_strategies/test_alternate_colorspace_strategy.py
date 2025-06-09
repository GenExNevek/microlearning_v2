# scripts/extraction/image_processing/tests/test_extraction_strategies/test_alternate_colorspace_strategy.py
import unittest
from unittest.mock import MagicMock, patch, call
from PIL import Image
import fitz # For fitz.csRGB, fitz.Colorspace etc.

from scripts.extraction.image_processing.extraction_strategies.alternate_colorspace_strategy import AlternateColorspaceExtractionStrategy
from ._test_helpers import BaseStrategyTestCase, MOCK_CONFIG, create_mock_pixmap_helper

class TestAlternateColorspaceExtractionStrategy(BaseStrategyTestCase):

    @patch('scripts.extraction.image_processing.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_success_paletted(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_paletted_pixmap_instance = create_mock_pixmap_helper(self.paletted_image) # paletted_image is already 'P' mode
        
        mock_rgb_image = self.paletted_image.convert('RGB')
        mock_rgb_pixmap_instance = create_mock_pixmap_helper(mock_rgb_image)

        def pixmap_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == self.mock_doc: # Initial fitz.Pixmap(doc, xref)
                return mock_paletted_pixmap_instance
            # Conversion call: fitz.Pixmap(fitz.csRGB, pix) or fitz.Pixmap(fitz.csRGB, pix, alpha=...)
            elif len(args) >= 2 and isinstance(args[0], fitz.Colorspace):
                return mock_rgb_pixmap_instance
            raise ValueError(f"Unexpected call to Pixmap constructor: {args}, {kwargs}")


        mock_fitz_pixmap_constructor.side_effect = pixmap_side_effect

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        self.assertGreaterEqual(mock_fitz_pixmap_constructor.call_count, 2)
        mock_paletted_pixmap_instance.close.assert_called_once()
        mock_rgb_pixmap_instance.close.assert_called_once()
        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_success_rgba(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_rgba_pixmap_instance = create_mock_pixmap_helper(self.rgba_image) # self.rgba_image is already RGBA
        
        # The strategy will try to convert using fitz.csRGB with alpha=True
        mock_rgba_pixmap_converted_instance = create_mock_pixmap_helper(self.rgba_image) # Result should still be RGBA

        def pixmap_side_effect(*args, **kwargs):
             if len(args) == 2 and args[0] == self.mock_doc and args[1] == self.mock_img_info[0]:
                 return mock_rgba_pixmap_instance
             elif len(args) >= 2 and isinstance(args[0], fitz.Colorspace) and args[0] == fitz.csRGB and kwargs.get('alpha') is True:
                  return mock_rgba_pixmap_converted_instance
             # Fallback for other conversion attempts if needed, or raise error for unexpected
             elif len(args) >= 2 and isinstance(args[0], fitz.Colorspace) and args[0] == fitz.csRGB: # e.g. alpha=False attempt
                  return create_mock_pixmap_helper(self.rgba_image.convert("RGB")) # if it tried to remove alpha
             raise ValueError(f"Unexpected call to Pixmap constructor in RGBA test: {args}, {kwargs}")

        mock_fitz_pixmap_constructor.side_effect = pixmap_side_effect

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGBA')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGBA')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        self.assertGreaterEqual(mock_fitz_pixmap_constructor.call_count, 1) # At least initial call
        mock_rgba_pixmap_instance.close.assert_called_once()
        if mock_fitz_pixmap_constructor.call_count > 1: # If conversion was attempted and returned our mock
            mock_rgba_pixmap_converted_instance.close.assert_called_once()

        if extracted_img: extracted_img.close()

    @patch('scripts.extraction.image_processing.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_too_small(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        small_paletted_image = self.small_image.convert('P')
        mock_paletted_pixmap_instance = create_mock_pixmap_helper(small_paletted_image)
        
        mock_rgb_image = small_paletted_image.convert('RGB')
        mock_rgb_pixmap_instance = create_mock_pixmap_helper(mock_rgb_image)

        def pixmap_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == self.mock_doc:
                return mock_paletted_pixmap_instance
            elif len(args) >= 2 and isinstance(args[0], fitz.Colorspace):
                 return mock_rgb_pixmap_instance
            raise ValueError(f"Unexpected call to Pixmap constructor: {args}, {kwargs}")

        mock_fitz_pixmap_constructor.side_effect = pixmap_side_effect

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertIn(f'Image too small: 30x30 (min: {MOCK_CONFIG["min_width"]}x{MOCK_CONFIG["min_height"]})', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)

        self.assertGreaterEqual(mock_fitz_pixmap_constructor.call_count, 2)
        mock_paletted_pixmap_instance.close.assert_called_once()
        mock_rgb_pixmap_instance.close.assert_called_once()

    @patch('scripts.extraction.image_processing.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_failure(self, mock_fitz_pixmap_constructor: MagicMock) -> None:
        mock_fitz_pixmap_constructor.side_effect = RuntimeError("Mock Pixmap error")

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertIn('Alternate colorspace extraction failed for xref 10: Mock Pixmap error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        mock_fitz_pixmap_constructor.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

if __name__ == '__main__':
    unittest.main()