# scripts/extraction/markdown_processing/image_link_processor.py

"""Module for processing image references in markdown content."""

import os
import re
import logging
from typing import Dict, Optional, Any, Set

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
        # Add more specific placeholders if ImageIssueType expands
        return "placeholder-error.png" # Generic error or unhandled issue type

    def process_image_links(self,
                            content: str,
                            unit_title_id: str,
                            image_extraction_results: Optional[Dict[str, Any]],
                            actual_disk_img_assets_path: Optional[str]
                           ) -> str:
        """
        Process image references in the markdown content.
        """
        safe_unit_title_id = re.sub(r'[^\w\-_\.]', '_', unit_title_id)
        img_assets_dir_name_for_md = f"{safe_unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        md_img_assets_path = f"./{img_assets_dir_name_for_md}"

        logger.debug(f"Processing image references. MD assets path: {md_img_assets_path}, Disk assets path: {actual_disk_img_assets_path}")

        if not image_extraction_results or not actual_disk_img_assets_path or not os.path.exists(actual_disk_img_assets_path):
            logger.warning(
                f"Image extraction results or disk image assets path not available/found "
                f"({actual_disk_img_assets_path}). Using generic image references for local images."
            )
            
            def generic_replace(match):
                alt_text = match.group(1)
                original_path_in_md = match.group(2)
                if original_path_in_md.startswith(('http://', 'https://', '/', 'data:')):
                    return match.group(0)
                # Use a generic placeholder for unresolvable local images
                return f"![{alt_text}]({md_img_assets_path}/placeholder-image.png)"

            content = re.sub(self.img_pattern, generic_replace, content)
            content += (f"\n\n<!-- WARNING: Image extraction results not fully available or "
                        f"assets directory missing ({actual_disk_img_assets_path}). "
                        f"Local image links may be placeholders. -->\n")
            return content

        try:
            saved_image_files = sorted([
                f for f in os.listdir(actual_disk_img_assets_path)
                if os.path.isfile(os.path.join(actual_disk_img_assets_path, f)) and
                   f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) and
                   not f.startswith('placeholder-')
            ])
            logger.debug(f"Found {len(saved_image_files)} saved image files in {actual_disk_img_assets_path}: {saved_image_files}")
        except FileNotFoundError:
            logger.warning(f"Disk image assets directory not found: {actual_disk_img_assets_path}. Cannot list saved images.")
            saved_image_files = []
        
        available_images_on_disk = saved_image_files[:]
        
        problematic_images_info: Dict[str, Dict[str, Any]] = {}
        if image_extraction_results.get('problematic_images'):
            for p_img in image_extraction_results['problematic_images']:
                page = p_img.get('page')
                index_on_page = p_img.get('index_on_page') # 0-indexed from extractor
                if page is not None and index_on_page is not None:
                    key = f"{page}-{index_on_page + 1}" # Key is 1-indexed for page and index
                    problematic_images_info[key] = p_img
        logger.debug(f"Problematic images info (keyed by 'page-idx'): {problematic_images_info}")

        processed_disk_image_indices: Set[int] = set()

        def replace_image_smartly(match):
            alt_text = match.group(1)
            original_path_in_md = match.group(2)

            if original_path_in_md.startswith(('http://', 'https://', '/', 'data:')):
                return match.group(0)

            logger.debug(f"Found MD image: alt='{alt_text}', original_path='{original_path_in_md}'")
            
            page_num, img_idx_on_page = None, None # Parsed, 1-indexed

            # Attempt 1: Parse from filename in MD link (e.g., figX-pageY-imgZ.png)
            # Expects Y and Z to be 1-indexed in filenames
            fn_match = re.search(r'page(\d+)[-_]?img(\d+)', original_path_in_md, re.IGNORECASE)
            if fn_match:
                page_num = int(fn_match.group(1))
                img_idx_on_page = int(fn_match.group(2))
                logger.debug(f"Parsed from MD path filename: page={page_num}, idx_on_page={img_idx_on_page}")

            # Attempt 2: Parse from alt text
            if page_num is None or img_idx_on_page is None:
                alt_text_lower = alt_text.lower()
                page_match_alt = re.search(r'page\s*(\d+)', alt_text_lower)
                if page_match_alt: page_num = int(page_match_alt.group(1))

                img_match_alt = re.search(r'(?:image|figure|fig|img)\s*(?:(\d+)\s*\.\s*(\d+)|(\d+))', alt_text_lower)
                if img_match_alt:
                    if img_match_alt.group(1) and img_match_alt.group(2): # P.I format
                        if page_num is None: page_num = int(img_match_alt.group(1))
                        img_idx_on_page = int(img_match_alt.group(2))
                    elif img_match_alt.group(3): # Just I format
                        img_idx_on_page = int(img_match_alt.group(3))
                logger.debug(f"Parsed from alt text: page={page_num}, idx_on_page={img_idx_on_page}")

            if page_num is not None and img_idx_on_page is not None:
                problem_key = f"{page_num}-{img_idx_on_page}"
                if problem_key in problematic_images_info:
                    issue_info = problematic_images_info[problem_key]
                    issue_type_val = issue_info.get('issue_type', ImageIssueType.OTHER.value)
                    issue_details = issue_info.get('issue', 'Details not available')
                    placeholder_filename = self._determine_placeholder_name(issue_type_val)
                    warning_comment = (f"\n<!-- WARNING: Image from Page {page_num}, Index {img_idx_on_page} "
                                       f"had an issue: {issue_type_val}. Details: {issue_details}. "
                                       f"Using placeholder: {placeholder_filename}. -->\n")
                    logger.warning(f"Image ref P{page_num}-I{img_idx_on_page} was problematic: {issue_type_val}. Using placeholder.")
                    return f"{warning_comment}![{alt_text} (Issue: {issue_type_val})]({md_img_assets_path}/{placeholder_filename})"

            target_saved_image_filename = None
            if page_num is not None and img_idx_on_page is not None:
                for i, disk_img_name in enumerate(available_images_on_disk):
                    if i in processed_disk_image_indices: continue
                    disk_fn_match = re.search(r'page(\d+)[-_]?img(\d+)\.', disk_img_name, re.IGNORECASE)
                    if disk_fn_match:
                        saved_page = int(disk_fn_match.group(1))
                        saved_idx = int(disk_fn_match.group(2))
                        if saved_page == page_num and saved_idx == img_idx_on_page:
                            target_saved_image_filename = disk_img_name
                            processed_disk_image_indices.add(i)
                            logger.info(f"Matched MD ref (P:{page_num}, I:{img_idx_on_page}) to disk image: {target_saved_image_filename}")
                            break
            
            if target_saved_image_filename:
                return f"![{alt_text}]({md_img_assets_path}/{target_saved_image_filename})"
            else:
                # Fallback: Sequential mapping for unmatched or unparsed references
                for i, disk_img_name in enumerate(available_images_on_disk):
                    if i not in processed_disk_image_indices:
                        processed_disk_image_indices.add(i)
                        logger.info(f"Sequentially mapping MD ref '{alt_text}' (path: {original_path_in_md}) to disk image: {disk_img_name}")
                        return f"![{alt_text}]({md_img_assets_path}/{disk_img_name})"

            logger.warning(f"No matching or available disk image for MD ref: alt='{alt_text}', path='{original_path_in_md}'. Using error placeholder.")
            return f"![{alt_text} (Image Not Found)]({md_img_assets_path}/placeholder-error.png)"

        processed_content = re.sub(self.img_pattern, replace_image_smartly, content)
        
        unused_disk_images = [
            img_name for i, img_name in enumerate(available_images_on_disk) 
            if i not in processed_disk_image_indices
        ]
        if unused_disk_images:
            logger.warning(f"Found {len(unused_disk_images)} unreferenced disk images: {unused_disk_images}")
            processed_content += (f"\n\n<!-- WARNING: {len(unused_disk_images)} extracted images on disk "
                                  f"were not referenced in the markdown: {', '.join(unused_disk_images)}. -->\n")
            
        return processed_content