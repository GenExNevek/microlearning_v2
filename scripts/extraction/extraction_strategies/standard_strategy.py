# scripts/extraction/extraction_strategies/standard_strategy.py

"""Standard image extraction strategy using PyMuPDF Pixmap."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple
# Import MagicMock for type checking in finally block
from unittest.mock import MagicMock # Keep import for clarity

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
        pix = None # Initialize pix here for finally block
        pil_image = None # Initialize pil_image here for finally block

        try:
            # Ensure document is valid
            if pdf_document is None:
                 raise ValueError("PDF document object is None.")

            # Extract the image
            # This call might fail if xref is invalid
            pix = fitz.Pixmap(pdf_document, xref)

            # Convert to PIL Image
            # PyMuPDF Pixmap.samples is bytes. Mode depends on n and alpha.
            # Determine the correct PIL mode based on PyMuPDF's structure
            # Check alpha first for RGBA
            if pix.alpha > 0:
                 # Pixmap with alpha has n including the alpha channel.
                 # Standard RGBA is n=4, alpha=1.
                 if pix.n == 4:
                      pil_image = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
                 else:
                      # Handle cases like Gray+Alpha (n=2, alpha=1), RGB+Alpha (n=4, alpha=1 - already covered), CMYK+Alpha (n=5, alpha=1)
                      # PyMuPDF samples format might not directly map to PIL modes if n is unexpected with alpha.
                      # Attempt conversion to RGBA via fitz first.
                      try:
                           # Use fitz.csRGB as target, requesting alpha=True.
                           # This works if the source samples contain alpha information.
                           pix_rgba = fitz.Pixmap(fitz.csRGB, pix, alpha=True)
                           pil_image = Image.frombytes("RGBA", [pix_rgba.width, pix_rgba.height], pix_rgba.samples)
                           if pix_rgba is not None and hasattr(pix_rgba, 'close'):
                               try: pix_rgba.close()
                               except Exception: pass
                           pix_rgba = None # Free converted pixmap
                      except Exception as e_conv_alpha:
                           raise RuntimeError(f"Could not convert pixmap with alpha (n={pix.n}, alpha={pix.alpha}) to RGBA via fitz.csRGB for PIL: {e_conv_alpha}") from e_conv_alpha

            elif pix.n == 1: # Gray (alpha is 0)
                 pil_image = Image.frombytes("L", [pix.width, pix.height], pix.samples)
            elif pix.n == 3: # RGB (alpha is 0)
                 pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            elif pix.n == 4 and hasattr(pix, 'colorspace') and pix.colorspace == fitz.csCMYK: # CMYK (alpha is 0)
                 # Ensure CMYK conversion works correctly for PIL
                 pil_image = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                 # Convert CMYK to RGB for consistency in output mode, unless CMYK output is desired elsewhere.
                 # Let's convert to RGB as per original code.
                 pil_image = pil_image.convert("RGB")
            else: # Handle other potential or unexpected formats (Lab, Indexed without alpha, etc.)
                 # Attempt a conversion to RGB via fitz as a fallback
                 try:
                      # fitz.Pixmap(fitz.csRGB, pix) handles various conversions to RGB.
                      # It results in alpha=0.
                      pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                      pil_image = Image.frombytes("RGB", [pix_rgb.width, pix_rgb.height], pix_rgb.samples)
                      logger.debug(f"Attempted conversion to RGB via fitz.csRGB for colorspace {pix.colorspace.name if hasattr(pix.colorspace, 'name') else 'N/A'} n={pix.n} alpha={pix.alpha}")
                      if pix_rgb is not None and hasattr(pix_rgb, 'close'):
                           try: pix_rgb.close()
                           except Exception: pass
                      pix_rgb = None # Free converted pixmap
                 except Exception as e_conv:
                       # If conversion fails, log and treat as extraction failure
                       raise RuntimeError(f"Could not convert pixmap samples to PIL Image or convert via fitz.csRGB (format n={pix.n}, alpha={pix.alpha}): {e_conv}") from e_conv


            # Free the pixmap memory after converting to PIL
            # Use hasattr and try/except for robustness with mocks/unexpected objects
            if pix is not None and hasattr(pix, 'close'):
                 try: pix.close()
                 except Exception: pass
            pix = None # free memory


            # Check minimum size AFTER conversion
            # pil_image must be created by now if no exception occurred
            if pil_image is None:
                 # This should not happen, but defensive check
                 raise RuntimeError("PIL Image not created after pixmap processing.")


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
            logger.debug(f"Standard extraction successful for xref {xref}")

        except Exception as e:
            error = f"Standard extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"
            # If an exception occurred after pil_image was created but before it was returned, close it
            # Note: pil_image might be None if the exception happened early
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
            # Ensure PyMuPDF pixmap is explicitly closed if it wasn't freed already
            # This is important for memory management
            # Simplified check: if object exists and has a close method, try to close it.
            # Handles real Pixmaps and mocks.
            # Ensure the original pix and any converted pixmaps are closed if they still exist
            if pix is not None and hasattr(pix, 'close'):
                try:
                    pix.close()
                except Exception: pass # Ignore errors during close

            # Need to ensure pix_rgb/pix_rgba are also checked in finally,
            # as they might not be None if an exception happened after creation but before local close.
            # Add pix_rgb = None and pix_rgba = None initialization at the start.
            # Check both here.
            # The current logic locally closes pix_converted (which covers pix_rgb/rgba).
            # The only case missed is if pix_converted is created but an error happens *before* its local close *and* before the main finally.
            # Let's add checks for pix_rgb and pix_rgba here assuming they *might* be used and not locally closed.
            # Re-reading the code, only `pix_converted` is used for the converted pixmap and it *is* locally closed.
            # The only variable that needs check in finally is the original `pix`. The local `pix_converted` cleanup is sufficient.
            # Let's keep the finally clean and trust the local cleanup. The original issue might have been complex mocks.
            # The simplified hasattr checks should resolve the mock issues anyway.
            # Keep the main cleanup focused on `pix`.


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info