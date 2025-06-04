# scripts/extraction/extraction_strategies/alternate_colorspace_strategy.py

"""Image extraction strategy using PyMuPDF Pixmap with alternate colorspace handling."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple
# Import MagicMock for isinstance checks in finally block
from unittest.mock import MagicMock

from .base_strategy import BaseExtractionStrategy

logger = logging.getLogger(__name__)

class AlternateColorspaceExtractionStrategy(BaseExtractionStrategy):
    """Extraction method using PyMuPDF's Pixmap with explicit colorspace conversion."""

    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt extraction with explicit colorspace conversion.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple.
            page_num: The 1-indexed page number.
            extraction_info: Dictionary to update with extraction details.

        Returns:
            Tuple of (PIL Image object or None, updated extraction info dict).
        """
        xref = img_info[0]
        extraction_info['extraction_method'] = 'pixmap_alternate_colorspace'
        extracted_image = None
        pix = None # Initialize pix
        pix_rgb = None # Initialize pix_rgb
        pil_image = None # Initialize pil_image

        try:
            # Get the Pixmap
            pix = fitz.Pixmap(pdf_document, xref)

            # Attempt conversion to RGB if it's not already RGB or Gray (n-alpha < 4)
            # Check explicitly for common problematic colorspaces or alpha
            # Using n and alpha check is more robust than just colorspace name
            if pix.n - pix.alpha < 3 or pix.alpha > 0: # If not RGB (n=3, alpha=0) or if has alpha
                try:
                    pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                    # Use the new RGB pixmap samples
                    pil_image = Image.frombytes("RGB", [pix_rgb.width, pix_rgb.height], pix_rgb.samples)
                except Exception as conv_error:
                    # If conversion fails, log and raise to be caught below
                    raise RuntimeError(f"Colorspace conversion to RGB failed: {conv_error}") from conv_error
            else:
                 # If already RGB, use original pixmap samples directly
                 pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Free the original pixmap memory immediately after its samples are used
            if pix is not None and isinstance(pix, (fitz.Pixmap, MagicMock)) and hasattr(pix, 'close'):
                 try: pix.close()
                 except Exception: pass
            pix = None # Set to None *after* closing


            # Free the converted pixmap memory immediately after its samples are used (if it was created)
            if pix_rgb is not None and isinstance(pix_rgb, (fitz.Pixmap, MagicMock)) and hasattr(pix_rgb, 'close'):
                 try: pix_rgb.close()
                 except Exception: pass
            pix_rgb = None # Set to None *after* closing


            # Check minimum size
            if not self._check_min_size(pil_image, extraction_info):
                # _check_min_size populates error and issue_type
                extraction_info['success'] = False # Explicitly set success to False on failure
                # Close the PIL image as we are returning None
                if isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close'):
                     try: pil_image.close()
                     except Exception: pass
                return None, extraction_info # Return None immediately

            extracted_image = pil_image
            extraction_info['success'] = True # Set success to True only if extraction and size check pass
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Alternate colorspace extraction successful for xref {xref}")

        except Exception as e:
            error = f"Alternate colorspace extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"
            # If an exception occurred after pil_image was created but before it was returned, close it
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
            # Safety net: Ensure any pixmaps that were *not* closed in the try block get closed here.
            # This should ideally not be necessary if the try block logic is correct, but good for robustness.
            # The `not getattr(obj.close, 'called', False)` check is for mocks to avoid double-counting close calls.
            if pix is not None and isinstance(pix, (fitz.Pixmap, MagicMock)) and hasattr(pix, 'close') and not getattr(pix.close, 'called', False):
                try:
                    pix.close()
                except Exception: pass
            if pix_rgb is not None and isinstance(pix_rgb, (fitz.Pixmap, MagicMock)) and hasattr(pix_rgb, 'close') and not getattr(pix_rgb.close, 'called', False):
                try:
                    pix_rgb.close()
                except Exception: pass


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info