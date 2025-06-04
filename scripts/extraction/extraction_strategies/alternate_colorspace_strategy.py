# scripts/extraction/extraction_strategies/alternate_colorspace_strategy.py

"""Image extraction strategy using PyMuPDF Pixmap with alternate colorspace handling."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple

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
        error = None

        try:
            # Try with explicit colorspace conversion
            pix = fitz.Pixmap(pdf_document, xref)

            # Force conversion to RGB
            if pix.colorspace:  # If there's a colorspace, convert to RGB
                pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                pil_image = Image.frombytes("RGB", [pix_rgb.width, pix_rgb.height], pix_rgb.samples)
                pix_rgb = None  # free memory
            else:
                 # Assume grayscale or another format PIL can handle directly after frombytes
                 # Attempt to convert to RGB anyway
                pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            pix = None  # free memory

            # Check minimum size
            if not self._check_min_size(pil_image, extraction_info):
                return None, extraction_info

            extracted_image = pil_image
            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Alternate colorspace extraction successful for xref {xref}")

        except Exception as e:
            error = f"Alternate colorspace extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extraction_info['success'] = False
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"


        return extracted_image, extraction_info