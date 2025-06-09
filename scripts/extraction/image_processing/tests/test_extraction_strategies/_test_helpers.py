# scripts/extraction/image_processing/tests/test_extraction_strategies/_test_helpers.py

import unittest
from unittest.mock import MagicMock
from PIL import Image
import io
import fitz
from typing import Dict, Any, Optional

# Import ABC and abstractmethod for creating a concrete base class test implementation
from abc import ABC, abstractmethod # Keep for BaseExtractionStrategy context
from scripts.extraction.image_processing.extraction_strategies.base_strategy import BaseExtractionStrategy


# Mock configuration
MOCK_CONFIG = {
    "min_width": 50,
    "min_height": 50,
    "dpi": 150 # For page-based strategy
}

# Helper function to create a dummy PIL image for testing
def create_dummy_image(width=100, height=100, mode='RGB', color='red') -> Optional[Image.Image]:
    """Creates a simple dummy PIL Image."""
    try:
        img = Image.new(mode, (width, height), color=color)
        return img
    except Exception as e:
        print(f"Error creating dummy image: {e}")
        return None

# Helper function to create a mock PyMuPDF Pixmap
def create_mock_pixmap_helper(pil_image: Optional[Image.Image]) -> MagicMock:
    """Creates a MagicMock that simulates a fitz.Pixmap."""
    if pil_image is None:
        return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())

    pil_image_to_process = pil_image # Avoid modifying the input directly if it's used elsewhere

    if pil_image_to_process.mode == 'L':
        rawmode = 'L'; n = 1; alpha = 0; cs = fitz.csGRAY
    elif pil_image_to_process.mode == 'RGB':
        rawmode = 'RGB'; n = 3; alpha = 0; cs = fitz.csRGB
    elif pil_image_to_process.mode == 'RGBA':
        rawmode = 'RGBA'; n = 4; alpha = 1
        cs = MagicMock(name='DeviceRGB'); cs.n = 3
    elif pil_image_to_process.mode == 'CMYK':
        rawmode = 'CMYK'; n = 4; alpha = 0; cs = fitz.csCMYK
    elif pil_image_to_process.mode == 'P':
         rawmode = 'L'; n = 1; alpha = 0
         mock_colorspace = MagicMock(); mock_colorspace.n = n; mock_colorspace.name = 'Indexed'; cs = mock_colorspace
         try:
            pil_image_to_process = pil_image_to_process.convert('L')
         except Exception as e:
             print(f"Warning: Could not convert PIL P mode to L for mocking: {e}")
             try:
                 pil_image_to_process = pil_image.convert('RGB') # Try original image for RGB conversion
                 rawmode = 'RGB'; n = 3; alpha = 0; cs = fitz.csRGB
             except Exception as e2:
                 print(f"Error: Could not convert PIL P mode to RGB either: {e2}")
                 return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())
    else:
        try:
            pil_image_to_process = pil_image_to_process.convert('RGB')
            rawmode = 'RGB'; n = 3; alpha = 0; cs = fitz.csRGB
        except Exception as e:
            print(f"Error: Could not convert PIL image mode {pil_image.mode} to RGB for mocking: {e}")
            return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())

    try:
        samples = pil_image_to_process.tobytes('raw', rawmode)
    except Exception as e:
        print(f"Error getting raw bytes from PIL image (mode={pil_image_to_process.mode}, rawmode={rawmode}) for mocking: {e}")
        return MagicMock(samples=None, width=0, height=0, n=0, alpha=0, colorspace=None, close=MagicMock())

    mock_pix = MagicMock()
    mock_pix.samples = samples
    mock_pix.width = pil_image_to_process.width
    mock_pix.height = pil_image_to_process.height
    mock_pix.n = n
    mock_pix.alpha = alpha
    mock_pix.colorspace = cs
    mock_pix.close = MagicMock()
    return mock_pix

# Helper function to create mock data returned by extract_image
def create_mock_extract_image_data_helper(pil_image: Image.Image, img_ext: str) -> Dict:
    """Creates a dictionary simulating the output of fitz.Document.extract_image."""
    buffer = io.BytesIO()
    try:
        pil_format = img_ext.upper()
        # Work with a temporary image for potential conversions
        temp_pil_image = pil_image
        if temp_pil_image.mode == 'RGBA' and pil_format == 'JPEG':
             temp_pil_image = temp_pil_image.convert('RGB')
        elif temp_pil_image.mode == 'P' and pil_format not in ['PNG', 'GIF', 'TIFF', 'BMP']: # Common formats supporting paletted
             temp_pil_image = temp_pil_image.convert('RGB')

        temp_pil_image.save(buffer, format=pil_format)
        img_bytes = buffer.getvalue()
        return {"ext": img_ext, "image": img_bytes}
    except Exception as e:
        print(f"Error saving dummy image to bytes for mock extract_image (ext={img_ext}, mode={pil_image.mode}): {e}")
        return {}

# Helper function to create a mock pixmap suitable for page rendering results
def create_mock_rendered_pixmap_helper(width: int, height: int, mode='RGB') -> MagicMock:
     """Creates a MagicMock simulating a fitz.Pixmap from page rendering."""
     dummy_page_image = create_dummy_image(width, height, mode)
     if dummy_page_image is None:
         return MagicMock(samples=None, width=0, height=0, alpha=0, close=MagicMock())

     mock_pix = MagicMock()
     try:
         mock_pix.samples = dummy_page_image.tobytes('raw', dummy_page_image.mode)
     except Exception as e:
         print(f"Error getting raw bytes for rendered pixmap mock: {e}")
         mock_pix.samples = None
     mock_pix.width, mock_pix.height = dummy_page_image.size
     mock_pix.alpha = 1 if mode == 'RGBA' else 0
     mock_pix.close = MagicMock()
     dummy_page_image.close()
     return mock_pix

# Define a concrete dummy strategy to test BaseExtractionStrategy methods
class ConcreteDummyExtractionStrategy(BaseExtractionStrategy):
     def extract(self, pdf_document, img_info, page_num, extraction_info):
          return None, extraction_info


class BaseStrategyTestCase(unittest.TestCase):
    def setUp(self):
        """Set up common mocks and test data."""
        self.mock_doc = MagicMock()
        self.mock_page = MagicMock()
        self.page_num = 1
        self.mock_doc.__len__ = MagicMock(return_value=10)
        self.mock_doc.__getitem__ = MagicMock(return_value=self.mock_page)
        self.mock_page.get_pixmap = MagicMock()
        self.mock_img_info = (10, 0, 100, 100, 8, fitz.csRGB, '', '')
        self.extraction_info: Dict[str, Any] = {}

        # Dummy PIL images
        self.dummy_image = create_dummy_image(100, 100, 'RGB', 'blue')
        self.small_image = create_dummy_image(30, 30, 'RGB', 'green')
        self.paletted_image = create_dummy_image(100, 100, 'RGB', 'red')
        if self.paletted_image: # create_dummy_image can return None
            self.paletted_image = self.paletted_image.convert('P')
        self.rgba_image = create_dummy_image(100, 100, 'RGBA', (255, 0, 0, 128))

    def tearDown(self):
        """Clean up dummy images."""
        if self.dummy_image: self.dummy_image.close()
        if self.small_image: self.small_image.close()
        if self.paletted_image: self.paletted_image.close()
        if self.rgba_image: self.rgba_image.close()