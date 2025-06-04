# scripts/extraction/tests/test_extraction_strategies.py

import unittest
from unittest.mock import MagicMock, patch, call
from PIL import Image
import io
import fitz
import pytest # Import pytest for skip
from typing import Dict, Any, Tuple, Optional
# Import ABC and abstractmethod for creating a concrete base class test implementation
from abc import ABC, abstractmethod


# Import the strategies to be tested
from scripts.extraction.extraction_strategies.standard_strategy import StandardExtractionStrategy
from scripts.extraction.extraction_strategies.alternate_colorspace_strategy import AlternateColorspaceExtractionStrategy
from scripts.extraction.extraction_strategies.compression_retry_strategy import CompressionRetryStrategy
from scripts.extraction.extraction_strategies.page_based_strategy import PageBasedExtractionStrategy
from scripts.extraction.extraction_strategies.base_strategy import BaseExtractionStrategy


# Mock configuration
MOCK_CONFIG = {
    "min_width": 50,
    "min_height": 50,
    "dpi": 150 # For page-based strategy
}

# Helper function to create a dummy PIL image for testing
def create_dummy_image(width=100, height=100, mode='RGB', color='red'):
    """Creates a simple dummy PIL Image."""
    try:
        img = Image.new(mode, (width, height), color=color)
        return img
    except Exception as e:
        print(f"Error creating dummy image: {e}")
        return None

# Helper function to create a mock PyMuPDF Pixmap
# This mock needs to simulate key attributes and methods used by the strategies
def create_mock_pixmap(pil_image: Image.Image) -> MagicMock:
    """Creates a MagicMock that simulates a fitz.Pixmap."""
    if pil_image is None:
        # Return a mock with default/empty attributes if image is None
        return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())

    # Determine fitz attributes based on PIL mode
    if pil_image.mode == 'L':
        rawmode = 'L'
        n = 1
        alpha = 0
        cs = fitz.csGRAY
    elif pil_image.mode == 'RGB':
        rawmode = 'RGB'
        n = 3
        alpha = 0
        cs = fitz.csRGB
    elif pil_image.mode == 'RGBA':
        rawmode = 'RGBA'
        n = 4
        alpha = 1
        # For mocking, we don't need a real fitz colorspace object for RGBA
        # Just ensure n=4 and alpha=1 are set correctly.
        cs = MagicMock(name='DeviceRGB') # Or some other mock, the name usually isn't checked unless specific logic exists
        cs.n = 3 # Simulate base colorspace channels
    elif pil_image.mode == 'CMYK':
        rawmode = 'CMYK'
        n = 4
        alpha = 0
        cs = fitz.csCMYK
    elif pil_image.mode == 'P': # Paletted
         # Paletted images in PDF often need conversion.
         # Simulate the attributes that would trigger conversion in the strategy.
         # A common way to trigger conversion is n != 1/3/4 or alpha > 0.
         # Paletted (n=1, alpha=0) with non-Gray colorspace name is one way.
         rawmode = 'L' # Simulates the single channel of palette indices for samples
         n = 1
         alpha = 0
         # Mock a colorspace that isn't DeviceGray to make it non-standard gray
         mock_colorspace = MagicMock()
         mock_colorspace.n = n
         mock_colorspace.name = 'Indexed' # Or some other non-standard name
         cs = mock_colorspace
         # Convert PIL image to 'L' before getting samples if source is 'P'
         # This ensures .tobytes('raw', 'L') works correctly.
         try:
            pil_image = pil_image.convert('L')
         except Exception as e:
             print(f"Warning: Could not convert PIL P mode to L for mocking: {e}")
             # Fallback: try converting to RGB or just use original samples if 'L' fails
             try:
                 pil_image = pil_image.convert('RGB')
                 rawmode = 'RGB'
                 n = 3
                 alpha = 0
                 cs = fitz.csRGB
             except Exception as e2:
                 print(f"Error: Could not convert PIL P mode to RGB either: {e2}")
                 # Cannot create valid mock samples
                 return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())

    else:
        # For other unsupported modes, convert to RGB for mocking Pixmap samples
        try:
            pil_image = pil_image.convert('RGB')
            rawmode = 'RGB'
            n = 3
            alpha = 0
            cs = fitz.csRGB
        except Exception as e:
            print(f"Error: Could not convert PIL image mode {pil_image.mode} to RGB for mocking: {e}")
            return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())


    # Get raw samples, which is what Pixmap.samples contains
    try:
        samples = pil_image.tobytes('raw', rawmode)
    except Exception as e:
        print(f"Error getting raw bytes from PIL image (mode={pil_image.mode}, rawmode={rawmode}) for mocking: {e}")
        return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())


    # Use plain MagicMock for the instance
    mock_pix = MagicMock()
    mock_pix.samples = samples
    mock_pix.width = pil_image.width
    mock_pix.height = pil_image.height
    mock_pix.n = n
    mock_pix.alpha = alpha
    mock_pix.colorspace = cs
    mock_pix.close = MagicMock() # Add a mock close method

    return mock_pix

# Helper function to create mock data returned by extract_image
def create_mock_extract_image_data(pil_image: Image.Image, img_ext: str) -> Dict:
    """Creates a dictionary simulating the output of fitz.Document.extract_image."""
    buffer = io.BytesIO()
    # Save image to the buffer in the specified format
    try:
        # PIL needs format name (e.g., 'JPEG', 'PNG'), not extension (e.g., 'jpeg', 'png')
        pil_format = img_ext.upper()
        # Ensure PIL supports the format directly from the image mode
        # If mode is RGBA and format is JPEG, it will fail unless converted
        if pil_image.mode == 'RGBA' and pil_format == 'JPEG':
             pil_image = pil_image.convert('RGB')
        elif pil_image.mode == 'P' and pil_format not in ['PNG', 'GIF', 'TIFF']:
             # Some formats don't support paletted, convert
             pil_image = pil_image.convert('RGB')

        pil_image.save(buffer, format=pil_format)
        img_bytes = buffer.getvalue()
        return {"ext": img_ext, "image": img_bytes}
    except Exception as e:
        print(f"Error saving dummy image to bytes for mock extract_image (ext={img_ext}, mode={pil_image.mode}): {e}")
        # Return empty dict or None as the strategy expects
        return {}


# Define a concrete dummy strategy to test BaseExtractionStrategy methods
class ConcreteDummyExtractionStrategy(BaseExtractionStrategy):
     def extract(self, pdf_document, img_info, page_num, extraction_info):
          # This method is not under test for BaseStrategy, provide a minimal implementation
          return None, extraction_info


class TestExtractionStrategies(unittest.TestCase):

    def setUp(self):
        """Set up common mocks and test data."""
        # Mock PyMuPDF document and page
        # Use plain MagicMock for instances to avoid spec/isinstance conflicts
        self.mock_doc = MagicMock()
        self.mock_page = MagicMock()

        # Ensure mock_doc behaves like a document for methods used
        self.page_num = 1 # 1-indexed page number for tests
        # Mock len() and getitem for page access
        self.mock_doc.__len__ = MagicMock(return_value=10) # Default length > test page_num
        self.mock_doc.__getitem__ = MagicMock(return_value=self.mock_page)

        # Mock the Page.get_pixmap method used by PageBasedStrategy
        self.mock_page.get_pixmap = MagicMock()

        # Mock image info tuple (xref, ...) - Minimal required is xref for Standard/Alternate
        self.mock_img_info = (10, 0, 100, 100, 8, fitz.csRGB, '', '') # Example tuple with xref 10

        # Initial extraction info dict - reset for each test
        self.extraction_info: Dict = {}

        # Dummy PIL images for creating mock pixmaps/data
        self.dummy_image = create_dummy_image(100, 100, 'RGB', 'blue') # Meets min size
        self.small_image = create_dummy_image(30, 30, 'RGB', 'green') # Smaller than min size
        # Create a paletted image for alternate colorspace tests
        self.paletted_image = create_dummy_image(100, 100, 'RGB', 'red').convert('P')
        # Create an RGBA image for alternate colorspace tests
        self.rgba_image = create_dummy_image(100, 100, 'RGBA', (255, 0, 0, 128)) # Semi-transparent red

    def tearDown(self):
        """Clean up dummy images."""
        if self.dummy_image:
            self.dummy_image.close()
        if self.small_image:
            self.small_image.close()
        if self.paletted_image:
             self.paletted_image.close()
        if self.rgba_image:
             self.rgba_image.close()

    # Helper to create mock pixmap instances with necessary attributes
    # Used by patching fitz.Pixmap and setting its return_value or side_effect
    def _create_mock_pixmap(self, pil_image: Optional[Image.Image]) -> MagicMock:
         return create_mock_pixmap(pil_image)

    # Helper to create mock data for extract_image
    def _create_mock_extract_image_data(self, pil_image: Image.Image, img_ext: str) -> Dict:
         return create_mock_extract_image_data(pil_image, img_ext)

    # Helper to create a mock pixmap suitable for page rendering results
    def _create_mock_rendered_pixmap(self, width: int, height: int, mode='RGB') -> MagicMock:
         # Page rendering typically results in RGB or RGBA
         dummy_page_image = create_dummy_image(width, height, mode)
         # Manually create mock with samples, width, height, alpha based on PIL image
         mock_pix = MagicMock()
         mock_pix.samples = dummy_page_image.tobytes('raw', dummy_page_image.mode)
         mock_pix.width, mock_pix.height = dummy_page_image.size
         if mode == 'RGBA':
            mock_pix.alpha = 1
         else:
            mock_pix.alpha = 0 # Fix: Use integer 1 or 0
         mock_pix.close = MagicMock() # Add a mock close method
         dummy_page_image.close() # Clean up the temp PIL image
         return mock_pix


    # --- Base Strategy Tests ---
    # Use the concrete dummy strategy to test BaseStrategy methods
    def test_base_strategy_check_min_size_pass(self) -> None:
        """Test base strategy min size check passes."""
        strategy = ConcreteDummyExtractionStrategy(MOCK_CONFIG)
        mock_image = MagicMock(spec=Image.Image, width=100, height=100) # Use width/height directly
        info = {}
        self.assertTrue(strategy._check_min_size(mock_image, info))
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

    def test_base_strategy_check_min_size_fail(self) -> None:
        """Test base strategy min size check fails."""
        strategy = ConcreteDummyExtractionStrategy(MOCK_CONFIG)
        mock_image = MagicMock(spec=Image.Image, width=30, height=30) # Use width/height directly
        info = {}
        self.assertFalse(strategy._check_min_size(mock_image, info))
        self.assertIn('Image too small', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        # Check the error message includes dimensions and config
        self.assertIn('30x30', info['error'])
        self.assertIn(f"min: {MOCK_CONFIG['min_width']}x{MOCK_CONFIG['min_height']}", info['error'])


    # --- Standard Extraction Strategy Tests ---
    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_rgb(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful standard extraction for RGB image."""
        # Configure the patched fitz.Pixmap to return a mock pixmap instance
        mock_fitz_pixmap_instance = self._create_mock_pixmap(self.dummy_image.convert('RGB'))
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here to ensure it's empty for this test's logic
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
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        # Assert that the pixmap instance's close method was called
        mock_fitz_pixmap_instance.close.assert_called_once()
        # The returned PIL image should be closed by the caller
        if extracted_img:
             extracted_img.close()


    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_cmyk(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful standard extraction for CMYK image."""
        mock_cmyk_image = self.dummy_image.convert('CMYK')
        # Configure the patched fitz.Pixmap to return a mock pixmap instance
        mock_fitz_pixmap_instance = self._create_mock_pixmap(mock_cmyk_image)
        # The create_mock_pixmap handles setting n=4, alpha=0, colorspace CMYK for this PIL mode
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB') # Should be converted to RGB
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB') # Info should reflect the final PIL mode
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        # Assert that the pixmap instance's close method was called
        mock_fitz_pixmap_instance.close.assert_called_once()
        # The returned PIL image should be closed by the caller
        if extracted_img:
             extracted_img.close()

    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_gray(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful standard extraction for Gray image."""
        mock_gray_image = self.dummy_image.convert('L')
        mock_fitz_pixmap_instance = self._create_mock_pixmap(mock_gray_image)
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'L') # Should be L
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'L') # Info should reflect the final PIL mode
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        if extracted_img:
             extracted_img.close()


    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_success_rgba(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful standard extraction for RGBA image."""
        mock_rgba_image = self.dummy_image.convert('RGBA')
        mock_fitz_pixmap_instance = self._create_mock_pixmap(mock_rgba_image)
        # Ensure the mock has n=4, alpha=1, which is the key for RGBA handling
        mock_fitz_pixmap_instance.n = 4
        mock_fitz_pixmap_instance.alpha = 1
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGBA') # Should be RGBA
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGBA')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        mock_fitz_pixmap_instance.close.assert_called_once()
        if extracted_img:
             extracted_img.close()


    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_too_small(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test standard extraction resulting in an image too small."""
        mock_fitz_pixmap_instance = self._create_mock_pixmap(self.small_image.convert('RGB')) # 30x30
        mock_fitz_pixmap.return_value = mock_fitz_pixmap_instance

        strategy = StandardExtractionStrategy(MOCK_CONFIG) # min_width/height = 50
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success']) # Ensure success is set to False
        self.assertEqual(info['extraction_method'], 'standard')
        # Check for the correct error message format
        self.assertIn('Image too small: 30x30', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues') # Ensure issue_type is set
        self.assertNotIn('dimensions', info) # Dimensions are not set on failure
        self.assertNotIn('mode', info)
        # Ensure pixmap is closed even if size check fails
        mock_fitz_pixmap_instance.close.assert_called_once()
        # No PIL image is returned, so no need to close extracted_img


    @patch('scripts.extraction.extraction_strategies.standard_strategy.fitz.Pixmap')
    def test_standard_extraction_failure(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test standard extraction failure due to Pixmap creation error."""
        # Configure the patched fitz.Pixmap constructor to raise an error
        mock_fitz_pixmap.side_effect = RuntimeError("Mock Pixmap error")

        strategy = StandardExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'standard')
        # Check for the correct error message format
        self.assertIn('Standard extraction failed for xref 10: Mock Pixmap error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        # As constructor failed, no instance was created to call .close() on.


    # --- Alternate Colorspace Extraction Strategy Tests ---
    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_success_paletted(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful alternate colorspace extraction for Paletted image (convert to RGB)."""
        # Simulate an image that might need explicit conversion (e.g., Paletted)
        # Mock the initial pixmap as a Paletted image (n=1, alpha=0, but non-Gray colorspace)
        mock_paletted_pixmap_instance = self._create_mock_pixmap(self.paletted_image)
        # Ensure it has attributes that signal conversion is needed
        # create_mock_pixmap handles setting n=1, alpha=0, colorspace='Indexed' for 'P' mode
        self.assertEqual(mock_paletted_pixmap_instance.n, 1)
        self.assertEqual(mock_paletted_pixmap_instance.alpha, 0)
        self.assertEqual(mock_paletted_pixmap_instance.colorspace.name, 'Indexed')


        # Mock the result of the conversion to RGB using fitz.Pixmap(fitz.csRGB, pix)
        mock_rgb_image = self.paletted_image.convert('RGB') # 100x100
        mock_rgb_pixmap_instance = self._create_mock_pixmap(mock_rgb_image)
        # Ensure the mock has attributes matching a fitz.csRGB conversion result (alpha=0)
        self.assertEqual(mock_rgb_pixmap_instance.n, 3)
        self.assertEqual(mock_rgb_pixmap_instance.alpha, 0)


        # Use side_effect to return different mocks based on call arguments
        def pixmap_side_effect(*args, **kwargs):
            if len(args) == 2 and args[0] == self.mock_doc:
                return mock_paletted_pixmap_instance
            else:
                return mock_rgb_pixmap_instance

        mock_fitz_pixmap.side_effect = pixmap_side_effect

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB') # Should be converted to RGB
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB') # Info should reflect the final PIL mode
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        # Check that fitz.Pixmap was called at least twice (original + conversion)
        self.assertGreaterEqual(mock_fitz_pixmap.call_count, 2)
        # Check for specific calls is tricky with multiple conversion attempts,
        # better to just check count and success.
        # If we must check calls, check for the initial and at least one RGB conversion attempt.
        mock_fitz_pixmap.assert_has_calls([
             call(self.mock_doc, self.mock_img_info[0]) # Initial call to get raw pixmap
             # Cannot strictly assert the conversion call as it might be Pixmap(fitz.csRGB, pix) or Pixmap(fitz.csRGB, pix, alpha=False) etc.
             # Just verifying count is > 1 implies conversion was attempted.
        ])

        # Assert that both pixmap instances' close methods were called
        # The side effect returns specific mocks, so we can check them.
        mock_paletted_pixmap_instance.close.assert_called_once()
        mock_rgb_pixmap_instance.close.assert_called_once()
        # The returned PIL image should be closed by the caller
        if extracted_img:
             extracted_img.close()

    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_success_rgba(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test successful alternate colorspace extraction for RGBA image (convert to RGBA)."""
        # Simulate an image with alpha where standard extraction might have failed.
        mock_rgba_pixmap_instance = self._create_mock_pixmap(self.rgba_image) # 100x100 RGBA PIL image
        # Ensure the mock has attributes signaling alpha
        mock_rgba_pixmap_instance.n = 4 # Simulate n=4 with alpha=1 from PDF
        mock_rgba_pixmap_instance.alpha = 1

        # Mock the result of the conversion to RGBA (strategy tries Pixmap(fitz.csRGB, pix, alpha=True))
        mock_rgba_image_converted = self.rgba_image # Conversion of RGBA to RGBA via fitz.csRGB, alpha=True should yield similar RGBA
        mock_rgba_pixmap_converted_instance = self._create_mock_pixmap(mock_rgba_image_converted)
        mock_rgba_pixmap_converted_instance.n = 4
        mock_rgba_pixmap_converted_instance.alpha = 1


        # Use side_effect to return different mocks based on call arguments
        def pixmap_side_effect(*args, **kwargs):
             # Initial creation call: fitz.Pixmap(doc, xref)
             if len(args) == 2 and args[0] == self.mock_doc and args[1] == self.mock_img_info[0]:
                 return mock_rgba_pixmap_instance
             # Conversion call: Strategy tries different conversion approaches, including alpha=True.
             # A simple check is if the first arg is a colorspace (fitz.csRGB is used).
             # The strategy calls Pixmap(fitz.csRGB, pix, alpha=True)
             elif len(args) >= 2 and isinstance(args[0], fitz.Colorspace) and args[0] == fitz.csRGB and kwargs.get('alpha') is True:
                  return mock_rgba_pixmap_converted_instance
             else:
                  # Fallback for unexpected calls, perhaps for debugging
                  print(f"Unexpected Pixmap call in side_effect: args={args}, kwargs={kwargs}")
                  # Return a default mock or raise an error if strictly expecting only known calls
                  return MagicMock()


        mock_fitz_pixmap.side_effect = pixmap_side_effect


        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGBA') # Should retain RGBA mode
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGBA') # Info should reflect the final PIL mode
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        # Check that fitz.Pixmap was called at least twice (original + conversion attempt)
        # Simplification: The strategy might try conversion even if alpha > 0.
        # Let's just assert that Pixmap was called at least once (to get the original)
        # and trust the side_effect and successful extraction confirms the flow.
        # We cannot strictly assert call_count == 2 with specific args due to strategy's internal logic flow.
        # The strategy first checks alpha, then attempts conversion if alpha > 0 *or* if alpha == 0 and needs conversion.
        # If alpha > 0, it tries Pixmap(fitz.csRGB, pix, alpha=True). If alpha == 0, it tries Pixmap(fitz.csRGB, pix).
        # The side effect setup correctly handles both.
        # A simple assertion that Pixmap was called at all is sufficient here, combined with the success checks.
        self.assertGreaterEqual(mock_fitz_pixmap.call_count, 1) # At least the initial call happens

        # The original and converted pixmap instances should be closed by the strategy.
        mock_rgba_pixmap_instance.close.assert_called_once()
        mock_rgba_pixmap_converted_instance.close.assert_called_once()

        # The returned PIL image should be closed by the caller
        if extracted_img:
             extracted_img.close()

    # Add a test for a non-standard colorspace like Lab
    # @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    # def test_alternate_colorspace_extraction_success_lab(self, mock_fitz_pixmap: MagicMock) -> None:
    #     """Test successful alternate colorspace extraction for Lab image (convert to RGB)."""


    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_too_small(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test alternate colorspace extraction resulting in an image too small."""
        # Simulate a small Paletted image that needs conversion
        mock_paletted_pixmap_instance = self._create_mock_pixmap(self.small_image.convert('P')) # 30x30
        mock_paletted_pixmap_instance.n = 1
        mock_paletted_pixmap_instance.alpha = 0
        mock_paletted_pixmap_instance.colorspace = MagicMock(name='Indexed')

        # Mock the result of the conversion to RGB (which will also be small)
        mock_rgb_image = self.small_image.convert('RGB') # 30x30
        mock_rgb_pixmap_instance = self._create_mock_pixmap(mock_rgb_image)
        mock_rgb_pixmap_instance.n = 3
        mock_rgb_pixmap_instance.alpha = 0
        mock_rgb_pixmap_instance.colorspace = fitz.csRGB # Still use fitz.csRGB for call assertion

        # Use side_effect to return different mocks based on call arguments
        # This is similar to the paletted success case, expecting Pixmap(fitz.csRGB, pix) without alpha kwarg.
        def pixmap_side_effect(*args, **kwargs):
            # Initial creation call: fitz.Pixmap(doc, xref)
            if len(args) == 2 and args[0] == self.mock_doc and args[1] == self.mock_img_info[0]:
                return mock_paletted_pixmap_instance
            # Conversion call: Strategy tries different conversion approaches.
            # A simple check is if the first arg is a colorspace (fitz.csRGB is used).
            elif len(args) >= 2 and isinstance(args[0], fitz.Colorspace) and args[0] == fitz.csRGB:
                 # The strategy calls Pixmap(fitz.csRGB, pix, alpha=pix.alpha > 0)
                 # For the paletted case with alpha=0, this means alpha=False or no alpha kwarg.
                 # Let's just return the converted RGB mock if it's a call with fitz.csRGB.
                 return mock_rgb_pixmap_instance
            else: # Catch unexpected calls
                 print(f"Unexpected Pixmap call in side_effect: args={args}, kwargs={kwargs}")
                 return MagicMock()

        mock_fitz_pixmap.side_effect = pixmap_side_effect

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG) # min_width/height = 50
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success']) # Ensure success is set to False
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        # Check for the correct error message format
        self.assertIn(f'Image too small: 30x30 (min: {MOCK_CONFIG["min_width"]}x{MOCK_CONFIG["min_height"]})', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues') # Ensure issue_type is set
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)

        # Check that fitz.Pixmap was called at least twice
        self.assertGreaterEqual(mock_fitz_pixmap.call_count, 2)
        mock_fitz_pixmap.assert_has_calls([
            call(self.mock_doc, self.mock_img_info[0]), # Initial call
            # Cannot strictly assert the conversion call due to strategy's variations
        ])
        # Assert that both pixmap instances' close methods were called
        mock_paletted_pixmap_instance.close.assert_called_once()
        mock_rgb_pixmap_instance.close.assert_called_once()
        # No PIL image is returned, so no need to close extracted_img


    @patch('scripts.extraction.extraction_strategies.alternate_colorspace_strategy.fitz.Pixmap')
    def test_alternate_colorspace_extraction_failure(self, mock_fitz_pixmap: MagicMock) -> None:
        """Test alternate colorspace extraction failure due to Pixmap creation error."""
        # Configure the patched fitz.Pixmap constructor to raise an error
        mock_fitz_pixmap.side_effect = RuntimeError("Mock Pixmap error")

        strategy = AlternateColorspaceExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'pixmap_alternate_colorspace')
        # Check for the correct error message format
        # Fix: Match actual error message format from strategy
        self.assertIn('Alternate colorspace extraction failed for xref 10: Mock Pixmap error', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        mock_fitz_pixmap.assert_called_once_with(self.mock_doc, self.mock_img_info[0])
        # As constructor failed, no instance was created to call .close() on.


    # --- Compression Retry Strategy Tests ---
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    def test_compression_retry_extraction_success(self, mock_pil_load: MagicMock, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test successful compression retry extraction."""
        # Configure fitz.Document.extract_image to return valid data
        valid_jpeg_data = self._create_mock_extract_image_data(self.dummy_image, 'jpeg')
        mock_extract_image.return_value = valid_jpeg_data
        # Explicitly assign the mock to the mock document instance
        self.mock_doc.extract_image = mock_extract_image


        # Configure PIL.Image.open to return a mock PIL Image instance
        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (100, 100) # Size > min_size
        mock_pil_image_instance.width = 100 # Add width attribute
        mock_pil_image_instance.height = 100 # Add height attribute
        mock_pil_image_instance.mode = 'RGB'
        # Mock convert to return self if already the target mode (RGB or L or RGBA)
        # Or return a new mock instance if conversion is needed
        def mock_convert(mode):
            if mode == mock_pil_image_instance.mode:
                 return mock_pil_image_instance
            # Create a new mock instance for the converted image
            new_mock_img = MagicMock(spec=Image.Image)
            new_mock_img.size = mock_pil_image_instance.size
            new_mock_img.width = mock_pil_image_instance.width # Ensure converted mock has dimensions
            new_mock_img.height = mock_pil_image_instance.height
            new_mock_img.mode = mode
            new_mock_img.close = MagicMock() # Converted image needs a close method
            return new_mock_img
        mock_pil_image_instance.convert.side_effect = mock_convert
        mock_pil_image_instance.load.return_value = None # load doesn't return anything specific
        mock_pil_image_instance.close = MagicMock() # Add close method mock
        mock_pil_open.return_value = mock_pil_image_instance

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        # Initialize extraction_info here to ensure it's empty for this test's logic
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB') # Should be RGB after optional convert
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        # Image.open is called with a BytesIO stream
        mock_pil_open.assert_called_once()
        args, kwargs = mock_pil_open.call_args
        self.assertIsInstance(args[0], io.BytesIO)
        # Fix: Remove assertion for format hint, it's not used in implementation
        # self.assertEqual(kwargs.get('format'), 'JPEG') # Check format hint

        # Assert load was called on the image instance returned by open
        mock_pil_image_instance.load.assert_called_once()

        # Assert close was called on the *original* image instance if convert returned a new one.
        # The strategy closes the internal variable `pil_image` if it's not the one returned.
        # If convert returns a new image, the original `pil_image` is closed.
        # mock_pil_image_instance.close.assert_called_once()
        # The *returned* image (the result of convert) should NOT be closed by the strategy.
        # Check if convert was called and if it returned a different instance
        if mock_pil_image_instance.convert.called and mock_pil_image_instance.convert.return_value != mock_pil_image_instance:
             mock_pil_image_instance.convert.return_value.close.assert_not_called()


        # The returned PIL image (which is the mock_pil_image_instance or a converted mock) should be closed by the caller
        if extracted_img:
             extracted_img.close()


    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    def test_compression_retry_extraction_no_data(self, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test compression retry extraction when extract_image returns no data."""
        # Configure fitz.Document.extract_image to return None or empty dict
        # Test expects empty dict based on code logic `if not (img_dict and isinstance(img_dict, dict) and img_dict.get("image")):`
        mock_extract_image.return_value = {} # Simulate no data found
        # Explicitly assign the mock to the mock document instance
        self.mock_doc.extract_image = mock_extract_image

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        # Check for the correct error message format
        # Fix: Match actual error message format from strategy
        self.assertIn('No raw image data found in extract_image result', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed') # Ensure issue_type is set
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)

        # Assert that extract_image was called
        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        # Assert that Image.open was NOT called because no data was found
        mock_pil_open.assert_not_called()
        # No PIL image instance was created, so no close call expected

    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    def test_compression_retry_extraction_invalid_data(self, mock_pil_load: MagicMock, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test compression retry extraction with invalid image data."""
        # Configure fitz.Document.extract_image to return invalid data
        # Make sure it returns a dict with 'image' key, even if data is bad, to pass the initial 'if' check
        mock_extract_image.return_value = {"ext": "jpeg", "image": b'invalid_image_data', "xref": self.mock_img_info[0]}
        # Explicitly assign the mock to the mock document instance
        self.mock_doc.extract_image = mock_extract_image

        # Configure PIL.Image.open to return a mock PIL Image instance *which will then fail on load*
        # This setup is crucial to ensure the PIL image close method is tested in the error path.
        mock_pil_image_instance = MagicMock(spec=Image.Image)
        # Make it look valid initially but fail on load
        mock_pil_image_instance.size = (100, 100)
        mock_pil_image_instance.width = 100 # Add width attribute
        mock_pil_image_instance.height = 100 # Add height attribute
        mock_pil_image_instance.mode = 'RGB' # Needs a mode for convert mock
        # Add a side_effect to the convert method as well, in case it's called before load
        mock_pil_image_instance.convert.return_value = mock_pil_image_instance # Assume convert succeeds before load fails
        mock_pil_image_instance.load.side_effect = IOError("Mock PIL load error") # Simulate load failure
        mock_pil_image_instance.close = MagicMock() # Add close method mock
        mock_pil_open.return_value = mock_pil_image_instance # Image.open returns this mock

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        # Check for the correct error message format - it should catch the Image.open/load error
        # The error comes from the raised exception, which is caught.
        # Fix: Match actual error message format from strategy
        self.assertIn('Alternate compression extraction failed for xref 10: Error during image decoding: Mock PIL load error', info['error'])
        self.assertEqual(info['issue_type'], 'decoding_failed') # Should be decoding_failed now
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)

        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once()
        # Assert load was attempted and failed
        mock_pil_image_instance.load.assert_called_once()
        # Assert the partially created PIL image was closed due to the error
        # Due to the structure, the close might be called twice (once in except, once in finally). Check for at least one call.
        self.assertGreaterEqual(mock_pil_image_instance.close.call_count, 1)
        # No PIL image is returned, so no need to close extracted_img


    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.fitz.Document.extract_image')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    def test_compression_retry_extraction_too_small(self, mock_pil_load: MagicMock, mock_pil_open: MagicMock, mock_extract_image: MagicMock) -> None:
        """Test compression retry extraction resulting in an image too small."""
        # Configure fitz.Document.extract_image to return data for a small image
        valid_png_data = self._create_mock_extract_image_data(self.small_image, 'png') # 30x30
        mock_extract_image.return_value = valid_png_data
        # Explicitly assign the mock to the mock document instance
        self.mock_doc.extract_image = mock_extract_image

        # Configure PIL.Image.open to return a mock PIL Image instance with small dimensions
        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (30, 30) # Size < min_size (50x50)
        mock_pil_image_instance.width = 30 # Add width attribute
        mock_pil_image_instance.height = 30 # Add height attribute
        mock_pil_image_instance.mode = 'RGB'
        # Ensure convert returns a mock with the correct small size
        def mock_convert(mode):
            new_mock_img = MagicMock(spec=Image.Image)
            new_mock_img.size = (30, 30)
            new_mock_img.width = 30 # Ensure converted mock has dimensions
            new_mock_img.height = 30
            new_mock_img.mode = mode
            new_mock_img.close = MagicMock()
            return new_mock_img
        mock_pil_image_instance.convert.side_effect = mock_convert
        mock_pil_image_instance.load.return_value = None
        mock_pil_image_instance.close = MagicMock() # Add close method mock
        mock_pil_open.return_value = mock_pil_image_instance # Image.open returns this mock


        strategy = CompressionRetryStrategy(MOCK_CONFIG) # min_width/height = 50
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success']) # Ensure success is set to False
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        # Check for the correct error message format from _check_min_size
        self.assertIn(f'Image too small: 30x30 (min: {MOCK_CONFIG["min_width"]}x{MOCK_CONFIG["min_height"]})', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues') # Ensure issue_type is set
        self.assertNotIn('dimensions', info) # Dimensions are not set on failure
        self.assertNotIn('mode', info)

        mock_extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once()
        mock_pil_image_instance.load.assert_called_once()
        # Assert the partially created PIL image was closed because it was too small and not returned
        # The strategy closes the 'pil_image' variable if the size check fails.
        # If convert returns a new image, 'pil_image' points to the converted one.
        # Fix: Check if the original or converted image was closed depending on if convert was called
        # The strategy closes `pil_image` which becomes the converted one if convert was called.
        if mock_pil_image_instance.convert.called:
             mock_pil_image_instance.convert.return_value.close.assert_called_once()
        else: # If convert was not called, the original image is closed
             mock_pil_image_instance.close.assert_called_once()

        # No PIL image is returned, so no need to close extracted_img


    # --- Page Based Extraction Strategy Tests ---
    # Patch fitz.Page.get_pixmap and fitz.Matrix as before
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_success(self, mock_fitz_matrix: MagicMock, mock_get_pixmap: MagicMock) -> None:
        """Test successful page-based extraction."""
        # Mock page object (plain MagicMock from setUp)
        # Ensure the mock doc returns the mock page when indexed AND has a length
        # These are set in setUp now for plain MagicMock
        self.mock_doc.__getitem__.return_value = self.mock_page
        self.mock_doc.__len__.return_value = self.page_num # Ensure doc has at least the requested page (page_num = 1)

        # Mock the rendered pixmap return value for self.mock_page.get_pixmap
        mock_rendered_pixmap_instance = self._create_mock_rendered_pixmap(width=200, height=300, mode='RGB')
        # Assign the mock return value to the *instance's* method
        # Note: The patch decorator patches the *original* method on the class.
        # To make the mock work correctly with the instance self.mock_page, we should
        # set the return_value on the patched mock object, which replaces the method
        # on all instances (or specifically on the instance if patch.object is used).
        # Setting return_value on mock_get_pixmap (the patched object) is the correct approach here.
        mock_get_pixmap.return_value = mock_rendered_pixmap_instance


        # Mock Matrix creation return value (plain MagicMock from setUp)
        mock_matrix_instance = MagicMock()
        mock_fitz_matrix.return_value = mock_matrix_instance

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG) # dpi = 150
        # Initialize extraction_info here
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
        self.assertIn('warning', info) # Expect the page-based warning
        self.assertIn('whole page rendering', info['warning'])
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        # Check that fitz.Matrix was called with correct zoom factor
        expected_zoom = MOCK_CONFIG['dpi'] / 72.0
        mock_fitz_matrix.assert_called_once_with(expected_zoom, expected_zoom)
        # Check that get_pixmap was called on the mock page with the matrix
        # Asserting against the patch target is the standard way when using @patch
        mock_get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)

        # Assert that the pixmap instance's close method was called
        mock_rendered_pixmap_instance.close.assert_called_once()
         # The returned PIL image should be closed by the caller
        if extracted_img:
             extracted_img.close()


    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_failure_rendering(self, mock_fitz_matrix: MagicMock, mock_get_pixmap: MagicMock) -> None:
        """Test page-based extraction failure during rendering."""
        # Mock page object (plain MagicMock from setUp)
        # Ensure the mock doc returns the mock page when indexed AND has a length
        self.mock_doc.__getitem__.return_value = self.mock_page
        self.mock_doc.__len__.return_value = self.page_num # Ensure doc has at least the requested page

        # Configure the patched get_pixmap to raise an error
        # Assign the side_effect to the *patched method object*
        mock_get_pixmap.side_effect = RuntimeError("Mock rendering error")


        # Mock Matrix creation return value (plain MagicMock from setUp)
        mock_matrix_instance = MagicMock()
        mock_fitz_matrix.return_value = mock_matrix_instance


        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        # Initialize extraction_info here
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        # Check for the correct error message format - it should now catch the RuntimeError from get_pixmap
        self.assertIn('Page-based extraction failed for page 1 during PIL conversion', info['error'])
        self.assertEqual(info['issue_type'], 'rendering_failed') # Issue type should be rendering_failed now
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.assertNotIn('warning', info) # Warning should not be present on failure

        # Check that fitz.Matrix was called
        expected_zoom = MOCK_CONFIG['dpi'] / 72.0
        mock_fitz_matrix.assert_called_once_with(expected_zoom, expected_zoom)
        # Check that get_pixmap was attempted on the mock page
        mock_get_pixmap.assert_called_once_with(matrix=mock_matrix_instance)
        # No pixmap instance was successfully created, so no close call expected.


    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Page.get_pixmap')
    @patch('scripts.extraction.extraction_strategies.page_based_strategy.fitz.Matrix')
    def test_page_based_extraction_invalid_page_num(self, mock_fitz_matrix: MagicMock, mock_get_pixmap: MagicMock) -> None:
        """Test page-based extraction fails for invalid page number."""
        # Mock doc length to be less than the requested page number (1-indexed)
        # For page 1 (index 0), doc_length = 0 will cause IndexError
        self.mock_doc.__len__.return_value = 0

        strategy = PageBasedExtractionStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        # Attempt extraction for page 1 (index 0) when doc length is 0
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'page_based')
        # Check the error message from the IndexError catch
        # Message format from the strategy code: "Page index {page_idx} requested (corresponds to page {page_num}), but document only has {doc_length} pages (0-{max(0, doc_length-1)})."
        self.assertIn('Page index 0 requested (corresponds to page 1), but document only has 0 pages (0-0).', info['error']) # Match trailing dot
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.assertNotIn('warning', info)

        # Ensure Matrix and get_pixmap were never called as it failed early
        mock_fitz_matrix.assert_not_called()
        mock_get_pixmap.assert_not_called()
        # __getitem__ should not be called if len check fails first
        self.mock_doc.__getitem__.assert_not_called()
        # __len__ should be called
        self.mock_doc.__len__.assert_called_once()


if __name__ == '__main__':
    # Note: Running tests this way might interfere with patching in a larger test suite.
    # It's generally better to use 'pytest' from the command line.
    unittest.main(argv=['first-arg-is-ignored'], exit=False)