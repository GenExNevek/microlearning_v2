# scripts/extraction/extraction_strategies/compression_retry_strategy.py

"""Image extraction strategy attempting to reconstruct from raw data."""

import fitz
from PIL import Image
import io
import logging
from typing import Optional, Dict, Any, Tuple
from unittest.mock import MagicMock # Keep import for clarity

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
        pil_image = None # Initialize pil_image here for finally block


        try:
            # Try extracting raw image data then reconstructing
            # This is the first point of failure if extract_image doesn't return data
            # Ensure pdf_document is not None before calling extract_image
            if pdf_document is None:
                 raise ValueError("PDF document object is None.")

            # This call might raise an exception or return None/empty dict
            # Handle potential exceptions during extract_image call itself
            try:
                img_dict = pdf_document.extract_image(xref)
            except Exception as e:
                error = f"Alternate compression extraction failed for xref {xref} during fitz.extract_image call: {str(e)}"
                logger.debug(error)
                extraction_info['success'] = False
                extraction_info['error'] = error
                extraction_info['issue_type'] = "extraction_failed"
                return None, extraction_info


            # Check if valid data was returned
            if not (img_dict and isinstance(img_dict, dict) and img_dict.get("image")):
                # This is the "no data" path
                error = f"No raw image data in extract_image result for xref {xref}"
                logger.debug(error)
                # No need to raise, just set failure info and return None
                extraction_info['success'] = False
                extraction_info['error'] = error
                extraction_info['issue_type'] = "extraction_failed" # Use extraction_failed for this case too
                return None, extraction_info


            # Valid data was found, proceed to decode with PIL
            img_bytes = img_dict["image"]
            img_ext = img_dict.get("ext", "png").lower() # Default to png if ext is missing

            try:
                # Try to create PIL image from raw bytes
                img_stream = io.BytesIO(img_bytes)
                # Attempt to open directly
                # Provide format hint from extracted extension if it's a known PIL format
                # PIL can often infer the format, but hinting might help some edge cases.
                format_hint = img_ext.upper() if img_ext in ['jpeg', 'png', 'gif', 'tiff', 'bmp'] else None
                pil_image = Image.open(img_stream, format=format_hint)
                pil_image.load()  # Load image data to catch issues early (like corrupt data)

                # Convert to RGB if needed (keep RGBA and L modes as they are common and useful)
                if pil_image.mode not in ["RGB", "RGBA", "L"]:
                     pil_image = pil_image.convert("RGB")

                # Close the byte stream now that PIL has loaded the data
                img_stream.close()


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
                # This is the "invalid data" path (PIL couldn't decode)
                error = f"Alternate compression extraction failed for xref {xref} during image decoding: {str(open_error)}"
                logger.debug(error)
                extracted_image = None # Ensure None is returned
                extraction_info['success'] = False
                extraction_info['error'] = error
                extraction_info['issue_type'] = "decoding_failed" # More specific issue type
                # Ensure pil_image (if partially created) is closed
                if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                     try: pil_image.close()
                     except Exception: pass

        except Exception as e:
            # Catch any other unexpected exceptions
            error = f"Alternate compression extraction failed for xref {xref} with unexpected error: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure None is returned
            extraction_info['success'] = False
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed" # Use extraction_failed for this category
            # Ensure pil_image (if partially created) is closed
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
            # Safety net: Ensure pil_image is closed if it exists and is not the one being returned.
            # The logic within the try/except blocks should handle this, but this is a final safeguard.
            # Simplified check: if object exists and has a close method, try to close it.
            # This handles real PIL Images and mocks.
            # Check if extracted_image is None or is a different object than pil_image
            # The condition `pil_image != extracted_image` handles the case where pil_image *is* the returned image.
            if pil_image is not None and pil_image != extracted_image and hasattr(pil_image, 'close'):
                 try:
                    pil_image.close() # Close real PIL image or mock
                 except Exception:
                     pass # Ignore errors during close


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info