# scripts/extraction/extraction_strategies/alternate_colorspace_strategy.py

"""Image extraction strategy using PyMuPDF Pixmap with alternate colorspace handling."""

import fitz
from PIL import Image
import logging
from typing import Optional, Dict, Any, Tuple
# Import MagicMock for isinstance checks in finally block
from unittest.mock import MagicMock # Keep import for clarity, although not strictly used in isinstance anymore

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
        pix = None # Initialize pix
        pix_converted = None # Use a single variable for the converted pixmap (RGB or RGBA)
        pil_image = None # Initialize pil_image

        try:
            # Ensure document is valid
            if pdf_document is None:
                 raise ValueError("PDF document object is None.")

            # Get the Pixmap
            # This call might fail if xref is invalid
            pix = fitz.Pixmap(pdf_document, xref)

            # Determine if conversion is needed and what type (RGB or RGBA)
            # This strategy focuses on converting potentially problematic or non-standard
            # colorspaces (like Indexed/Paletted, Lab) into standard RGB or RGBA.
            # It should also handle images that might be Gray or RGB but have alpha,
            # ensuring the alpha channel is preserved by converting to RGBA.

            # If pix has alpha, convert to RGBA to preserve it.
            if pix.alpha > 0:
                # Use fitz.csRGBA for conversion when alpha is present
                # Note: fitz.csRGBA is just fitz.csRGB with alpha=1 flag, but Pixmap(fitz.csRGBA, pix) handles it.
                # Actually, Pixmap(fitz.csRGB, pix, alpha=True) is the way to explicitly request alpha.
                # But fitz.Pixmap(fitz.csRGBA, pix) might work if csRGBA exists (it doesn't, but csRGB with alpha flag does).
                # Let's use fitz.csRGB and explicitly handle the alpha flag if needed for conversion.
                # A simpler way: If pix.alpha > 0, assume it needs RGBA conversion *via fitz*, then PIL.
                # If pix.alpha == 0, assume it needs RGB conversion *via fitz*, then PIL.
                # This strategy attempts conversion regardless, assuming the input is something Standard missed.
                pix_converted = fitz.Pixmap(fitz.csRGB, pix, alpha=pix.alpha > 0) # Create new pixmap, preserving or adding alpha if needed
                # The above might not work as intended for converting non-RGB+alpha to RGBA.
                # The most reliable conversion targets are fitz.csRGB and fitz.csGRAY.
                # To get RGBA, you typically convert to fitz.csRGB and then add alpha *if* the source had it.
                # Let's convert to fitz.csRGB first, then check alpha.
                temp_pix_rgb = fitz.Pixmap(fitz.csRGB, pix) # Convert base colorspace to RGB
                if pix.alpha > 0:
                    # If original had alpha, create an RGBA pixmap from the RGB data and the original alpha.
                    # This requires access to the original alpha channel data, which isn't directly exposed
                    # in the simple Pixmap object samples unless alpha=1 from the start.
                    # A safer approach is to use Pixmap(fitz.csRGBA, pix) IF that worked, or Pixmap.get_pixmap(alpha=True).
                    # Let's try the simplest fitz approach that usually works: Pixmap(colorspace, pixmap).
                    # fitz.csRGBA doesn't exist. Convert to fitz.csRGB. If alpha > 0, manually build RGBA samples or rely on PIL convert.
                    # If Pixmap(fitz.csRGB, pix) is created, its alpha will be 0. We lose original alpha.
                    # The goal is to handle alternate colorspaces, preserving alpha if present.
                    # Let's try: if alpha > 0, convert to RGBA via fitz. If alpha is 0, convert to RGB via fitz.
                    # Pixmap(fitz.csRGB, pix) correctly converts other CS to RGB.
                    # Pixmap(fitz.csRGB, pix, alpha=1) forces an alpha channel, often transparent.
                    # Pixmap.get_pixmap(alpha=True) is for *rendering*, not image extraction.
                    # Back to the original approach: convert to RGB via Pixmap(fitz.csRGB, pix).
                    # If original had alpha, we need to manually re-add it or use a different fitz method.
                    # Let's reconsider the standard Pixmap(doc, xref) attributes. `pix.samples` contains alpha if `pix.alpha > 0`.
                    # So, if `pix.alpha > 0`, `pix.n` will include the alpha channel count.
                    # e.g., RGB+Alpha PDF -> fitz.Pixmap has n=4, alpha=1. CMYK+Alpha -> n=5, alpha=1.
                    # The check `if pix.n - pix.alpha < 3 or pix.alpha > 0:` is intended to catch these non-standard or alpha cases.
                    # `pix.n - pix.alpha` gives the number of color channels. If < 3 (Gray or Palette etc.) OR alpha > 0.
                    # This check seems reasonable for identifying images that might need processing beyond simple RGB/Gray/CMYK.
                    # Let's go back to the original check and convert logic, but fix the RGBA handling.
                    # If the original pix has alpha, the samples include it. We should convert samples to PIL *as RGBA*.
                    # If the original pix has no alpha, the samples don't. We should convert samples to PIL *as RGB*.
                    # The *fitz conversion* `fitz.Pixmap(fitz.csRGB, pix)` creates a *new* pixmap with RGB colorspace and alpha=0.
                    # So if the original had alpha, converting with `fitz.csRGB` *loses* the alpha.
                    # Correct approach:
                    # 1. Get original pixmap `pix = fitz.Pixmap(doc, xref)`
                    # 2. Check `pix.alpha`. If > 0, create PIL image as RGBA from `pix.samples`.
                    # 3. If `pix.alpha == 0`, check `pix.n`. If `pix.n == 1` (Gray) or `pix.n == 3` (RGB) or `pix.n == 4` (CMYK handled by Standard), maybe this strategy shouldn't run?
                    #    Assuming this strategy runs because Standard failed for *some* reason (e.g., bad colorspace obj).
                    #    In this case (alpha==0), convert to RGB using `fitz.Pixmap(fitz.csRGB, pix)` and create PIL as RGB.
                    # This seems more logical:
                    if pix.alpha > 0:
                        # Original has alpha. Attempt conversion to RGBA via fitz.
                        try:
                                # Use fitz.csRGB as target, but request alpha=True. This works if the original
                                # samples can provide alpha (i.e., original pix.alpha was > 0).
                                pix_converted = fitz.Pixmap(fitz.csRGB, pix, alpha=True)
                                # Use RGBA mode for PIL
                                pil_image = Image.frombytes("RGBA", [pix_converted.width, pix_converted.height], pix_converted.samples)
                                # Close the converted pixmap immediately
                                if pix_converted is not None and hasattr(pix_converted, 'close'):
                                    try: pix_converted.close()
                                    except Exception: pass
                                pix_converted = None
                                # Close the original pixmap immediately
                                if pix is not None and hasattr(pix, 'close'):
                                    try: pix.close()
                                    except Exception: pass
                                pix = None

                        except Exception as conv_error:
                                raise RuntimeError(f"Colorspace conversion to RGBA failed: {conv_error}") from conv_error
                    else:
                        # Original has no alpha. Attempt conversion to RGB via fitz.
                        try:
                                pix_converted = fitz.Pixmap(fitz.csRGB, pix)
                                # Use RGB mode for PIL
                                pil_image = Image.frombytes("RGB", [pix_converted.width, pix_converted.height], pix_converted.samples)
                                # Close the converted pixmap immediately
                                if pix_converted is not None and hasattr(pix_converted, 'close'):
                                    try: pix_converted.close()
                                    except Exception: pass
                                pix_converted = None
                                # Close the original pixmap immediately
                                if pix is not None and hasattr(pix, 'close'):
                                    try: pix.close()
                                    except Exception: pass
                                pix = None
                        except Exception as conv_error:
                                raise RuntimeError(f"Colorspace conversion to RGB failed: {conv_error}") from conv_error

            # pil_image must be created by now if no exception occurred during pixmap processing
            if pil_image is None:
                 # This should not happen if previous steps succeeded, but defensive check
                 raise RuntimeError("PIL Image not created after pixmap processing.")

            # Check minimum size
            if not self._check_min_size(pil_image, extraction_info):
                # _check_min_size populates error and issue_type
                extraction_info['success'] = False # Explicitly set success to False on failure
                # Close the PIL image as we are returning None
                if isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close'):
                     try: pil_image.close()
                     except Exception: pass
                return None, extraction_info # Return None immediately

            extracted_image = pil_image
            extraction_info['success'] = True # Set success to True only if extraction and size check pass
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
            logger.debug(f"Alternate colorspace extraction successful for xref {xref}")

        except Exception as e:
            error = f"Alternate colorspace extraction failed for xref {xref}: {str(e)}"
            logger.debug(error)
            extracted_image = None # Ensure extracted_image is None on failure
            extraction_info['success'] = False # Explicitly set success to False on exception
            extraction_info['error'] = error
            extraction_info['issue_type'] = "extraction_failed"
            # If an exception occurred after pil_image was created but before it was returned, close it
            # Note: pil_image might be partially created or None if the exception happened early
            if pil_image is not None and isinstance(pil_image, Image.Image) and hasattr(pil_image, 'close') and pil_image != extracted_image:
                 try: pil_image.close()
                 except Exception: pass


        finally:
            # Safety net: Ensure any pixmaps that were *not* closed in the try block get closed here.
            # This should ideally not be necessary if the try block logic is correct, but good for robustness.
            # Simplified check: if the object exists and has a close method, try to close it.
            # This handles real PyMuPDF Pixmaps and mocks.
            if pix is not None and hasattr(pix, 'close'):
                try:
                    pix.close()
                except Exception: pass # Ignore errors during close

            # Same for the converted pixmap
            if pix_converted is not None and hasattr(pix_converted, 'close'):
                 try: pix_converted.close()
                 except Exception: pass # Ignore errors during close


        # The caller (RetryCoordinator) is responsible for closing the *returned* PIL image (extracted_image)
        return extracted_image, extraction_info