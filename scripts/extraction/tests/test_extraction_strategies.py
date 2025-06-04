
# scripts/extraction/tests/test_extraction_strategies.py

"""Unit tests for individual extraction strategies."""

import unittest
from unittest.mock import MagicMock, patch, call, ANY
from PIL import Image
import fitz
import os
import tempfile
import shutil
import io
# import call # Remove unused import from pyswip # This was already removed in the previous fix, confirming it's not needed

# Import strategy classes and BaseStrategy
from ..extraction_strategies.base_strategy import BaseExtractionStrategy
from ..extraction_strategies.standard_strategy import StandardExtractionStrategy
from ..extraction_strategies.alternate_colorspace_strategy import AlternateColorspaceExtractionStrategy
from ..extraction_strategies.compression_retry_strategy import CompressionRetryStrategy
from ..extraction_strategies.page_based_strategy import PageBasedExtractionStrategy

# Import ImageIssueType for assertions
# Adjust import path based on project structure
# Assuming scripts/extraction/tests is sibling to scripts/utils
from scripts.utils.image_validation import ImageIssueType


# Import types for type hints
from typing import Optional, Dict, Any, Tuple, Type


# Mock configuration
MOCK_CONFIG = {
    "min_width": 50,
    "min_height": 50,
    "dpi": 150, # Used by PageBasedStrategy
}

# Concrete mock class for testing BaseExtractionStrategy methods
class ConcreteMockStrategy(BaseExtractionStrategy):
    """A concrete implementation of BaseExtractionStrategy for testing."""
    def extract(self, pdf_document: fitz.Document, img_info: tuple, page_num: int, extraction_info: Dict) -> Tuple[Optional[Image.Image], Dict]:
        """Dummy extract implementation."""
        # This method is not called by the BaseStrategy methods being tested
        pass


class TestExtractionStrategies(unittest.TestCase):

    def setUp(self) -> None:
        # Create mock PDF document and image info
        # Using spec=fitz.Document is okay here as fitz.Document is not being patched at this level
        self.mock_doc = MagicMock(spec=fitz.Document)
        # img_info is typically (xref, s, w, h, bpc, cs, intent, format, filter, stream)
        self.mock_img_info = (10, 0, 100, 100, 8, fitz.csRGB, '', 'jpeg', 'dct', b'dummy_image_data')
        self.page_num = 1
        self.extraction_info: Dict[str, Any] = {} # Ensure it's a dictionary


        # Create dummy PIL Image objects for mocking return values
        self.dummy_image = Image.new('RGB', (100, 100), color = 'red')
        self.small_image = Image.new('RGB', (30, 30), color = 'blue') # Smaller than min size

    def tearDown(self) -> None:
        # Ensure any resources are cleaned up (PIL images might need closing if not garbage collected)
        self.dummy_image.close()
        self.small_image.close()

    # --- Helper Methods to create mock PyMuPDF/PIL objects ---

    def _create_mock_pixmap(self, image: Image.Image) -> MagicMock:
        """Creates a mock fitz.Pixmap object from a PIL Image."""
        width, height = image.size
        mode = image.mode
        # Ensure samples are bytes, convert if needed (e.g. for palette images)
        if image.mode == 'P':
            # Convert palette image to RGB or RGBA before getting samples
            img_for_samples = image.convert('RGB') # Convert to a mode that tobytes works reliably on
            samples = img_for_samples.tobytes()
            img_for_samples.close()
        else:
             samples = image.tobytes()


        n = len(image.getbands())
        alpha = 1 if 'A' in mode else 0
        # Set colorspace based on PIL mode for mocking purposes
        if mode in ['RGB', 'RGBA']:
             colorspace = fitz.csRGB
        elif mode == 'L':
             colorspace = fitz.csGRAY
        elif mode == 'CMYK':
             colorspace = fitz.csCMYK
        else:
             colorspace = None


        mock_pix = MagicMock() # Do not use spec=fitz.Pixmap here when fitz.Pixmap is patched
        mock_pix.width = width
        mock_pix.height = height
        mock_pix.samples = samples
        mock_pix.n = n
        mock_pix.alpha = alpha
        mock_pix.colorspace = colorspace # Set the mock colorspace
        mock_pix.tobytes.return_value = samples # Add tobytes method
        mock_pix.close = MagicMock() # Add a close method mock
        return mock_pix

    def _create_mock_extract_image_data(self, image: Image.Image, ext: str) -> Dict[str, Any]:
        """Creates a mock dictionary like fitz.Document.extract_image returns."""
        img_byte_arr = io.BytesIO()
        # Ensure the image mode is compatible with the format for saving to bytes
        # Convert before saving to bytes if necessary
        img_to_save = image
        if ext.lower() in ['jpg', 'jpeg'] and image.mode == 'RGBA':
             img_to_save = image.convert('RGB')
        elif ext.lower() == 'png' and image.mode == 'CMYK':
             img_to_save = image.convert('RGB') # PIL PNG save doesn't support CMYK directly

        img_to_save.save(img_byte_arr, format=ext.upper())

        if img_to_save != image:
             img_to_save.close() # Close the temporary converted image


        return {"ext": ext, "image": img_byte_arr.getvalue(), "xref": self.mock_img_info[0]} # Add xref as it's often included


    def _create_mock_rendered_pixmap(self, width: int, height: int) -> MagicMock:
        """Creates a mock fitz.Pixmap object simulating a page render."""
        img = Image.new('RGB', (width, height), color = 'gray') # Simulate a page render
        mock_pix = self._create_mock_pixmap(img)
        img.close() # Close the PIL image used to create samples
        return mock_pix


    # --- Tests for StandardExtractionStrategy ---

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_rgb(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful standard extraction for RGB image."""
        # Configure the patched fitz.Pixmap to return a mock pixmap instance
        mock_fitz_pixmap_instance = self._create_mock_pixmap(self.dummy_image.convert('RGB'))
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

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
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once() # Ensure pixmap is closed

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_cmyk(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful standard extraction for CMYK image."""
        mock_cmyk_image = self.dummy_image.convert('CMYK')
        # Configure the patched fitz.Pixmap to return a mock pixmap instance
        mock_fitz_pixmap_instance = self._create_mock_pixmap(mock_cmyk_image)
        # Manually set n for CMYK mock (Pixmaps from CMYK PIL images have n=4)
        mock_fitz_pixmap_instance.n = 4
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

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
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        mock_cmyk_image.close() # Clean up

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_failure(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test standard extraction failure."""
        mock_fitz_pixmap.side_effect = RuntimeError("Mock Pixmap error")

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        # Check for the correct error message format
        self.assertIn('Standard extraction failed for xref 10: Mock Pixmap error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_too_small(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test standard extraction resulting in an image too small."""
        mock_fitz_pixmap_instance = self._create_mock_pixmap(self.small_image) # 30x30
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG) # min_width/height = 50
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success']) # Ensure success is set to False
        self.assertEqual(info['extraction_method'], 'standard')
        # Check for the correct error message format
        self.assertIn('Image too small: 30x30', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info) # Dimensions are not set on failure
        mock_fitz_pixmap_instance.close.assert_called_once() # Ensure pixmap is closed even if size check fails
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])


    # --- Tests for AlternateColorspaceExtractionStrategy ---

    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_success(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful alternate colorspace extraction."""
        # Simulate an image that might need explicit conversion (e.g., Palette)
        mock_paletted_image = self.dummy_image.convert('P')
        mock_rgb_image = self.dummy_image.convert('RGB')

        # Configure the patched fitz.Pixmap to return the original (paletted) pixmap first,
        # and the converted (RGB) pixmap when called with csRGB and the first pixmap instance
        mock_paletted_pixmap_instance = self._create_mock_pixmap(mock_paletted_image)
        mock_rgb_pixmap_instance = self._create_mock_pixmap(mock_rgb_image)

        # Use side_effect to return different mocks based on call arguments
        def pixmap_side_effect(*args, **kwargs):
             # Check if it's the conversion call: first arg is colorspace, second is a pixmap instance
             if len(args) == 2 and isinstance(args[0], fitz.Colorspace) and isinstance(args[1], MagicMock):
                  return mock_rgb_pixmap_instance
             # Check if it's the initial creation call: first arg is doc, second is xref
             elif len(args) == 2 and isinstance(args[0], MagicMock) and args[1] == self.mock_img_info[0]:
                  return mock_paletted_pixmap_instance
             else:
                  raise RuntimeError(f"Unexpected Pixmap call with args: {args}, kwargs: {kwargs}")

        mock_fitz_pixmap.side_effect = pixmap_side_effect


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
        mock_fitz_pixmap.assert_has_calls([
             call(self.mock_doc, self.mock_img_info[0]),
             call(fitz.csRGB, mock_paletted_pixmap_instance) # Ensure it was called with the first pixmap instance
        ])
        # Assert close calls for both original and converted pixmaps
        mock_paletted_pixmap_instance.close.assert_called_once()
        mock_rgb_pixmap_instance.close.assert_called_once()
        mock_paletted_image.close()
        mock_rgb_image.close()


    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_failure(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test alternate colorspace extraction failure."""
        mock_fitz_pixmap.side_effect = RuntimeError("Mock Pixmap error")

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        # Check for the correct error message format
        self.assertIn('Alternate colorspace extraction failed for xref 10: Mock Pixmap error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])

    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_too_small(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test alternate colorspace extraction resulting in an image too small."""
        mock_paletted_image = self.small_image.convert('P') # 30x30
        mock_rgb_image = self.small_image.convert('RGB') # 30x30

        mock_paletted_pixmap_instance = self._create_mock_pixmap(mock_paletted_image)
        mock_rgb_pixmap_instance = self._create_mock_pixmap(mock_rgb_image)

        # Use side_effect to return different mocks based on call arguments
        def pixmap_side_effect(*args, **kwargs):
             # Check if it's the conversion call
             if len(args) == 2 and isinstance(args[0], fitz.Colorspace) and isinstance(args[1], MagicMock):
                  return mock_rgb_pixmap_instance
             # Check if it's the initial creation call
             elif len(args) == 2 and isinstance(args[0], MagicMock) and args[1] == self.mock_img_info[0]:
                  return mock_paletted_pixmap_instance
             else:
                  raise RuntimeError(f"Unexpected Pixmap call with args: {args}, kwargs: {kwargs}")

        mock_fitz_pixmap.side_effect = pixmap_side_effect

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG) # min_width/height = 50
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success']) # Ensure success is set to False
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        # Check for the correct error message format
        self.assertIn('Image too small: 30x30', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info)
        mock_fitz_pixmap.assert_has_calls([
             call(self.mock_doc, self.mock_img_info[0]),
             call(fitz.csRGB, mock_paletted_pixmap_instance) # Ensure it was called with the first pixmap instance
        ])
        # Assert close calls for both original and converted pixmaps
        mock_paletted_pixmap_instance.close.assert_called_once()
        mock_rgb_pixmap_instance.close.assert_called_once()
        mock_paletted_image.close()
        mock_rgb_image.close()


    # --- Tests for CompressionRetryStrategy ---

    # Need to patch Image.open and Image.Image.load in the strategy's module
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    def test_compression_retry_extraction_success(self, mock_pil_load: MagicMock, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test successful compression retry extraction."""
        # Configure fitz.Document.extract_image to return valid data
        valid_jpeg_data = self._create_mock_extract_image_data(self.dummy_image, 'jpeg')
        mock_extract_image.return_value = valid_jpeg_data

        # Configure PIL.Image.open to return a mock PIL Image instance
        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (100, 100) # Size > min_size
        mock_pil_image_instance.mode = 'RGB'
        mock_pil_image_instance.getbands.return_value = ('R', 'G', 'B') # For mode check
        mock_pil_image_instance.convert.return_value = mock_pil_image_instance # Convert returns self if already RGB
        mock_pil_image_instance.load.return_value = None # load doesn't return anything specific
        mock_pil_image_instance.close = MagicMock() # Add close method mock
        mock_pil_open.return_value = mock_pil_image_instance

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        # Initialize extraction_info here to ensure it's empty for this test's logic
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        # Check if it's the expected mock instance
        self.assertIs(extracted_img, mock_pil_image_instance)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        # Image.open is called with the BytesIO object created inside the strategy
        mock_pil_open.assert_called_once_with(ANY, format=None) # Format might be hinted by PIL, use ANY
        mock_pil_image_instance.load.assert_called_once() # Check load was called
        mock_pil_image_instance.close.assert_called_once() # Ensure image is closed


    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    def test_compression_retry_extraction_no_data(self, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test compression retry extraction when extract_image returns no data."""
        mock_extract_image.return_value = None # Simulate no data found

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        # Check for the correct error message format
        self.assertIn('No raw image data in extract_image result for xref 10', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed') # Ensure issue_type is set
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_not_called() # PIL should not be called


    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    def test_compression_retry_extraction_invalid_data(self, mock_pil_load: MagicMock, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test compression retry extraction with invalid image data."""
        # Configure fitz.Document.extract_image to return invalid data
        # Make sure it returns a dict with 'image' key, even if data is bad, to pass the initial 'if' check
        mock_extract_image.return_value = {"ext": "jpeg", "image": b'invalid_image_data', "xref": self.mock_img_info[0]}

        # Configure PIL.Image.open to raise an error
        mock_pil_open.side_effect = IOError("Mock PIL open error")

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        # Check for the correct error message format
        self.assertIn('Alternate compression extraction failed for xref 10: Mock PIL open error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed') # Ensure issue_type is set
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once() # PIL should be called
        mock_pil_load.assert_not_called() # load should not be called if open failed


    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    def test_compression_retry_extraction_too_small(self, mock_pil_load: MagicMock, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test compression retry extraction resulting in an image too small."""
        # Configure fitz.Document.extract_image to return data for a small image
        valid_png_data = self._create_mock_extract_image_data(self.small_image, 'png') # 30x30
        mock_extract_image.return_value = valid_png_data

        # Configure PIL.Image.open to return a mock PIL Image instance with small dimensions
        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (30, 30) # Size < min_size (50x50)
        mock_pil_image_instance.mode = 'RGB'
        mock_pil_image_instance.getbands.return_value = ('R', 'G', 'B')
        mock_pil_image_instance.convert.return_value = mock_pil_image_instance
        mock_pil_image_instance.load.return_value = None
        mock_pil_image_instance.close = MagicMock()
        mock_pil_open.return_value = mock_pil_image_instance

        strategy = CompressionRetryStrategy(MOCK_CONFIG) # min_width/height = 50
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success']) # Ensure success is set to False
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        # Check for the correct error message format
        self.assertIn('Image too small: 30x30', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues') # Issue type set by _check_min_size
        self.assertNotIn('dimensions', info) # Dimensions are not set on failure

        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once()
        mock_pil_image_instance.load.assert_called_once()
        mock_pil_image_instance.close.assert_called_once() # Ensure image is closed


    # --- Tests for PageBasedExtractionStrategy ---

    # Patching fitz.Page.get_pixmap and fitz.Matrix in the strategy's module
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_success(self, mock_fitz_matrix: MagicMock, mock_get_pixmap: MagicMock) -> None:
        """Test successful page-based extraction."""
        # Mock page object (spec is okay here)
        mock_page = MagicMock(spec=fitz.Page)
        # Ensure the mock doc returns the mock page when indexed AND has a length
        self.mock_doc.__getitem__.return_value = mock_page
        self.mock_doc.__len__.return_value = self.page_num # Ensure doc has at least the requested page

        # Mock the rendered pixmap return value
        mock_rendered_pixmap_instance = self._create_mock_rendered_pixmap(width=200, height=300)
        mock_get_pixmap.return_value = mock_rendered_pixmap_instance

        # Mock Matrix creation return value
        mock_matrix_instance = MagicMock() # Do not use spec=fitz.Matrix when patching fitz.Matrix
        mock_fitz_matrix.return_value = mock_matrix_instance

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG) # dpi = 150
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (200, 300)) # Should be size of the rendered page mock
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        self.assertEqual(info['dimensions'], '200x300')
        self.assertEqual(info['mode'], 'RGB')
        self.assertIn('warning', info) # Should have a warning about using whole page
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        # Check calls
        # The strategy gets page_num (1-indexed), converts to page_idx (0-indexed)
        self.mock_doc.__getitem__.assert_called_once_with(self.page_num - 1) # Check index used
        mock_fitz_matrix.assert_called_once_with(MOCK_CONFIG['dpi'] / 72.0, MOCK_CONFIG['dpi'] / 72.0)
        # Check that get_pixmap was called with the mock matrix instance
        mock_get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)
        # Ensure pixmap instance was closed (handled by finally in strategy)
        mock_rendered_pixmap_instance.close.assert_called_once()


    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_failure(self, mock_fitz_matrix: MagicMock, mock_get_pixmap: MagicMock) -> None:
        """Test page-based extraction failure."""
        # Mock page object (spec is okay here)
        mock_page = MagicMock(spec=fitz.Page)
        # Ensure the mock doc returns the mock page when indexed AND has a length
        self.mock_doc.__getitem__.return_value = mock_page
        self.mock_doc.__len__.return_value = self.page_num # Ensure doc has at least the requested page

        # Configure the patched get_pixmap to raise an error
        mock_get_pixmap.side_effect = RuntimeError("Mock rendering error")

        # Mock Matrix creation return value
        mock_matrix_instance = MagicMock() # Do not use spec=fitz.Matrix when patching fitz.Matrix
        mock_fitz_matrix.return_value = mock_matrix_instance


        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        # Check for the correct error message format - it should now catch the RuntimeError
        self.assertIn('Page-based extraction failed for page 1: Mock rendering error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed') # Ensure issue_type is set

        # Check calls
        # The strategy gets page_num (1-indexed), converts to page_idx (0-indexed)
        self.mock_doc.__getitem__.assert_called_once_with(self.page_num - 1) # Check index used
        mock_fitz_matrix.assert_called_once_with(MOCK_CONFIG['dpi'] / 72.0, MOCK_CONFIG['dpi'] / 72.0)
        # Check that get_pixmap was called with the mock matrix instance
        mock_get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)


    # --- Tests for BaseExtractionStrategy methods (using concrete mock) ---

    def test_base_strategy_check_min_size_pass(self) -> None:
        """Test min size check passes."""
        # Instantiate the concrete mock strategy
        strategy = ConcreteMockStrategy(MOCK_CONFIG)
        info: Dict[str, Any] = {} # Ensure info dict is passed

        self.assertTrue(strategy._check_min_size(self.dummy_image, info))
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

    def test_base_strategy_check_min_size_fail(self) -> None:
        """Test min size check fails."""
        # Instantiate the concrete mock strategy
        strategy = ConcreteMockStrategy(MOCK_CONFIG)
        info: Dict[str, Any] = {} # Ensure info dict is passed

        self.assertFalse(strategy._check_min_size(self.small_image, info))
        # Check for the correct error message format
        self.assertIn('Image too small: 30x30', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')


if __name__ == '__main__':
    unittest.main()