# scripts/extraction/markdown_processing/image_link_processor.py

"""Module for processing image references in markdown content."""

import os
import re
import logging
from typing import Dict, Optional, Any, Set, List, Tuple

from ...config import settings # For IMAGE_ASSETS_SUFFIX
from ...utils.image_validation import ImageIssueType # For placeholder names

logger = logging.getLogger(__name__)

class ImageLinkProcessor:
    """Processes image references in markdown, linking them to extracted images or placeholders."""

    def __init__(self):
        self.img_pattern = r'!\[(.*?)\]\((.*?)\)' # Alt text, path

    def _determine_placeholder_name(self, issue_type_val: Optional[str]) -> str:
        """Determines the placeholder filename based on issue type."""
        if issue_type_val == ImageIssueType.BLANK.value:
            return "placeholder-blank.png"
        elif issue_type_val == ImageIssueType.CORRUPT.value:
            return "placeholder-corrupt.png"
        return "placeholder-error.png"

    def _parse_page_index_from_md(self, alt_text: str, md_path: str) -> Tuple[Optional[int], Optional[int]]:
        """Helper to parse page and index from markdown alt text or path."""
        page_num, img_idx_on_page = None, None

        # ***FIXED: Updated pattern to match actual filename format from image_extractor.py***
        # Looking for: fig{GLOBAL_COUNT}-page{PAGE_NUM_1_IDX}-img{IMG_ON_PAGE_1_IDX}.{ext} format
        # Regex: fig(\d+)-page(\d+)[-_]?img(\d+)
        # Group 1: Global figure number
        # Group 2: Page number (1-indexed)
        # Group 3: Image index on page (1-indexed)
        fn_match = re.search(r'fig(\d+)-page(\d+)[-_]?img(\d+)', md_path, re.IGNORECASE)
        if fn_match:
            # page_num from group(2) (1-indexed page number from filename)
            page_num = int(fn_match.group(2))
            # img_idx_on_page from group(3) (1-indexed image index on page from filename), convert to 0-indexed
            img_idx_on_page = int(fn_match.group(3)) - 1
            logger.debug(f"Parsed from MD path filename '{md_path}': page={page_num} (1-indexed), idx_on_page={img_idx_on_page} (0-indexed)")
            return page_num, img_idx_on_page

        # ***ENHANCED: Also check for legacy pattern as fallback***
        # Looking for: page{P}-img{I}.{ext} format
        legacy_fn_match = re.search(r'page(\d+)[-_]?img(\d+)', md_path, re.IGNORECASE)
        if legacy_fn_match:
            page_num = int(legacy_fn_match.group(1)) # 1-indexed page number
            img_idx_on_page = int(legacy_fn_match.group(2)) - 1  # Convert 1-indexed img index to 0-indexed
            logger.debug(f"Parsed from MD path (legacy pattern) '{md_path}': page={page_num} (1-indexed), idx_on_page={img_idx_on_page} (0-indexed)")
            return page_num, img_idx_on_page

        # Attempt 2: Parse from alt text
        alt_text_lower = alt_text.lower()
        # Try to get page number from alt text if not already found
        if page_num is None:
            page_match_alt = re.search(r'page\s*(\d+)', alt_text_lower)
            if page_match_alt: page_num = int(page_match_alt.group(1)) # Assume 1-indexed from alt text

        # Try to get image index from alt text
        # Regex: (image|figure|fig|img) followed by optional space, then
        # EITHER ( (\d+) [space/./,] (\d+) ) -> page.image or page,image or page image (group1=page, group2=image)
        # OR ( (\d+) ) -> just image number (group3=image)
        img_match_alt = re.search(r'(?:image|figure|fig|img)\s*(?:(\d+)\s*[.,]?\s*(\d+)|(\d+))', alt_text_lower)
        if img_match_alt:
            if img_match_alt.group(1) and img_match_alt.group(2): # Format like "fig <page_val_from_alt>.<index_val_from_alt>"
                # If page_num wasn't found from "page X" pattern, use the one from "fig P.I"
                if page_num is None: page_num = int(img_match_alt.group(1)) # Assume 1-indexed
                # ***FIXED: Convert to 0-indexed for consistency***
                img_idx_on_page = int(img_match_alt.group(2)) - 1 # Assume 1-indexed from alt, convert to 0-indexed
            elif img_match_alt.group(3): # Format like "fig <index_val_from_alt>"
                # ***FIXED: Convert to 0-indexed for consistency***
                img_idx_on_page = int(img_match_alt.group(3)) - 1 # Assume 1-indexed from alt, convert to 0-indexed
        
        logger.debug(f"Parsed from alt text '{alt_text}': page={page_num} (1-indexed if parsed), idx_on_page={img_idx_on_page} (0-indexed if parsed)")
        return page_num, img_idx_on_page

    def _find_specific_disk_image(self,
                                  target_page: int, target_idx: int, # target_page is 1-indexed, target_idx is 0-indexed
                                  available_images_on_disk: List[str],
                                  # This set tracks images ALREADY USED by SEQUENTIAL assignment
                                  sequentially_assigned_indices: Set[int],
                                  allow_reuse_if_specific_match: bool = False
                                 ) -> Optional[Tuple[str, int]]:
        """Finds a disk image matching specific page/index. Returns (filename, disk_index) or None."""
        for i, disk_img_name in enumerate(available_images_on_disk):
            # ***FIXED: Updated pattern to match actual filename format from image_extractor.py***
            # Looking for: fig{GLOBAL_COUNT}-page{PAGE_NUM_1_IDX}-img{IMG_ON_PAGE_1_IDX}.{ext} format
            # Regex: fig(\d+)-page(\d+)[-_]?img(\d+)\.
            # Group 1: Global figure number
            # Group 2: Page number (1-indexed)
            # Group 3: Image index on page (1-indexed)
            disk_fn_match = re.search(r'fig(\d+)-page(\d+)[-_]?img(\d+)\.', disk_img_name, re.IGNORECASE)
            if disk_fn_match:
                saved_page_from_disk = int(disk_fn_match.group(2)) # 1-indexed page number from disk filename
                # Convert 1-indexed img index from disk filename to 0-indexed for comparison
                saved_idx_on_page_from_disk = int(disk_fn_match.group(3)) - 1 
                
                if saved_page_from_disk == target_page and saved_idx_on_page_from_disk == target_idx:
                    # Found a disk image that semantically matches the page/index.
                    if allow_reuse_if_specific_match:
                        # Yes, specific matches can reuse disk images regardless of sequential assignment.
                        logger.info(f"Specific match (reuse allowed): MD ref (P:{target_page}, I:{target_idx}) to disk image: {disk_img_name} (index {i})")
                        return disk_img_name, i
                    else:
                        # Not allowing general reuse, so check if it was already sequentially assigned.
                        if i not in sequentially_assigned_indices:
                            logger.info(f"Specific match (no reuse, not sequentially assigned): MD ref (P:{target_page}, I:{target_idx}) to disk image: {disk_img_name} (index {i})")
                            return disk_img_name, i
                        else:
                            logger.debug(f"Disk image {disk_img_name} matches P:{target_page}, I:{target_idx} but was already sequentially assigned and reuse is not generally allowed for this call.")
            
            # ***ENHANCED: Check for legacy pattern as fallback***
            # Looking for: page{P}-img{I}.{ext} format
            legacy_disk_fn_match = re.search(r'page(\d+)[-_]?img(\d+)\.', disk_img_name, re.IGNORECASE)
            if legacy_disk_fn_match:
                saved_page_from_disk = int(legacy_disk_fn_match.group(1)) # 1-indexed page number
                saved_idx_on_page_from_disk = int(legacy_disk_fn_match.group(2)) - 1  # Convert 1-indexed to 0-indexed
                if saved_page_from_disk == target_page and saved_idx_on_page_from_disk == target_idx:
                    if allow_reuse_if_specific_match or i not in sequentially_assigned_indices:
                        logger.info(f"Legacy pattern match: MD ref (P:{target_page}, I:{target_idx}) to disk image: {disk_img_name} (index {i})")
                        return disk_img_name, i
        return None

    def process_image_links(self,
                            content: str,
                            unit_title_id: str,
                            image_extraction_results: Optional[Dict[str, Any]],
                            actual_disk_img_assets_path: Optional[str]
                           ) -> str:
        safe_unit_title_id = re.sub(r'[^\w\-_\.]', '_', unit_title_id)
        img_assets_dir_name_for_md = f"{safe_unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        md_img_assets_path = f"./{img_assets_dir_name_for_md}"

        logger.debug(f"Processing image references. MD assets path: {md_img_assets_path}, Disk assets path: {actual_disk_img_assets_path}")

        if not image_extraction_results or not actual_disk_img_assets_path or not os.path.exists(actual_disk_img_assets_path):
            logger.warning(f"Image assets path not available/found ({actual_disk_img_assets_path}). Using generic placeholders.")
            def generic_replace(match):
                alt_text, original_path_in_md = match.group(1), match.group(2)
                if original_path_in_md.startswith(('http://', 'https://', '/', 'data:')): return match.group(0)
                return f"![{alt_text}]({md_img_assets_path}/placeholder-image.png)"
            content = re.sub(self.img_pattern, generic_replace, content)
            content += f"\n\n<!-- WARNING: Image assets directory missing ({actual_disk_img_assets_path}). Local image links may be placeholders. -->\n"
            return content

        try:
            saved_image_files = sorted([
                f for f in os.listdir(actual_disk_img_assets_path)
                if os.path.isfile(os.path.join(actual_disk_img_assets_path, f)) and
                   f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) and
                   not f.startswith('placeholder-')
            ])
            logger.debug(f"Found {len(saved_image_files)} saved disk images: {saved_image_files}")
        except FileNotFoundError:
            logger.warning(f"Image assets directory not found at {actual_disk_img_assets_path} during listdir. Using generic placeholders.")
            saved_image_files = []
        
        available_images_on_disk = saved_image_files[:]
        
        # Problematic images from extraction results:
        # 'page' is 1-indexed, 'index_on_page' is 0-indexed.
        problematic_images_info: Dict[str, Dict[str, Any]] = {
            # Key uses 1-indexed page and 0-indexed index_on_page from extraction results
            f"{p.get('page')}-{p.get('index_on_page', -1)}": p
            for p in image_extraction_results.get('problematic_images', [])
            if p.get('page') is not None and p.get('index_on_page') is not None
        }
        logger.debug(f"Problematic images info (keyed 'page(1-idx)-idx(0-idx)'): {problematic_images_info}")

        sequentially_assigned_disk_indices: Set[int] = set()
        
        md_image_references = list(re.finditer(self.img_pattern, content))
        new_content_parts = []
        last_end = 0

        for match_obj in md_image_references:
            new_content_parts.append(content[last_end:match_obj.start()])
            last_end = match_obj.end()

            alt_text = match_obj.group(1)
            original_path_in_md = match_obj.group(2)
            replacement_image_tag = match_obj.group(0) 

            if original_path_in_md.startswith(('http://', 'https://', '/', 'data:')):
                new_content_parts.append(replacement_image_tag)
                continue

            logger.debug(f"Processing MD image: alt='{alt_text}', original_path='{original_path_in_md}'")
            # page_num will be 1-indexed if parsed, img_idx_on_page will be 0-indexed if parsed
            page_num, img_idx_on_page = self._parse_page_index_from_md(alt_text, original_path_in_md)

            # 1. Check for problematic image based on parsed page/index
            if page_num is not None and img_idx_on_page is not None:
                # problem_key uses 1-indexed page_num and 0-indexed img_idx_on_page
                problem_key = f"{page_num}-{img_idx_on_page}"
                if problem_key in problematic_images_info:
                    issue_info = problematic_images_info[problem_key]
                    issue_type_val = issue_info.get('issue_type', ImageIssueType.OTHER.value)
                    placeholder_filename = self._determine_placeholder_name(issue_type_val)
                    
                    display_page = page_num # page_num is already 1-indexed
                    display_idx = img_idx_on_page + 1  # Convert 0-indexed img_idx_on_page to 1-indexed for display
                    warning_comment = (f"\n<!-- WARNING: Image from Page {display_page}, Index {display_idx} "
                                       f"had an issue: {issue_info.get('issue', 'N/A')}. Using placeholder. -->\n")
                    replacement_image_tag = f"{warning_comment}![{alt_text} (Issue: {issue_type_val})]({md_img_assets_path}/{placeholder_filename})"
                    new_content_parts.append(replacement_image_tag)
                    logger.warning(f"MD ref P{page_num}(1-idx)-I{img_idx_on_page}(0-idx) was problematic. Using placeholder: {placeholder_filename}")
                    continue # Move to next MD image

            # 2. Try to find a specific disk image match
            target_saved_image_filename = None
            if page_num is not None and img_idx_on_page is not None:
                # Pass 1-indexed page_num and 0-indexed img_idx_on_page to _find_specific_disk_image
                specific_match_result = self._find_specific_disk_image(
                    page_num, img_idx_on_page, available_images_on_disk, 
                    sequentially_assigned_disk_indices, 
                    allow_reuse_if_specific_match=True 
                )
                if specific_match_result:
                    target_saved_image_filename, _ = specific_match_result 
            
            if target_saved_image_filename:
                replacement_image_tag = f"![{alt_text}]({md_img_assets_path}/{target_saved_image_filename})"
            else:
                # 3. Fallback: Sequential mapping
                found_sequential = False
                for i, disk_img_name in enumerate(available_images_on_disk):
                    if i not in sequentially_assigned_disk_indices:
                        sequentially_assigned_disk_indices.add(i) 
                        replacement_image_tag = f"![{alt_text}]({md_img_assets_path}/{disk_img_name})"
                        logger.info(f"Sequentially mapping MD ref '{alt_text}' (path: {original_path_in_md}) to disk image: {disk_img_name}")
                        found_sequential = True
                        break
                if not found_sequential:
                    logger.warning(f"No specific or sequential disk image for MD ref: alt='{alt_text}', path='{original_path_in_md}'. Using error placeholder.")
                    replacement_image_tag = f"![{alt_text} (Image Not Found)]({md_img_assets_path}/placeholder-error.png)"
            
            new_content_parts.append(replacement_image_tag)

        new_content_parts.append(content[last_end:])
        processed_content = "".join(new_content_parts)
        
        final_linked_disk_images = set()
        for match in re.finditer(rf'!\[.*?\]\({re.escape(md_img_assets_path)}/([^\)]+?)\)', processed_content):
            img_filename_in_link = match.group(1)
            if not img_filename_in_link.startswith("placeholder-"):
                final_linked_disk_images.add(img_filename_in_link)

        truly_unused_disk_images = [
            disk_name for disk_name in available_images_on_disk if disk_name not in final_linked_disk_images
        ]

        if truly_unused_disk_images:
            logger.warning(f"Found {len(truly_unused_disk_images)} unreferenced disk images: {truly_unused_disk_images}")
            processed_content += (f"\n\n<!-- WARNING: {len(truly_unused_disk_images)} extracted images on disk "
                                  f"were not referenced in the markdown: {', '.join(truly_unused_disk_images)}. -->\n")
            
        return processed_content
