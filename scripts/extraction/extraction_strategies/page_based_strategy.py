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
                 # This case should ideally be caught before calling, but defensive check.
                 # Raising ValueError here to be caught by the general exception handler.
                 raise ValueError("PDF document object is None.")

            # Check page range defensively and get the page object.
            try:
                 doc_length = len(pdf_document) # This call might fail
                 if not (0 <= page_idx < doc_length):
                      # Use max(0, doc_length - 1) for the upper bound of the 0-indexed range string
                      # to handle doc_length = 0 correctly (range becomes 0-0).
                      error_msg = (f"Page index {page_idx} requested (corresponds to page {page_num}), "
                                   f"but document only has {doc_length} pages (0-{max(0, doc_length - 1)}).")
                      raise IndexError(error_msg)
                 page = pdf_document[page_idx] # This call might also fail
                 if page is None: # Defensive check if getitem returns None
                      raise ValueError(f"PDF document returned None for page index {page_idx}.")
                 logger.debug(f"Successfully accessed page {page_num} (index {page_idx}) for rendering.")

            except (IndexError, ValueError, RuntimeError, Exception) as page_access_error: # Catch broader exceptions for doc access
                 error = f"Page-based extraction failed for page {page_num} during page access: {str(page_access_error)}"
                 logger.debug(error)
                 extraction_info['success'] = False
                 extraction_info['error'] = str(page_access_error) # Use the specific error from IndexError/ValueError
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
            matrix = fitz.Matrix(zoom_factor, zoom_factor)

            # Use a try-except block around Pixmap rendering
            try:
                # This call might fail (e.g., invalid PDF data on page)
                pix = page.get_pixmap(matrix=matrix)
                # Safely determine pixmap mode for logging
                pix_alpha_val = getattr(pix, 'alpha', 0) # Default to 0 if alpha attribute doesn't exist or is not int
                if not isinstance(pix_alpha_val, int): # Handle if alpha is not an int (e.g. MagicMock)
                    pix_alpha_val = 0 # Fallback for non-integer alpha
                pix_mode_str = 'RGBA' if pix_alpha_val > 0 else 'RGB'
                logger.debug(f"Successfully rendered page {page_num} to pixmap ({getattr(pix, 'width', 0)}x{getattr(pix, 'height', 0)}, mode={pix_mode_str}).")


            except Exception as rendering_error:
                 error = f"Page-based extraction failed for page {page_num} during pixmap rendering: {str(rendering_error)}"
                 logger.debug(error)
                 # extracted_image is already None
                 extraction_info['success'] = False
                 extraction_info['error'] = error
                 extraction_info['issue_type'] = "rendering_failed"
                 # No pixmap was successfully created, nothing to close here.
                 return None, extraction_info # Return immediately on rendering failure


            # Convert to PIL Image
            try:
                # Assuming get_pixmap typically returns RGB or RGBA for page rendering.
                # Check pix.alpha to determine mode. pix.alpha should be int (0 or 1).
                # Safely get alpha value
                pix_alpha_val = getattr(pix, 'alpha', 0)
                if not isinstance(pix_alpha_val, int): # Handle if alpha is not an int (e.g. MagicMock)
                    pix_alpha_val = 0 # Fallback for non-integer alpha
                mode = "RGBA" if pix_alpha_val > 0 else "RGB"
                pil_image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                logger.debug(f"Successfully converted page {page_num} pixmap to PIL image.")
            except Exception as pil_conv_error:
                 error = f"Page-based extraction failed for page {page_num} during PIL conversion: {str(pil_conv_error)}"
                 logger.debug(error)
                 # extracted_image is already None
                 extraction_info['success'] = False
                 extraction_info['error'] = error
                 extraction_info['issue_type'] = "extraction_failed" # Keep generic extraction_failed for PIL conversion errors
                 # pil_image is None here, pix might exist
                 # Pixmap is closed in the finally block of this try-catch-finally for PIL conversion
                 return None, extraction_info # Return immediately on PIL conversion failure
            finally:
                # Free the pixmap memory immediately after its samples are used by PIL or if conversion fails
                # Use hasattr and try/except for robustness with mocks/unexpected objects
                if pix is not None and hasattr(pix, 'close'):
                     try: pix.close()
                     except Exception: pass # Ignore errors during close
                pix = None # Set to None *after* closing, regardless of success/failure of close


            # If all steps pass, set extracted_image and success
            if pil_image is None:
                 # This should not happen if previous steps succeeded and no exception was raised,
                 # but defensive check. This would be caught by the general exception handler.
                 raise RuntimeError("PIL Image not created after pixmap rendering and conversion, but no specific error was caught.")

            extracted_image = pil_image # pil_image is now the image to be returned
            pil_image = None # Clear local variable to avoid accidental close in general except if it's the returned image

            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            # Adding a warning is good practice as this strategy returns the whole page.
            extraction_info['warning'] = "Used whole page rendering as fallback; image contains entire page."
            logger.debug(f"Page-based extraction successful for page {page_num}")


        except Exception as e:
            # Catch any other unexpected exceptions that weren't specifically handled above
            # This includes the ValueError for pdf_document is None, or RuntimeError from success path.
            error = f"Page-based extraction failed for page {page_num} with unexpected error: {str(e)}"
            logger.error(error, exc_info=True) # Log with stack trace for unexpected errors
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed" # Generic type for unhandled errors
            # Ensure pil_image (if partially created before this catch and not assigned to extracted_image) is closed
            if pil_image is not None and hasattr(pil_image, 'close'): # pil_image here is the local var, not the one to be returned
                 try: pil_image.close()
                 except Exception: pass


        finally:
             # Safety net: Ensure any pixmaps that might not have been closed earlier are closed.
             # This should ideally not be necessary if the try/except/finally logic for pix is correct.
             if pix is not None and hasattr(pix, 'close'):
                 try:
                     pix.close()
                 except Exception: pass # Ignore errors during close


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info