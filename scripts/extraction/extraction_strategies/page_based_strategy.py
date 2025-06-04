# scripts/extraction/extraction_strategies/page_based_strategy.py

"""Image extraction strategy rendering the whole page as a fallback."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple

from .base_strategy import BaseExtractionStrategy

logger = logging.getLogger(__name__)

class PageBasedExtractionStrategy(BaseExtractionStrategy):
    """Fallback strategy: render page as image and return the whole page."""

    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt extraction by rendering the whole page.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple (used for context, not extraction itself).
            page_num: The 1-indexed page number.
            extraction_info: Dictionary to update with extraction details.

        Returns:
            Tuple of (PIL Image object or None, updated extraction info dict).
        """
        page_idx = page_num - 1
        extraction_info['extraction_method'] = 'page_based'
        extracted_image = None
        error = None

        try:
            # Get the page
            page = pdf_document[page_idx]

            # Render page to pixmap at configurable resolution
            # Using dpi from config, applied as zoom factor
            current_dpi = self.config.get("dpi", 150) # Get DPI from base config
            zoom_factor = current_dpi / 72.0 # 72 is standard PDF point size
            matrix = fitz.Matrix(zoom_factor, zoom_factor)
            pix = page.get_pixmap(matrix=matrix)

            # Convert to PIL Image
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pix = None # free memory

            # Note: We don't check minimum size here, as the result is the entire page.
            # The downstream validation/processing should handle filtering if needed.
            # However, adding a warning is good practice.
            extraction_info['warning'] = "Used whole page rendering as fallback; image contains entire page."

            extracted_image = pil_image
            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Page-based extraction successful for page {page_num}")


        except Exception as e:
            error = f"Page-based extraction failed for page {page_num}: {str(e)}"
            logger.debug(error)
            extraction_info['success'] = False
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"

        return extracted_image, extraction_info
