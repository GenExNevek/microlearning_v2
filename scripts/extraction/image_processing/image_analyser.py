from dataclasses import dataclass
from typing import Tuple, List, Optional
from PIL import Image
import os

from scripts.utils import image_analysis_utils

@dataclass
class AnalysisResult:
    """A dataclass to hold the structured results of an image analysis."""
    image_hash: str
    dimensions: Tuple[int, int]
    aspect_ratio: float
    content_type: str  # e.g., 'diagram', 'icon', 'photograph', 'blank'
    is_likely_icon: bool
    edge_density: float
    color_complexity: float
    file_size_bytes: int
    is_blank: bool

class ImageAnalyser:
    """
    Analyzes image content to produce structured metadata for filtering and correlation.
    """
    def _classify_content_type(self, analysis_data: dict) -> Tuple[str, bool]:
        """
        Rule-based classification of the image content type.
        Returns a tuple of (content_type, is_likely_icon).
        """
        width, height = analysis_data['dimensions']
        edge_density = analysis_data['edge_density']
        color_complexity = analysis_data['color_complexity']

        is_icon = False
        if (width < 80 and height < 80) and color_complexity < 0.1:
            is_icon = True

        if analysis_data['is_blank']:
            return 'blank', is_icon

        if is_icon:
            return 'icon', True
        
        # Rule for diagrams: high edge density, low-to-mid color complexity
        if edge_density > 0.05 and color_complexity < 0.2:
            return 'diagram', False

        # Rule for photographs: high color complexity, varied edges
        if color_complexity > 0.2:
            return 'photograph', False
            
        return 'unknown', is_icon

    def analyse_image(self, pil_image: Image.Image) -> AnalysisResult:
        """
        Performs a full analysis of a given PIL Image object.
        """
        # Get basic properties
        dimensions = pil_image.size
        aspect_ratio = dimensions[0] / dimensions[1] if dimensions[1] > 0 else 0
        
        # In-memory size estimation; not perfect but avoids temp files
        file_size_bytes = len(pil_image.tobytes())

        # Perform advanced analysis using utils
        image_hash = image_analysis_utils.compute_perceptual_hash(pil_image)
        edge_density = image_analysis_utils.calculate_edge_density(pil_image)
        color_complexity = image_analysis_utils.calculate_color_complexity(pil_image)
        is_blank = image_analysis_utils.is_likely_blank(pil_image)
        
        # Classify content
        analysis_data = {
            'dimensions': dimensions,
            'edge_density': edge_density,
            'color_complexity': color_complexity,
            'is_blank': is_blank
        }
        content_type, is_likely_icon = self._classify_content_type(analysis_data)
        
        return AnalysisResult(
            image_hash=image_hash,
            dimensions=dimensions,
            aspect_ratio=aspect_ratio,
            content_type=content_type,
            is_likely_icon=is_likely_icon,
            edge_density=edge_density,
            color_complexity=color_complexity,
            file_size_bytes=file_size_bytes,
            is_blank=is_blank,
        )