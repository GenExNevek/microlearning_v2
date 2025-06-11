# scripts/extraction/markdown_processing/image_link_processor.py

"""
Module for processing image references in markdown content using a content-aware
correlation engine.
"""

import os
import re
import logging
from typing import Dict, Optional, Any, List

from ...config import settings
from .content_analyser import ContentAnalyser
from ..image_processing.correlation_engine import CorrelationEngine, CorrelationMatch

logger = logging.getLogger(__name__)

class ImageLinkProcessor:
    """
    Processes and corrects image links in markdown by correlating them with
    extracted image files based on content and context.
    """

    def __init__(self):
        """Initializes the processor and its components."""
        self.img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
        self.content_analyser = ContentAnalyser()
        self.correlation_engine = CorrelationEngine()

    def _get_kept_images(self, image_extraction_results: Optional[Dict[str, Any]]) -> List[Dict]:
        """Safely retrieves the list of kept images from the extraction results."""
        if not image_extraction_results:
            return []
        
        kept_images = image_extraction_results.get('kept_image_data', [])
        if not kept_images:
            logger.warning("No 'kept_image_data' found in extraction results. Correlation will be empty.")
        
        return kept_images

    def process_image_links(self,
                            content: str,
                            unit_title_id: str,
                            image_extraction_results: Optional[Dict[str, Any]],
                            actual_disk_img_assets_path: Optional[str]
                           ) -> str:
        """
        Refactored method to process image links using the correlation engine.
        """
        safe_unit_title_id = re.sub(r'[^\w\-_\.]', '_', unit_title_id)
        img_assets_dir_name_for_md = f"{safe_unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        md_img_assets_path = f"./{img_assets_dir_name_for_md}"

        md_image_references = list(self.img_pattern.finditer(content))
        if not md_image_references:
            logger.info("No image references found in markdown content. Nothing to process.")
            return content

        kept_images = self._get_kept_images(image_extraction_results)
        if not kept_images:
            logger.warning("No kept images available for correlation. All image links will become placeholders.")
            def placeholder_replace(match):
                if match.group(2).startswith(('http', 'https', 'data:')):
                    return match.group(0)
                return f"![{match.group(1)}]({md_img_assets_path}/placeholder-error.png)"
            return self.img_pattern.sub(placeholder_replace, content)

        md_refs_clues = [
            self.content_analyser.analyse_markdown_context(content, match)
            for match in md_image_references
        ]

        matches: List[CorrelationMatch] = self.correlation_engine.correlate(md_refs_clues, kept_images)
        
        ref_index_to_filename_map = {}
        used_disk_images = set()
        for match in matches:
            img_index = match.extracted_img_index
            if 0 <= img_index < len(kept_images):
                img_data = kept_images[img_index]
                img_path = img_data.get('image_path')
                # --- SAFETY CHECK ADDED ---
                if img_path:
                    filename = os.path.basename(img_path)
                    ref_index_to_filename_map[match.md_ref_index] = filename
                    used_disk_images.add(filename)
                else:
                    logger.warning(f"Correlation match for ref {match.md_ref_index} points to image index {img_index} which has no 'image_path'.")
            else:
                 logger.warning(f"Correlation engine returned an out-of-bounds image index: {img_index}")

        new_content_parts = []
        last_end = 0
        for i, match_obj in enumerate(md_image_references):
            new_content_parts.append(content[last_end:match_obj.start()])
            
            alt_text = match_obj.group(1)
            original_path = match_obj.group(2)
            
            if original_path.startswith(('http', 'https', 'data:')):
                new_content_parts.append(match_obj.group(0))
            elif i in ref_index_to_filename_map:
                correct_filename = ref_index_to_filename_map[i]
                new_path = f"{md_img_assets_path}/{correct_filename}"
                new_content_parts.append(f"![{alt_text}]({new_path})")
            else:
                logger.warning(f"No correlation found for image reference with alt text: '{alt_text}'. Using placeholder.")
                new_content_parts.append(f"![{alt_text} (Image not found)]({md_img_assets_path}/placeholder-error.png)")

            last_end = match_obj.end()

        new_content_parts.append(content[last_end:])
        processed_content = "".join(new_content_parts)

        all_kept_filenames = {os.path.basename(img['image_path']) for img in kept_images if img.get('image_path')}
        unused_images = all_kept_filenames - used_disk_images
        if unused_images:
            unused_list = ', '.join(sorted(list(unused_images)))
            warning_suffix = f"\n\n\n"
            processed_content += warning_suffix

        return processed_content