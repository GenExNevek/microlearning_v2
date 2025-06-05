# scripts/extraction/image_processor.py (Updated import)
# This file was already created above, just noting the import update needed if utils is not a sibling

"""Handles post-extraction image processing like resizing, saving, and validation."""

import logging
import os
import io
from PIL import Image
from typing import Dict, Any, Tuple

# Assuming utils is in a parent directory
# from ..utils.image_validation import ImageValidator, ImageIssueType # Original
from ..utils.image_validation import ImageValidator, ImageIssueType # Adjusted import based on typical structure

# Rest of the file content is the same as generated before.
# The import path will depend on the exact structure of the 'utils' directory relative to 'extraction'.
# If utils is a sibling of extraction: from ..utils.image_validation
# If utils is two levels up (e.g., scripts/utils): from ...utils.image_validation
# Let's assume the latter based on common project layouts.

logger = logging.getLogger(__name__)

class ImageProcessor:
    """Manages image resizing, optimisation, file saving, and format conversions."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the ImageProcessor with configuration."""
        self.config = config
        self.image_format = self.config.get("image_format", "png").lower()
        self.quality = self.config.get("quality", 95)
        self.max_width = self.config.get("max_width", 1920)
        self.max_height = self.config.get("max_height", 1080)
        self.min_width = self.config.get("min_width", 50)
        self.min_height = self.config.get("min_height", 50)
        self.supported_formats = self.config.get("supported_formats", ["png", "jpg", "jpeg"])
        self.maintain_aspect_ratio = self.config.get("maintain_aspect_ratio", True)
        self.validation_enabled = self.config.get("validate_images", True)

        # Configure validator with same thresholds
        self.validator = ImageValidator(
            min_width=self.min_width,
            min_height=self.min_height,
            supported_formats=self.supported_formats
        )

    def process_and_save_image(self, image: Image.Image, output_path: str) -> Dict:
        """
        Process (resize) and save the extracted image, then validate the saved file.

        Args:
            image: PIL Image object.
            output_path: Full path where the image should be saved.

        Returns:
            Dictionary with processing and validation results.
        """
        result = {
            'success': False,
            'path': output_path,
            'issue': None,
            'issue_type': None,
            'validation_info': {},
            'processing_details': {}
        }

        try:
            processed_image = image

            # Resize if needed while maintaining aspect ratio
            if self.maintain_aspect_ratio:
                original_width, original_height = processed_image.size
                processed_image = self._resize_image(processed_image, result['processing_details'])
                if processed_image.size != (original_width, original_height):
                     logger.debug(f"Image processed: Resized from {original_width}x{original_height} to {processed_image.width}x{processed_image.height}")
            else:
                 logger.debug("Image processing: Aspect ratio maintenance disabled.")

            # Save the image
            self._save_image(processed_image, output_path, result['processing_details'])

            # Validate the saved image if validation is enabled
            if self.validation_enabled:
                logger.debug(f"Image validation enabled. Validating saved file: {output_path}")
                validation_result = self.validator.validate_image_file(output_path)

                result['validation_info'] = validation_result.metrics
                if validation_result.is_valid:
                    result['success'] = True
                    logger.debug(f"Image validation successful for {output_path}")
                else:
                    result['success'] = False
                    result['issue'] = validation_result.details
                    result['issue_type'] = validation_result.issue_type.value if validation_result.issue_type else "unknown"
                    logger.warning(f"Image validation failed for {output_path}: {result['issue']}")
            else:
                # Validation skipped, assume success if saved
                result['success'] = True
                logger.debug(f"Image validation skipped for {output_path}")


        except Exception as e:
            result['success'] = False
            result['issue'] = f"Error during image processing or saving: {str(e)}"
            result['issue_type'] = "processing_error"
            logger.error(f"Processing/Saving failed for {output_path}: {e}")

        return result

    def _resize_image(self, image: Image.Image, processing_details: Dict) -> Image.Image:
        """
        Resize image if it exceeds maximum dimensions while maintaining aspect ratio.

        Args:
            image: PIL Image object.
            processing_details: Dictionary to log resizing details.

        Returns:
            Resized PIL Image object.
        """
        width, height = image.size
        processing_details['original_dimensions'] = f"{width}x{height}"

        # Calculate scaling factor
        scale_factor = min(
            self.max_width / width if width > self.max_width else 1,
            self.max_height / height if height > self.max_height else 1
        )

        if scale_factor < 1:
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            # Use LANCZOS for high quality downsampling
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            processing_details['resized_dimensions'] = f"{new_width}x{new_height}"
            processing_details['resize_applied'] = True
        else:
             processing_details['resize_applied'] = False

        return image

    def _save_image(self, image: Image.Image, path: str, processing_details: Dict):
        """
        Save PIL Image to file.

        Args:
            image: PIL Image object.
            path: Output file path.
            processing_details: Dictionary to log saving details.
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Determine format to save
        save_format = self.image_format.upper()
        if save_format == "JPG": # Canonicalize to JPEG for Pillow
            save_format = "JPEG"
        processing_details['save_format'] = save_format

        # Save with appropriate quality/compression
        save_kwargs = {}
        if save_format == 'JPEG': # Use canonical name
            save_kwargs['quality'] = self.quality
            save_kwargs['optimize'] = True
            processing_details['jpeg_quality'] = self.quality
        elif save_format == 'PNG':
            save_kwargs['compress_level'] = 9 # Default is 6, 9 is max compression
            processing_details['png_compress_level'] = 9

        # Ensure image is in a mode compatible with the target format if necessary
        if save_format == 'JPEG' and image.mode == 'RGBA': # Use canonical name
             logger.debug("Converting RGBA to RGB for JPEG save.")
             image = image.convert('RGB')
             processing_details['mode_converted'] = 'RGBA_to_RGB'
        elif save_format == 'PNG' and image.mode not in ['RGB', 'RGBA', 'L', 'P']:
             # PNG supports various modes, but RGB/RGBA are common outputs
             logger.debug(f"Converting {image.mode} to RGB/RGBA for PNG save.")
             try:
                 image = image.convert('RGBA') if 'A' in image.getbands() else image.convert('RGB')
                 processing_details['mode_converted'] = image.mode
             except Exception as e:
                 logger.warning(f"Failed to convert image mode {image.mode} for PNG save: {e}. Attempting save anyway.")


        image.save(path, format=save_format, **save_kwargs)
        processing_details['save_successful'] = True
        logger.debug(f"Saved processed image to: {path}")
