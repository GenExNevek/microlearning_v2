# scripts/extraction/extraction_strategies/compression_retry_strategy.py

"""Image extraction strategy using PyMuPDF Document.extract_image as a fallback."""

import fitz
from PIL import Image
import io
import logging
from typing import Optional, Dict, Any, Tuple
from .base_strategy import BaseExtractionStrategy

logger = logging.getLogger(__name__)

class CompressionRetryStrategy(BaseExtractionStrategy):
    """
    Fallback strategy: attempt extraction using fitz.Document.extract_image().

    This method extracts the raw compressed image data directly from the PDF stream.
    It bypasses PyMuPDF's Pixmap processing, which can sometimes fail for
    certain compression types or malformed streams. The extracted data is
    then passed to PIL for decoding.
    """

    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt extraction using fitz.Document.extract_image().

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
            # Ensure document is valid
            if pdf_document is None:
                 raise ValueError("PDF document object is None.")

            # Use extract_image() which extracts the raw compressed data
            # This method might return an empty dict or None if data is not accessible/valid
            img_dict = pdf_document.extract_image(xref)

            # Check if extraction yielded valid data
            if not (img_dict and isinstance(img_dict, dict) and img_dict.get("image")):
                raise RuntimeError("No raw image data found in extract_image result.")

            img_bytes = img_dict["image"]
            img_ext = img_dict.get("ext", "unknown") # Get extension hint if available

            # Attempt to open the image data using PIL
            # Use a BytesIO wrapper for the binary data
            # Pass format hint to PIL if available, can help with certain formats
            try:
                # Use io.BytesIO directly with Image.open
                pil_image = Image.open(io.BytesIO(img_bytes))
                # Load the image data to ensure it's decoded before closing BytesIO/returning
                pil_image.load()
            except Exception as decode_error:
                # Catch specific PIL errors during opening/loading
                raise RuntimeError(f"Error during image decoding: {decode_error}") from decode_error


            # Check minimum size before returning
            # Use the helper method from BaseStrategy
            if not self._check_min_size(pil_image, extraction_info):
                # _check_min_size populates error and issue_type
                extraction_info['success'] = False # Explicitly set success to False on failure
                # Close the PIL image as we are returning None
                if isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close'):
                     try: pil_image.close()
                     except Exception: pass
                return None, extraction_info # Return None immediately


            # If all steps pass, set extracted_image and success
            # pil_image must be created and loaded by now if no exception occurred
            if pil_image is None:
                 # This should not happen, but defensive check
                 raise RuntimeError("PIL Image not created after decoding.")


            # Optionally convert to a standard mode if needed (e.g., 'P' to 'RGB')
            # This improves compatibility but might slightly alter appearance for some images
            # Leaving this off for now to preserve original data as much as possible,
            # relying on the main processing loop to handle mode conversion later if necessary.
            # The standard strategy handles common conversions (CMYK to RGB). This strategy
            # might yield images in less common modes if PIL supports them.
            # Let's convert paletted images to RGB as they are common and often cause issues.
            if pil_image.mode == 'P':
                 try:
                      # Convert paletted to RGB or RGBA if it has transparency (not common for P)
                      # PIL convert('RGB') handles palette mapping
                      temp_image = pil_image.convert('RGB')
                      # Close the original paletted image
                      if pil_image is not None and hasattr(pil_image, 'close') and pil_image != temp_image:
                           try: pil_image.close()
                           except Exception: pass
                      pil_image = temp_image # Update pil_image to the converted one
                 except Exception as convert_error:
                      # Log a warning, but don't necessarily fail extraction
                      logger.warning(f"Could not convert paletted image xref {xref} to RGB: {convert_error}")
                      # Keep the original paletted image


            extracted_image = pil_image
            extraction_info['success'] = True # Set success to True only if extraction, decoding, and size pass
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Alternate compression extraction successful for xref {xref}")


        except Exception as e:
            # Catch any errors during extract_image, PIL open/load, or size check failure
            error = f"Alternate compression extraction failed for xref {xref}: {str(e)}"
            # Check if the error specifically indicates a decoding problem
            if "image decoding" in str(e):
                 extraction_info['issue_type'] = "decoding_failed"
            elif "Image too small" in str(e):
                 # Size check error already sets issue_type in _check_min_size,
                 # but catch generic Exception ensures it's also caught here
                 extraction_info['issue_type'] = extraction_info.get('issue_type', 'size_issues') # Keep if already set
            else:
                 extraction_info['issue_type'] = "extraction_failed"

            logger.debug(error)
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error

            # If pil_image was created but an exception occurred before it was returned, close it
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
            # No PyMuPDF Pixmaps are used in this strategy, so no pix.close() needed here.
            pass # No explicit cleanup needed in finally for this strategy as PIL images are handled in try/except


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info