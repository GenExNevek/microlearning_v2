# scripts/extraction/extraction_strategies/page_based_strategy.py

"""Image extraction strategy rendering the whole page as a fallback."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple
# Import MagicMock not strictly needed for logic, but can help with isinstance in tests

from .base_strategy import BaseExtractionStrategy

logger = logging.getLogger(__name__)

class PageBasedExtractionStrategy(BaseExtractionStrategy):
    """Fallback strategy: render page as image and return the whole page."""

    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple, # img_info is passed but typically not used for extraction itself in this strategy
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt extraction by rendering the whole page.

        This strategy is a last resort for cases where image-specific extraction
        methods fail. It renders the entire page containing the image as a single
        image, effectively capturing the image as part of the page content.
        The image boundaries on the page are not considered by this strategy,
        and the entire page image is returned.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple (used for context, not extraction itself).
            page_num: The 1-indexed page number.
            extraction_info: Dictionary to update with extraction details.

        Returns:
            Tuple of (PIL Image object or None, updated extraction info dict).
        """
        # Page number is 1-indexed, PyMuPDF page index is 0-indexed
        page_idx = page_num - 1
        extraction_info['extraction_method'] = 'page_based'
        extracted_image = None
        pix = None # Initialize pixmap
        pil_image = None # Initialize pil_image


        try:
            # Ensure document is valid
            if pdf_document is None:
                 raise ValueError("PDF document object is None.")

            # Check page range defensively and get the page object.
            # Use a try-except block for accessing document length and page,
            # as these can fail on corrupted documents.
            try:
                 doc_length = len(pdf_document) # This call might fail
                 # Using >= and < handles 0-indexed correctly relative to doc_length
                 if page_idx < 0 or page_idx >= doc_length:
                      raise IndexError(f"Page index {page_idx} requested (corresponds to page {page_num}), but document only has {doc_length} pages (0-{max(0, doc_length-1)}).")
                 page = pdf_document[page_idx] # This call might also fail
                 if page is None: # Defensive check if getitem returns None
                      raise ValueError(f"PDF document returned None for page index {page_idx}")
                 logger.debug(f"Successfully accessed page {page_num} (index {page_idx}) for rendering.")

            except Exception as page_access_error:
                 # Catch errors related to accessing document length or page object
                 error = f"Page-based extraction failed for page {page_num} during page access: {str(page_access_error)}"
                 logger.debug(error)
                 extraction_info['success'] = False
                 extraction_info['error'] = error
                 # MODIFIED: Standardize issue_type to 'extraction_failed' as per solution
                 extraction_info['issue_type'] = "extraction_failed"
                 return None, extraction_info


            # Render page to pixmap at configurable resolution
            current_dpi = self.config.get("dpi", 150)
            # Validate DPI: must be numeric and positive
            if not isinstance(current_dpi, (int, float)) or current_dpi <= 0:
                 logger.warning(f"Invalid DPI setting '{current_dpi}' ({type(current_dpi)}) for page rendering. Using default 150.")
                 current_dpi = 150

            zoom_factor = current_dpi / 72.0
            # Use a try-except block around Pixmap rendering
            try:
                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                # This call might fail (e.g., invalid PDF data on page)
                pix = page.get_pixmap(matrix=matrix)
                logger.debug(f"Successfully rendered page {page_num} to pixmap ({pix.width}x{pix.height}, mode={'RGBA' if pix.alpha > 0 else 'RGB'}).")

            except Exception as rendering_error:
                 # Specific error type for rendering failures
                 error = f"Page-based extraction failed for page {page_num} during pixmap rendering: {str(rendering_error)}"
                 logger.debug(error)
                 extracted_image = None # Ensure None on this failure path
                 extraction_info['success'] = False
                 extraction_info['error'] = error
                 extraction_info['issue_type'] = "rendering_failed"
                 # No pixmap was successfully created, nothing to close here.
                 return None, extraction_info # Return immediately on rendering failure


            # Convert to PIL Image
            # Assuming get_pixmap typically returns RGB or RGBA for page rendering.
            # Check pix.alpha to determine mode.
            try:
                mode = "RGBA" if pix.alpha > 0 else "RGB"
                pil_image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                logger.debug(f"Successfully converted page {page_num} pixmap to PIL image.")
            except Exception as pil_conv_error:
                 error = f"Page-based extraction failed for page {page_num} during PIL conversion: {str(pil_conv_error)}"
                 logger.debug(error)
                 extracted_image = None # Ensure None on this failure path
                 extraction_info['success'] = False
                 extraction_info['error'] = error
                 extraction_info['issue_type'] = "extraction_failed" # Keep generic extraction_failed for PIL conversion errors
                 # Ensure pixmap is closed if PIL conversion fails *after* pix is created
                 if pix is not None and hasattr(pix, 'close'):
                     try: pix.close()
                     except Exception: pass
                 pix = None # Ensure reference is cleared
                 return None, extraction_info # Return immediately on PIL conversion failure


            # Free the pixmap memory immediately after its samples are used by PIL
            # Use hasattr and try/except for robustness with mocks/unexpected objects
            if pix is not None and hasattr(pix, 'close'):
                 try: pix.close()
                 except Exception: pass
            pix = None # Set to None *after* closing


            # Note: We don't check minimum size here, as the result is the entire page.
            # The downstream validation/processing should handle filtering if needed.
            # Adding a warning is good practice as this strategy returns the whole page.
            # Only add the warning if the extraction was successful.
            # Warning is added after success check below.


            # If all steps pass, set extracted_image and success
            # pil_image must be created by now if no exception occurred
            if pil_image is None:
                 # This should not happen if previous steps succeeded, but defensive check
                 raise RuntimeError("PIL Image not created after pixmap rendering or conversion.")

            extracted_image = pil_image
            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            extraction_info['warning'] = "Used whole page rendering as fallback; image contains entire page." # Add warning on success
            logger.debug(f"Page-based extraction successful for page {page_num}")


        except Exception as e:
            # Catch any other unexpected exceptions that weren't specifically handled above
            error = f"Page-based extraction failed for page {page_num} with unexpected error: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed" # Generic type for unhandled errors
            # Ensure pil_image (if partially created before this catch) is closed
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
             # Safety net: Ensure any pixmaps that might not have been closed earlier are closed.
             # This should ideally not be necessary if the try block logic is correct.
             # Handles real Pixmaps and mocks.
             if pix is not None and hasattr(pix, 'close'):
                 try:
                     pix.close()
                 except Exception: pass # Ignore errors during close


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info