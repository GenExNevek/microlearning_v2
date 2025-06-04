# scripts/extraction/extraction_strategies/compression_retry_strategy.py

"""Image extraction strategy attempting to reconstruct from raw data."""

import fitz
from PIL import Image
import io
import logging
from typing import Optional, Dict, Any, Tuple

from .base_strategy import BaseExtractionStrategy

logger = logging.getLogger(__name__)

class CompressionRetryStrategy(BaseExtractionStrategy):
    """Extraction method trying to reconstruct from raw image data."""

    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt extraction by reconstructing from raw data.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple.
            page_num: The 1-indexed page number.
            extraction_info: Dictionary to update with extraction details.

        Returns:
            Tuple of (PIL Image object or None, updated extraction info dict).
        """
        xref = img_info[0]
        extraction_info['extraction_method'] = 'alternate_compression'
        extracted_image = None
        error = None

        try:
            # Try extracting raw image data then reconstructing
            img_dict = pdf_document.extract_image(xref)

            if img_dict and "image" in img_dict and img_dict["image"]:
                img_bytes = img_dict["image"]
                img_ext = img_dict.get("ext", "png") # Default to png if ext is missing

                # Try to create PIL image from raw bytes
                try:
                    # Attempt to open directly
                    pil_image = Image.open(io.BytesIO(img_bytes))
                    pil_image.load()  # Load image data to catch issues early
                except Exception as open_error:
                    # If direct open fails, try using the reported extension if possible
                    try:
                         # PIL needs a hint for some formats if header is ambiguous
                         format_hint = img_ext.upper() if img_ext.lower() in ['jpeg', 'png', 'gif', 'tiff', 'bmp'] else None
                         if format_hint:
                             pil_image = Image.open(io.BytesIO(img_bytes), format=format_hint)
                             pil_image.load()
                         else:
                             raise open_error # Re-raise if no format hint helps

                    except Exception as format_error:
                        raise format_error # Re-raise if all attempts fail


                # Convert to RGB if needed
                if pil_image.mode not in ["RGB", "RGBA", "L"]: # Allow L (grayscale) as it's common
                     pil_image = pil_image.convert("RGB") # Convert others to RGB

                # Check minimum size
                if not self._check_min_size(pil_image, extraction_info):
                    return None, extraction_info

                extracted_image = pil_image
                extraction_info['success'] = True
                extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
                extraction_info['mode'] = extracted_image.mode
                logger.debug(f"Alternate compression extraction successful for xref {xref}")

            else:
                error = f"No raw image data in extract_image result for xref {xref}"
                logger.debug(error)
                extraction_info['success'] = False
                extraction_info['error'] = error
                extraction_info['issue_type'] = "extraction_failed"


        except Exception as e:
            error = f"Alternate compression extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extraction_info['success'] = False
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"

        return extracted_image, extraction_info
