# scripts/extraction/tests/test_extraction_strategies.py

"""Unit tests for individual extraction strategies."""

import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
import fitz
import os
import tempfile
import shutil
import io
from pyswip import call

# Import strategy classes and BaseStrategy
from ..extraction_strategies.base_strategy import BaseExtractionStrategy
from ..extraction_strategies.standard_strategy import StandardExtractionStrategy
from ..extraction_strategies.alternate_colorspace_strategy import AlternateColorspaceExtractionStrategy
from ..extraction_strategies.compression_retry_strategy import CompressionRetryStrategy
from ..extraction_strategies.page_based_strategy import PageBasedExtractionStrategy

# Mock configuration
MOCK_CONFIG = {
    "min_width": 50,
    "min_height": 50,
    "dpi": 150, # Used by PageBasedStrategy
}

class TestExtractionStrategies(unittest.TestCase):

    def setUp(self):
        # Create mock PDF document and image info
        self.mock_doc = MagicMock(spec=fitz.Document)
        # img_info is typically (xref, s, w, h, bpc, cs, intent, format, filter, stream)
        self.mock_img_info = (10, 0, 100, 100, 8, fitz.csRGB, '', 'jpeg', 'dct', b'dummy_image_data')
        self.page_num = 1
        self.extraction_info = {}

        # Create dummy PIL Image objects for mocking return values
        self.dummy_image = Image.new('RGB', (100, 100), color = 'red')
        self.small_image = Image.new('RGB', (30, 30), color = 'blue') # Smaller than min size

    def tearDown(self):
        # Ensure any resources are cleaned up (PIL images might need closing if not garbage collected)
        self.dummy_image.close()
        self.small_image.close()

    # --- Helper Methods to mock PyMuPDF behavior ---

    def _mock_pixmap(self, image: Image.Image):
        """Mocks fitz.Pixmap creation from a PIL Image."""
        width, height = image.size
        mode = image.mode
        samples = image.tobytes()
        n = len(image.getbands())
        alpha = 1 if 'A' in mode else 0
        colorspace = fitz.csRGB if mode in ['RGB', 'RGBA'] else (fitz.csGRAY if mode == 'L' else None)

        mock_pix = MagicMock(spec=fitz.Pixmap)
        mock_pix.width = width
        mock_pix.height = height
        mock_pix.samples = samples
        mock_pix.n = n
        mock_pix.alpha = alpha
        mock_pix.colorspace = colorspace
        mock_pix.tobytes.return_value = samples # Add tobytes method
        return mock_pix

    def _mock_extract_image(self, image: Image.Image, ext: str):
        """Mocks fitz.Document.extract_image."""
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format=ext.upper())
        return {"ext": ext, "image": img_byte_arr.getvalue()}

    def _mock_page_render(self, page_idx: int, dpi: int = 150):
        """Mocks fitz.Page rendering."""
        # Create a simple mock page image
        img = Image.new('RGB', (dpi * 8 // 72, dpi * 10 // 72), color = 'gray') # Simulate A4 page size
        return self._mock_pixmap(img)


    # --- Tests for StandardExtractionStrategy ---

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_rgb(self, mock_pixmap):
        """Test successful standard extraction for RGB image."""
        mock_pix = self._mock_pixmap(self.dummy_image.convert('RGB'))
        mock_pixmap.return_value = mock_pix

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
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
        mock_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_cmyk(self, mock_pixmap):
        """Test successful standard extraction for CMYK image."""
        mock_cmyk_image = self.dummy_image.convert('CMYK')
        mock_pix = self._mock_pixmap(mock_cmyk_image)
        # Manually set n for CMYK mock
        mock_pix.n = 4
        mock_pixmap.return_value = mock_pix

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB') # Should be converted to RGB
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_cmyk_image.close() # Clean up

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_failure(self, mock_pixmap):
        """Test standard extraction failure."""
        mock_pixmap.side_effect = RuntimeError("Mock Pixmap error")

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertIn('Standard extraction failed', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        mock_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_too_small(self, mock_pixmap):
        """Test standard extraction resulting in an image too small."""
        mock_pix = self._mock_pixmap(self.small_image)
        mock_pixmap.return_value = mock_pix

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertIn('Image too small', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info) # Dimensions might not be added if size check fails early
        mock_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])


    # --- Tests for AlternateColorspaceExtractionStrategy ---

    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_success(self, mock_pixmap):
        """Test successful alternate colorspace extraction."""
        # Simulate an image that might need explicit conversion
        mock_pix = self._mock_pixmap(self.dummy_image.convert('P')) # Palette image
        mock_pix_rgb = self._mock_pixmap(self.dummy_image.convert('RGB')) # Mock the converted pixmap
        mock_pixmap.side_effect = [mock_pix, mock_pix_rgb] # First call creates paletted, second converts

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
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
        # Check calls: one to get original, one to get RGB conversion
        mock_pixmap.assert_has_calls([
             call(self.mock_doc, self.mock_img_info[0]),
             call(fitz.csRGB, mock_pix)
        ])
        mock_pix.close()
        mock_pix_rgb.close()


    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_failure(self, mock_pixmap):
        """Test alternate colorspace extraction failure."""
        mock_pixmap.side_effect = RuntimeError("Mock Pixmap error")

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertIn('Alternate colorspace extraction failed', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        mock_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_too_small(self, mock_pixmap):
        """Test alternate colorspace extraction resulting in an image too small."""
        mock_pix = self._mock_pixmap(self.small_image.convert('P'))
        mock_pix_rgb = self._mock_pixmap(self.small_image.convert('RGB'))
        mock_pixmap.side_effect = [mock_pix, mock_pix_rgb]

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertIn('Image too small', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info)
        mock_pixmap.assert_has_calls([
             call(self.mock_doc, self.mock_img_info[0]),
             call(fitz.csRGB, mock_pix)
        ])
        mock_pix.close()
        mock_pix_rgb.close()

    # --- Tests for CompressionRetryStrategy ---

    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    def test_compression_retry_extraction_success(self, mock_extract_image):
        """Test successful compression retry extraction."""
        mock_extract_image.return_value = self._mock_extract_image(self.dummy_image, 'jpeg')

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        # PIL might open it in a different mode, but conversion to RGB is attempted
        self.assertIn(extracted_img.mode, ['RGB', 'RGBA']) # Should be RGB or RGBA after conversion
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertIn(info['mode'], ['RGB', 'RGBA'])
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    def test_compression_retry_extraction_no_data(self, mock_extract_image):
        """Test compression retry extraction when extract_image returns no data."""
        mock_extract_image.return_value = None

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertIn('No image data in extract_image result', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    def test_compression_retry_extraction_invalid_data(self, mock_extract_image):
        """Test compression retry extraction with invalid image data."""
        mock_extract_image.return_value = {"ext": "jpeg", "image": b'invalid_image_data'} # Invalid JPEG data

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertIn('Alternate compression extraction failed', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    def test_compression_retry_extraction_too_small(self, mock_extract_image):
        """Test compression retry extraction resulting in an image too small."""
        mock_extract_image.return_value = self._mock_extract_image(self.small_image, 'png')

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertIn('Image too small', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info)
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])


    # --- Tests for PageBasedExtractionStrategy ---

    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_success(self, mock_matrix, mock_get_pixmap):
        """Test successful page-based extraction."""
        # Mock page object and get_pixmap
        mock_page = MagicMock(spec=fitz.Page)
        self.mock_doc.__getitem__.return_value = mock_page

        # Mock the rendered pixmap
        mock_rendered_image = Image.new('RGB', (200, 300), color='white') # Simulate a page render
        mock_pix = self._mock_pixmap(mock_rendered_image)
        mock_get_pixmap.return_value = mock_pix

        # Mock Matrix creation
        mock_matrix_instance = MagicMock(spec=fitz.Matrix)
        mock_matrix.return_value = mock_matrix_instance

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (200, 300)) # Should be size of the rendered page
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        self.assertEqual(info['dimensions'], '200x300')
        self.assertEqual(info['mode'], 'RGB')
        self.assertIn('warning', info) # Should have a warning about using whole page
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        # Check calls
        self.mock_doc.__getitem__.assert_called_once_with(self.page_num - 1)
        mock_matrix.assert_called_once_with(MOCK_CONFIG['dpi'] / 72.0, MOCK_CONFIG['dpi'] / 72.0)
        mock_get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)
        mock_pix.close() # Ensure mock pixmap is closed

    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_failure(self, mock_matrix, mock_get_pixmap):
        """Test page-based extraction failure."""
        mock_page = MagicMock(spec=fitz.Page)
        self.mock_doc.__getitem__.return_value = mock_page

        mock_get_pixmap.side_effect = RuntimeError("Mock rendering error")

        mock_matrix_instance = MagicMock(spec=fitz.Matrix)
        mock_matrix.return_value = mock_matrix_instance


        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        self.assertIn('Page-based extraction failed', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')

        self.mock_doc.__getitem__.assert_called_once_with(self.page_num - 1)
        mock_matrix.assert_called_once_with(MOCK_CONFIG['dpi'] / 72.0, MOCK_CONFIG['dpi'] / 72.0)
        mock_get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)

    def test_base_strategy_check_min_size_pass(self):
        """Test min size check passes."""
        strategy = BaseExtractionStrategy(MOCK_CONFIG) # Use BaseStrategy to test common method
        info = {}
        self.assertTrue(strategy._check_min_size(self.dummy_image, info))
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

    def test_base_strategy_check_min_size_fail(self):
        """Test min size check fails."""
        strategy = BaseExtractionStrategy(MOCK_CONFIG)
        info = {}
        self.assertFalse(strategy._check_min_size(self.small_image, info))
        self.assertIn('Image too small', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')


if __name__ == '__main__':
    unittest.main()