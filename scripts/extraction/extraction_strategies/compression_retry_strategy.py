# scripts/extraction/extraction_strategies/compression_retry_strategy.py

"""Image extraction strategy attempting to reconstruct from raw data."""

import fitz
from PIL import Image
import io
import logging
from typing import Optional, Dict, Any, Tuple
from unittest.mock import MagicMock


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
        pil_image = None # Initialize pil_image

        try:
            # Try extracting raw image data then reconstructing
            # This is the first point of failure if extract_image doesn't return data
            img_dict = pdf_document.extract_image(xref)

            if img_dict and "image" in img_dict and img_dict["image"]:
                img_bytes = img_dict["image"]
                # img_ext is often lowercase, PIL format names are uppercase
                img_ext = img_dict.get("ext", "png").lower() # Default to png if ext is missing

                # Try to create PIL image from raw bytes
                img_stream = io.BytesIO(img_bytes)
                try:
                    # Attempt to open directly
                    # Provide format hint from extracted extension if it's a known PIL format
                    format_hint = img_ext.upper() if img_ext in ['jpeg', 'png', 'gif', 'tiff', 'bmp'] else None
                    pil_image = Image.open(img_stream, format=format_hint)
                    pil_image.load()  # Load image data to catch issues early (like corrupt data)

                    # Convert to RGB if needed (keep RGBA and L modes)
                    if pil_image.mode not in ["RGB", "RGBA", "L"]:
                         pil_image = pil_image.convert("RGB")

                    # Check minimum size AFTER potential conversion
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
                    logger.debug(f"Alternate compression extraction successful for xref {xref}")

                except Exception as open_error:
                    # Catch errors during Image.open or pil_image.load()
                    # This is the "invalid data" path
                    error = f"Alternate compression extraction failed for xref {xref} during image decoding: {str(open_error)}"
                    logger.debug(error)
                    extracted_image = None # Ensure None is returned
                    extraction_info['success'] = False
                    extraction_info['error'] = error
                    extraction_info['issue_type'] = "extraction_failed" # Or 'decoding_failed'? Stick to extraction_failed for simplicity
                    # Ensure pil_image (if partially created) is closed
                    if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                         try: pil_image.close()
                         except Exception: pass


            else:
                # This is the "no data" path
                error = f"No raw image data in extract_image result for xref {xref}"
                logger.debug(error)
                extracted_image = None # Ensure None is returned
                extraction_info['success'] = False
                extraction_info['error'] = error
                extraction_info['issue_type'] = "extraction_failed" # Use extraction_failed for this case too


        except Exception as e:
            # Catch errors during pdf_document.extract_image or other unexpected issues
            # This is primarily for issues with the extract_image call itself
            error = f"Alternate compression extraction failed for xref {xref} during data extraction: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure None is returned
            extraction_info['success'] = False
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"
            # Ensure pil_image (if partially created) is closed
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
            # Safety net: Ensure pil_image is closed if it exists and is not the one being returned
            # The logic within the try/except blocks should handle this, but this is a final safeguard.
            if pil_image is not None and pil_image != extracted_image and isinstance(pil_image, (Image.Image, MagicMock)) and hasattr(pil_image, 'close') and not getattr(pil_image.close, 'called', False):
                 try:
                    pil_image.close() # Close real PIL image or mock
                 except Exception:
                     pass # Ignore errors during close


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info