# scripts/extraction/markdown_processing/image_link_processor.py

"""
Enhanced module for processing image references in markdown content using a content-aware
correlation engine with improved fallback mechanisms.
"""

import os
import re
import logging
from typing import Dict, Optional, Any, List

from ...config import settings
from .content_analyser import ContentAnalyser, ContextClues
from ..image_processing.correlation_engine import CorrelationEngine, CorrelationMatch

logger = logging.getLogger(__name__)

class ImageLinkProcessor:
    """
    Enhanced processor for image links in markdown with robust correlation and fallback mechanisms.
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

    def _get_available_image_files(self, assets_dir: Optional[str]) -> List[str]:
        """Get list of actual image files available on disk."""
        if not assets_dir or not os.path.exists(assets_dir):
            return []
        
        try:
            files = os.listdir(assets_dir)
            image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg'))]
            logger.debug(f"Found {len(image_files)} image files in {assets_dir}")
            return sorted(image_files)
        except Exception as e:
            logger.error(f"Error listing files in {assets_dir}: {e}")
            return []

    def _create_descriptive_placeholder(self, clue: ContextClues, md_ref_index: int) -> str:
        """Create a descriptive placeholder based on context clues."""
        base_name = "placeholder"
        
        # Use content type for better placeholder naming
        if clue.content_type:
            base_name = f"placeholder-{clue.content_type}"
        elif "thermometer" in clue.alt_text.lower():
            base_name = "placeholder-thermometer"
        elif "graph" in clue.alt_text.lower():
            base_name = "placeholder-graph"
        elif "target" in clue.alt_text.lower():
            base_name = "placeholder-target"
        else:
            base_name = f"placeholder-missing-{md_ref_index + 1}"
        
        return f"{base_name}.png"

    def _try_filename_based_matching(self, clues: List[ContextClues], available_files: List[str]) -> Dict[int, str]:
        """Attempt to match based on available filenames when correlation fails."""
        matches = {}
        used_files = set()
        
        for i, clue in enumerate(clues):
            if i in matches:
                continue
            
            # Try different matching strategies
            best_match = None
            best_score = 0
            
            for filename in available_files:
                if filename in used_files:
                    continue
                
                score = 0
                filename_lower = filename.lower()
                alt_lower = clue.alt_text.lower()
                
                # Content-based scoring
                if clue.content_type:
                    if clue.content_type in filename_lower:
                        score += 50
                
                # Keyword matching
                for keyword in clue.keywords:
                    if keyword in filename_lower:
                        score += 10
                
                # Direct text matching
                if "thermometer" in alt_lower and "thermometer" in filename_lower:
                    score += 40
                elif "graph" in alt_lower and "graph" in filename_lower:
                    score += 40
                elif "target" in alt_lower and "target" in filename_lower:
                    score += 40
                
                # Page number matching (if available)
                if clue.page_number:
                    if f"page{clue.page_number}" in filename_lower:
                        score += 30
                
                # Figure number matching
                if clue.figure_number:
                    if f"fig{clue.figure_number}" in filename_lower:
                        score += 25
                
                if score > best_score:
                    best_score = score
                    best_match = filename
            
            # Accept matches with reasonable confidence
            if best_match and best_score >= 20:
                matches[i] = best_match
                used_files.add(best_match)
                logger.info(f"Filename-based match: MD ref {i} -> {best_match} (score: {best_score})")
        
        return matches

    def _apply_intelligent_sequential_fallback(self, unmatched_clues: List[tuple], available_files: List[str], used_files: set) -> Dict[int, str]:
        """Apply intelligent sequential matching based on document order and content hints."""
        matches = {}
        remaining_files = [f for f in available_files if f not in used_files]
        
        if not remaining_files:
            return matches
        
        # Sort remaining files by their apparent order (page number, then image index)
        def extract_order_key(filename):
            # Extract page and image numbers for sorting
            page_match = re.search(r'page(\d+)', filename)
            img_match = re.search(r'img(\d+)', filename)
            page_num = int(page_match.group(1)) if page_match else 999
            img_num = int(img_match.group(1)) if img_match else 999
            return (page_num, img_num)
        
        remaining_files.sort(key=extract_order_key)
        
        # Match in document order
        for (md_ref_index, clue), filename in zip(unmatched_clues, remaining_files):
            matches[md_ref_index] = filename
            logger.info(f"Sequential fallback: MD ref {md_ref_index} -> {filename}")
        
        return matches

    def process_image_links(self,
                            content: str,
                            unit_title_id: str,
                            image_extraction_results: Optional[Dict[str, Any]],
                            actual_disk_img_assets_path: Optional[str]
                           ) -> str:
        """Enhanced image link processing with multiple fallback strategies."""
        safe_unit_title_id = re.sub(r'[^\w\-_\.]', '_', unit_title_id)
        img_assets_dir_name_for_md = f"{safe_unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        md_img_assets_path = f"./{img_assets_dir_name_for_md}"

        md_image_references = list(self.img_pattern.finditer(content))
        if not md_image_references:
            logger.info("No image references found in markdown content. Nothing to process.")
            return content

        # Get available resources
        kept_images = self._get_kept_images(image_extraction_results)
        available_files = self._get_available_image_files(actual_disk_img_assets_path)
        
        # Analyze all image references
        md_refs_clues = [
            self.content_analyser.analyse_markdown_context(content, match)
            for match in md_image_references
        ]
        
        # Strategy 1: Try correlation engine first
        ref_index_to_filename_map = {}
        if kept_images:
            matches: List[CorrelationMatch] = self.correlation_engine.correlate(md_refs_clues, kept_images)
            
            used_disk_images = set()
            for match in matches:
                img_index = match.extracted_img_index
                if 0 <= img_index < len(kept_images):
                    img_data = kept_images[img_index]
                    img_path = img_data.get('image_path')
                    if img_path:
                        filename = os.path.basename(img_path)
                        ref_index_to_filename_map[match.md_ref_index] = filename
                        used_disk_images.add(filename)
                        logger.debug(f"Correlation match: MD ref {match.md_ref_index} -> {filename}")
        
        # Strategy 2: Filename-based matching for unmatched references
        unmatched_indices = [i for i in range(len(md_refs_clues)) if i not in ref_index_to_filename_map]
        if unmatched_indices and available_files:
            unmatched_clues = [md_refs_clues[i] for i in unmatched_indices]
            filename_matches = self._try_filename_based_matching(unmatched_clues, available_files)
            
            for local_idx, filename in filename_matches.items():
                global_idx = unmatched_indices[local_idx]
                ref_index_to_filename_map[global_idx] = filename
                logger.info(f"Filename-based rescue: MD ref {global_idx} -> {filename}")
        
        # Strategy 3: Intelligent sequential fallback
        still_unmatched = [i for i in range(len(md_refs_clues)) if i not in ref_index_to_filename_map]
        if still_unmatched and available_files:
            used_files = set(ref_index_to_filename_map.values())
            unmatched_clue_pairs = [(i, md_refs_clues[i]) for i in still_unmatched]
            
            sequential_matches = self._apply_intelligent_sequential_fallback(
                unmatched_clue_pairs, available_files, used_files
            )
            
            for md_ref_index, filename in sequential_matches.items():
                ref_index_to_filename_map[md_ref_index] = filename
        
        # Build the final content
        new_content_parts = []
        last_end = 0
        
        for i, match_obj in enumerate(md_image_references):
            new_content_parts.append(content[last_end:match_obj.start()])
            
            alt_text = match_obj.group(1)
            original_path = match_obj.group(2)
            
            # Skip external URLs
            if original_path.startswith(('http', 'https', 'data:')):
                new_content_parts.append(match_obj.group(0))
            elif i in ref_index_to_filename_map:
                # Use matched filename
                correct_filename = ref_index_to_filename_map[i]
                new_path = f"{md_img_assets_path}/{correct_filename}"
                new_content_parts.append(f"![{alt_text}]({new_path})")
                logger.debug(f"Replaced image reference {i}: {original_path} -> {new_path}")
            else:
                # Create descriptive placeholder
                clue = md_refs_clues[i]
                placeholder_filename = self._create_descriptive_placeholder(clue, i)
                placeholder_path = f"{md_img_assets_path}/{placeholder_filename}"
                
                # Enhanced alt text with context
                enhanced_alt = f"{alt_text} (Missing: {clue.content_type or 'unknown content'})"
                new_content_parts.append(f"![{enhanced_alt}]({placeholder_path})")
                
                # Add diagnostic comment
                diagnostic_info = []
                if clue.page_number:
                    diagnostic_info.append(f"Expected page {clue.page_number}")
                if clue.figure_number:
                    diagnostic_info.append(f"Figure {clue.figure_number}")
                if clue.content_type:
                    diagnostic_info.append(f"Content type: {clue.content_type}")
                
                diagnostic_text = ", ".join(diagnostic_info) if diagnostic_info else "No specific context found"
                new_content_parts.append(f"\n<!-- WARNING: No image found for reference {i+1}. {diagnostic_text}. Using placeholder. -->\n")
                
                logger.warning(f"No match found for image reference {i} (alt: '{alt_text}'). Using placeholder: {placeholder_filename}")
            
            last_end = match_obj.end()
        
        new_content_parts.append(content[last_end:])
        
        final_content = ''.join(new_content_parts)
        
        # Log summary
        matched_count = len(ref_index_to_filename_map)
        total_count = len(md_image_references)
        logger.info(f"Image link processing complete: {matched_count}/{total_count} references matched")
        
        return final_content