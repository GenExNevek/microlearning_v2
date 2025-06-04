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
        self.min_width = self.config.get("min_width", 50)
        self.min_height = self.config.get("min_height", 50)

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
        if image.width < self.min_width or image.height < self.min_height:
            extraction_info['error'] = f"Image too small: {image.width}x{image.height}"
            extraction_info['issue_type'] = "size_issues"
            logger.debug(f"Image too small: {image.width}x{image.height}")
            return False
        return True

# Define a type hint for strategies
from typing import Type, Tuple
StrategyTuple = Tuple[Type['BaseExtractionStrategy'], str]