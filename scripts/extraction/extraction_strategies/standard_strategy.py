"""Standard image extraction strategy using PyMuPDF Pixmap."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple

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
        error = None

        try:
            # Extract the image
            pix = fitz.Pixmap(pdf_document, xref)

            # Convert to PIL Image
            if pix.n - pix.alpha < 4:  # GRAY or RGB
                pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            else:  # CMYK
                pil_image = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                pil_image = pil_image.convert("RGB")

            pix = None  # free memory

            # Check minimum size
            if not self._check_min_size(pil_image, extraction_info):
                return None, extraction_info

            extracted_image = pil_image
            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Standard extraction successful for xref {xref}")

        except Exception as e:
            error = f"Standard extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extraction_info['success'] = False
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"

        return extracted_image, extraction_info
