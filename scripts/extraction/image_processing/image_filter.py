# scripts/extraction/image_processing/image_filter.py

from typing import Tuple, Dict
from scripts.extraction.image_processing.image_analyser import AnalysisResult

class ImageFilter:
    """
    Uses analysis results and configuration to filter out irrelevant images
    (e.g., small icons, blank spacers).
    
    Enhanced with diagnostic mode capability to analyse all images and provide
    detailed reasons about filtering decisions.
    """
    def __init__(self, config: Dict, diagnostic_mode: bool = False):
        """
        Initialize the filter with configuration.
        
        Args:
            config: Dictionary of filter configuration settings
            diagnostic_mode: If True, never filters images but provides detailed reasons
        """
        self.config = config
        self.diagnostic_mode = diagnostic_mode or config.get('DIAGNOSTIC_MODE_ENABLED', False)
        self.min_width = self.config.get('MIN_MEANINGFUL_IMAGE_WIDTH', 50)
        self.min_height = self.config.get('MIN_MEANINGFUL_IMAGE_HEIGHT', 50)
        self.max_icon_area = self.config.get('MAX_ICON_AREA_PX', 4096)  # 64x64
        
        # Diagnostic mode settings
        self.include_analysis_details = config.get('DIAGNOSTIC_INCLUDE_ANALYSIS_DETAILS', True)
        self.show_threshold_values = config.get('DIAGNOSTIC_SHOW_THRESHOLD_VALUES', True)

    def should_keep_image(self, analysis: AnalysisResult) -> Tuple[bool, str]:
        """
        Evaluates an image's analysis data to decide if it should be kept.
        
        In diagnostic mode, always returns True but provides detailed filtering reasons.

        Args:
            analysis: The AnalysisResult object containing image analysis data

        Returns:
            A tuple containing:
            - Boolean: True to keep (always True in diagnostic mode), False to discard
            - String: Detailed reason for the decision
        """
        # Run all filter checks and collect detailed information
        filter_reasons = []
        would_be_filtered = False
        
        # Check 1: Minimum dimensions
        width, height = analysis.dimensions
        if width < self.min_width or height < self.min_height:
            would_be_filtered = True
            if self.show_threshold_values:
                reason = f"Image dimensions ({width}x{height}) are below threshold ({self.min_width}x{self.min_height})"
            else:
                reason = "Image dimensions are below minimum threshold"
            filter_reasons.append(reason)
        
        # Check 2: Blank images
        if self.config.get('FILTER_BLANK_IMAGES', True) and analysis.is_blank:
            would_be_filtered = True
            if self.include_analysis_details:
                reason = f"Image is likely blank (analysis details: {getattr(analysis, 'blank_analysis_details', 'N/A')})"
            else:
                reason = "Image is likely blank"
            filter_reasons.append(reason)

        # Check 3: Decorative banners
        if self.config.get('FILTER_DECORATIVE_BANNERS', True) and hasattr(analysis, 'is_likely_decorative_banner') and analysis.is_likely_decorative_banner:
            would_be_filtered = True
            if self.include_analysis_details and hasattr(analysis, 'banner_analysis_details'):
                reason = f"Detected as a low-complexity decorative banner. Details: {analysis.banner_analysis_details}"
            else:
                reason = "Detected as a decorative banner"
            filter_reasons.append(reason)

        # Check 4: UI elements/icons
        if self.config.get('FILTER_UI_ELEMENTS', True) and analysis.is_likely_icon:
            area = width * height
            if area < self.max_icon_area:
                would_be_filtered = True
                if self.show_threshold_values:
                    reason = f"Small icon/UI element (area {area}px < {self.max_icon_area}px threshold)"
                else:
                    reason = "Small icon/UI element detected"
                filter_reasons.append(reason)
        
        # Check 5: Low complexity filter (NEW - for catching fig6/fig7 type images)
        if self.config.get('FILTER_LOW_COMPLEXITY', True):
            # Filter images that are medium-sized but very low complexity
            # These often result in tiny file sizes when saved
            area = width * height
            if (area > 20000 and area < 100000 and  # Medium size (roughly 140x140 to 316x316)
                hasattr(analysis, 'color_complexity') and analysis.color_complexity < 0.05 and
                hasattr(analysis, 'edge_density') and analysis.edge_density < 0.02):
                would_be_filtered = True
                if self.include_analysis_details:
                    reason = f"Low complexity medium-sized image (complexity: {getattr(analysis, 'color_complexity', 'N/A'):.3f}, edges: {getattr(analysis, 'edge_density', 'N/A'):.3f})"
                else:
                    reason = "Low complexity image detected"
                filter_reasons.append(reason)
        
        # Prepare the final reason string
        if self.diagnostic_mode:
            if would_be_filtered:
                detailed_reason = " | ".join(filter_reasons)
                if self.include_analysis_details:
                    content_info = f"Content type: {analysis.content_type}, Dimensions: {analysis.dimensions}"
                    if hasattr(analysis, 'color_complexity') and hasattr(analysis, 'edge_density'):
                        content_info += f", Complexity: {analysis.color_complexity:.3f}, Edges: {analysis.edge_density:.3f}"
                    final_reason = f"[WOULD BE FILTERED] Reason: {detailed_reason} | Analysis: {content_info}"
                else:
                    final_reason = f"[WOULD BE FILTERED] Reason: {detailed_reason}"
                return True, final_reason
            else:
                # Image passes all filters
                if self.include_analysis_details:
                    content_info = f"Content: {analysis.content_type}, Dimensions: {analysis.dimensions}"
                    if hasattr(analysis, 'color_complexity') and hasattr(analysis, 'edge_density'):
                        content_info += f", Complexity: {analysis.color_complexity:.3f}, Edges: {analysis.edge_density:.3f}"
                    final_reason = f"[OK] Passed all filters | {content_info}"
                else:
                    final_reason = f"[OK] Passed all filters ({analysis.content_type})"
                return True, final_reason
        else:
            # Normal filtering mode
            if would_be_filtered:
                return False, filter_reasons[0] if filter_reasons else "Filtered for unknown reason"
            else:
                return True, f"Kept: Meaningful content detected ({analysis.content_type})"

    def enable_diagnostic_mode(self):
        """Enable diagnostic mode for this filter instance."""
        self.diagnostic_mode = True
    
    def disable_diagnostic_mode(self):
        """Disable diagnostic mode for this filter instance."""
        self.diagnostic_mode = False
    
    def is_diagnostic_mode_enabled(self) -> bool:
        """Check if diagnostic mode is currently enabled."""
        return self.diagnostic_mode