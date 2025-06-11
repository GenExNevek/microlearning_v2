from typing import Tuple, Dict
from scripts.extraction.image_processing.image_analyser import AnalysisResult

class ImageFilter:
    """
    Uses analysis results and configuration to filter out irrelevant images
    (e.g., small icons, blank spacers).
    """
    def __init__(self, config: Dict):
        self.config = config
        self.min_width = self.config.get('MIN_MEANINGFUL_IMAGE_WIDTH', 50)
        self.min_height = self.config.get('MIN_MEANINGFUL_IMAGE_HEIGHT', 50)
        self.max_icon_area = self.config.get('MAX_ICON_AREA_PX', 4096) # 64x64

    def should_keep_image(self, analysis: AnalysisResult) -> Tuple[bool, str]:
        """
        Evaluates an image's analysis data to decide if it should be kept.

        Returns:
            A tuple containing a boolean (True to keep, False to discard)
            and a string reason for the decision.
        """
        if self.config.get('FILTER_BLANK_IMAGES', True) and analysis.is_blank:
            return False, "Filtered: Blank or single-color image"

        width, height = analysis.dimensions
        if width < self.min_width or height < self.min_height:
            return False, f"Filtered: Below minimum dimensions ({self.min_width}x{self.min_height})"
        
        if self.config.get('FILTER_UI_ELEMENTS', True) and analysis.is_likely_icon:
            if (width * height) < self.max_icon_area:
                return False, f"Filtered: Small icon/UI element (area < {self.max_icon_area}px)"
            
        return True, f"Kept: Meaningful content detected ({analysis.content_type})"