# scripts/extraction/extraction_strategies/standard_strategy.py

"""Standard image extraction strategy using PyMuPDF Pixmap."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple
# Import MagicMock for type checking in finally block
from unittest.mock import MagicMock

from .base_strategy import BaseExtractionStrategy

logger = logging.getLogger(__name__)

class StandardExtractionStrategy(BaseExtractionStrategy):
    """Standard extraction method using PyMuPDF's Pixmap."""

    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt standard image extraction.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple.
            page_num: The 1-indexed page number.
            extraction_info: Dictionary to update with extraction details.

        Returns:
            Tuple of (PIL Image object or None, updated extraction info dict).
        """
        xref = img_info[0]
        extraction_info['extraction_method'] = 'standard'
        extracted_image = None
        pix = None # Initialize pix

        try:
            # Extract the image
            pix = fitz.Pixmap(pdf_document, xref)

            # Convert to PIL Image
            # PyMuPDF Pixmap.samples is bytes. Mode depends on n and alpha.
            # Determine the correct PIL mode based on PyMuPDF's structure
            if pix.n == 1 and pix.alpha == 0: # Gray
                 pil_image = Image.frombytes("L", [pix.width, pix.height], pix.samples)
            elif pix.n == 3 and pix.alpha == 0: # RGB
                 pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            elif pix.n == 4 and pix.alpha == 0 and pix.colorspace == fitz.csCMYK: # CMYK
                 pil_image = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                 pil_image = pil_image.convert("RGB") # Convert CMYK to RGB for consistency
            elif pix.n == 4 and pix.alpha == 1: # RGBA
                 pil_image = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
            else: # Handle other potential or unexpected formats
                 # Attempt a conversion to RGB as a fallback
                 try:
                      pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                      logger.debug(f"Attempted generic RGB frombytes for colorspace {pix.colorspace} n={pix.n} alpha={pix.alpha}")
                 except Exception as e_conv:
                       # If conversion fails, log and treat as extraction failure
                       raise RuntimeError(f"Could not convert pixmap samples to PIL Image (unsupported format {pix.n} channels, alpha={pix.alpha}): {e_conv}") from e_conv


            # Free the pixmap memory after converting to PIL
            pix = None # free memory


            # Check minimum size AFTER conversion
            if not self._check_min_size(pil_image, extraction_info):
                # _check_min_size populates error and issue_type
                extraction_info['success'] = False # Explicitly set success to False on failure
                # Close the PIL image as we are returning None
                if isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close'):
                     try: pil_image.close()
                     except Exception: pass
                return None, extraction_info # Return None immediately

            # If all checks pass, set extracted_image and success
            extracted_image = pil_image
            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Standard extraction successful for xref {xref}")

        except Exception as e:
            error = f"Standard extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"

        finally:
            # Ensure PyMuPDF pixmap is explicitly closed if it wasn't freed already
            # This is important for memory management
            if pix is not None and isinstance(pix, (fitz.Pixmap, MagicMock)) and hasattr(pix, 'close') and not getattr(pix.close, 'called', False):
                try:
                    pix.close()
                except Exception: pass

        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info