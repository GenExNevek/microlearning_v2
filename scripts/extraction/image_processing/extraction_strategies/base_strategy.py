# scripts/extraction/extraction_strategies/base_strategy.py

"""Base class for image extraction strategies."""

import fitz
from PIL import Image
from typing import Optional, Dict, Any, Tuple
from abc import ABC, abstractmethod
import logging


logger = logging.getLogger(__name__)

class BaseExtractionStrategy(ABC):
    """Abstract base class for PDF image extraction strategies."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the strategy with configuration.

        Args:
            config: Dictionary of configuration settings.
        """
        self.config = config
        # Ensure min_width and min_height are integers and have sensible defaults
        # Use .get with default and then convert to int for robustness
        try:
            self.min_width = int(self.config.get("min_width", 50))
        except (ValueError, TypeError):
            logger.warning(f"Invalid min_width configuration value: {self.config.get('min_width')}. Using default 50.")
            self.min_width = 50

        try:
            self.min_height = int(self.config.get("min_height", 50))
        except (ValueError, TypeError):
            logger.warning(f"Invalid min_height configuration value: {self.config.get('min_height')}. Using default 50.")
            self.min_height = 50

        # Ensure minimums are positive
        self.min_width = max(1, self.min_width)
        self.min_height = max(1, self.min_height)


    @abstractmethod
    def extract(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        extraction_info: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt to extract an image using this strategy.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple from page.get_images().
            page_num: The 1-indexed page number the image was found on.
            extraction_info: Dictionary to add extraction details/errors to.

        Returns:
            A tuple containing:
            - The extracted PIL Image object, or None if extraction failed.
            - An updated extraction_info dictionary including success status and details.
        """
        pass

    def _check_min_size(self, image: Image.Image, extraction_info: Dict) -> bool:
        """
        Check if the extracted image meets minimum size requirements.

        Args:
            image: The PIL Image object.
            extraction_info: Dictionary to add validation details to.

        Returns:
            True if the image meets minimum size, False otherwise.
        """
        if image is None:
            # This case should ideally be handled by the strategy returning None immediately,
            # but as a defensive check within the method.
            error_msg = "Image object is None before size check."
            extraction_info['error'] = error_msg
            extraction_info['issue_type'] = "internal_error"
            logger.error(error_msg)
            return False

        # Ensure image has width and height attributes (might be a mock without them)
        if not hasattr(image, 'width') or not hasattr(image, 'height'):
             error_msg = f"Image object is missing width or height attributes during size check: {type(image)}"
             extraction_info['error'] = error_msg
             extraction_info['issue_type'] = "internal_error"
             logger.error(error_msg)
             return False


        if image.width < self.min_width or image.height < self.min_height:
            extraction_info['error'] = f"Image too small: {image.width}x{image.height} (min: {self.min_width}x{self.min_height})"
            extraction_info['issue_type'] = "size_issues"
            logger.debug(f"Image too small: {image.width}x{image.height} for min {self.min_width}x{self.min_height}")
            return False
        return True

# Define a type hint for strategies
from typing import Type, Tuple
StrategyTuple = Tuple[Type['BaseExtractionStrategy'], str]