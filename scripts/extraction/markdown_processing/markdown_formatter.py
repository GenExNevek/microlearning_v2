# scripts/extraction/markdown_processing/markdown_formatter.py

"""
Main orchestrator for formatting extracted PDF content as markdown.
This class coordinates various specialist processors.
"""

import os
import re # For final cleanup
import logging
from typing import Dict, Optional, Any, Tuple # Ensure Tuple is imported

from ...config import settings, extraction_prompt # Relative import for settings and prompt
from ..image_processing.image_extractor import ImageExtractor # From parent package
from ..pdf_processing.pdf_reader import PDFReader # From parent package, for type hint

# Imports for specialist components from the current package
from .metadata_extractor import MetadataExtractor
from .frontmatter_generator import FrontmatterGenerator
from .content_processor import ContentProcessor
from .section_marker_processor import SectionMarkerProcessor
from .image_link_processor import ImageLinkProcessor

logger = logging.getLogger(__name__)

class MarkdownFormatter:
    """
    Orchestrates the PDF content extraction and markdown formatting pipeline
    using specialized components.
    """

    def __init__(self, pdf_reader: PDFReader):
        """Initialize with a PDFReader instance and specialist processors."""
        self.pdf_reader = pdf_reader
        
        self.metadata_extractor = MetadataExtractor()
        self.frontmatter_generator = FrontmatterGenerator()
        self.content_processor = ContentProcessor(self.frontmatter_generator)
        self.section_marker_processor = SectionMarkerProcessor()
        self.image_link_processor = ImageLinkProcessor()
        
        self.image_extractor = ImageExtractor()
        logger.info("MarkdownFormatter (orchestrator) initialized with all components.")

    def extract_metadata_from_path(self, pdf_path: str) -> Dict[str, Any]:
        """Delegates to MetadataExtractor to get path-based metadata."""
        return self.metadata_extractor.extract_metadata_from_path(pdf_path)

    def _get_image_assets_dir(self, pdf_path: str, metadata: Dict[str, Any]) -> Tuple[str, str]:
        """
        Determine the image assets directory path on disk.
        Returns the full path to the image assets directory and the base filename used for assets.
        """
        try:
            abs_pdf_source_dir = os.path.abspath(settings.PDF_SOURCE_DIR)
            abs_pdf_path = os.path.abspath(pdf_path)

            if abs_pdf_path.startswith(abs_pdf_source_dir):
                rel_path = os.path.relpath(abs_pdf_path, abs_pdf_source_dir)
            else:
                logger.warning(
                    f"PDF path {pdf_path} is not relative to PDF_SOURCE_DIR {abs_pdf_source_dir}. "
                    f"Using a structure based on PDF's parent directory name under target."
                )
                pdf_parent_dir_name = os.path.basename(os.path.dirname(abs_pdf_path))
                rel_path = os.path.join(pdf_parent_dir_name or "_external", os.path.basename(pdf_path))
        except ValueError as e: # pragma: no cover
            logger.warning(f"Could not determine relative path for {pdf_path}: {e}. Using basename.")
            rel_path = os.path.basename(pdf_path)
        except Exception as e: # pragma: no cover
            logger.error(f"Unexpected error processing PDF path {pdf_path}: {e}. Using basename fallback.")
            rel_path = os.path.basename(pdf_path)
        
        md_rel_base = os.path.splitext(rel_path)[0]
        target_md_parent_dir = os.path.join(settings.MARKDOWN_TARGET_DIR, os.path.dirname(md_rel_base))
        md_filename_without_ext = os.path.basename(md_rel_base) # This is the key: e.g., UNI0003_camb_as_physics_m1_l3
        img_assets_dir_name = f"{md_filename_without_ext}{settings.IMAGE_ASSETS_SUFFIX}"
        img_assets_full_path = os.path.join(target_md_parent_dir, img_assets_dir_name)
        
        try:
            os.makedirs(img_assets_full_path, exist_ok=True)
            logger.debug(f"Created/verified image assets directory: {img_assets_full_path}")
        except PermissionError as e: # pragma: no cover
            logger.error(f"Permission denied creating directory {img_assets_full_path}: {e}")
            import tempfile
            fallback_dir_name = f"microlearning_assets_{os.path.basename(target_md_parent_dir)}_{img_assets_dir_name}"
            fallback_dir = os.path.join(tempfile.gettempdir(), fallback_dir_name)
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                logger.warning(f"Using fallback directory due to permission error: {fallback_dir}")
                return fallback_dir, md_filename_without_ext
            except Exception as fallback_e:
                logger.critical(f"Failed to create fallback directory {fallback_dir}: {fallback_e}")
                raise RuntimeError(f"Cannot create image assets directory (permission error and fallback failed): {e}") from fallback_e
        except OSError as e: # pragma: no cover
            if hasattr(e, 'winerror') and e.winerror == 123: # ERROR_INVALID_NAME (Windows)
                 logger.error(f"Invalid characters in path for directory {img_assets_full_path}: {e}")
                 sanitized_img_assets_dir_name = re.sub(r'[<>:"/\\|?*]', '_', img_assets_dir_name)
                 if sanitized_img_assets_dir_name != img_assets_dir_name:
                    img_assets_full_path = os.path.join(target_md_parent_dir, sanitized_img_assets_dir_name)
                    try:
                        os.makedirs(img_assets_full_path, exist_ok=True)
                        logger.warning(f"Used sanitized directory name: {img_assets_full_path}")
                        # On success, md_filename_without_ext is still the logical base
                        # No need to change md_filename_without_ext for sanitized dir name
                    except Exception as sanitize_e:
                        logger.error(f"Failed to create directory even with sanitized name: {sanitize_e}")
                        raise RuntimeError(f"Cannot create image assets directory (invalid name and sanitize failed): {e}") from sanitize_e
                 else:
                    raise RuntimeError(f"Cannot create image assets directory (invalid name): {e}") from e

            elif "File name too long" in str(e) or (hasattr(e, 'errno') and e.errno == 36):  # ENAMETOOLONG
                max_len_component = 200 
                if len(img_assets_dir_name) > max_len_component:
                    # The original md_filename_without_ext is still the logical identifier for the content.
                    # We are truncating the directory name on disk, but links should conceptually use the original identifier
                    # to find files *within* that (potentially truncated name) directory.
                    # This assumes the filenames themselves within the directory are not affected by this truncation.
                    original_asset_suffix_len = len(settings.IMAGE_ASSETS_SUFFIX)
                    truncated_base_len = max_len_component - original_asset_suffix_len
                    if truncated_base_len <=0: # Should not happen with reasonable max_len_component
                         raise RuntimeError(f"Cannot create image assets directory (IMAGE_ASSETS_SUFFIX too long for max_len_component): {e}") from e

                    # Truncate md_filename_without_ext part if it's too long to form the directory name
                    # This is tricky because md_filename_without_ext is also used by ImageLinkProcessor.
                    # For now, let's assume md_filename_without_ext is the one used for the dir name base.
                    # If this base part `md_filename_without_ext` is too long, we must also use a truncated version
                    # for the `ImageLinkProcessor` later, or the paths won't match.
                    # However, the initial problem stated the *directory name* was wrong, not the *filenames inside*.
                    # So, we pass the *original* md_filename_without_ext, as it's the base for image *filenames*.
                    # The directory name itself gets truncated.
                    truncated_dir_name_component = img_assets_dir_name[:max_len_component]
                    
                    img_assets_full_path = os.path.join(target_md_parent_dir, truncated_dir_name_component)
                    try:
                        os.makedirs(img_assets_full_path, exist_ok=True)
                        logger.warning(f"Used truncated directory name due to length limit: {img_assets_full_path}")
                    except Exception as truncate_e:
                        logger.error(f"Failed to create directory even with truncated name: {truncate_e}")
                        raise RuntimeError(f"Cannot create image assets directory (name too long and truncate failed): {e}") from truncate_e
                else:
                    logger.error(f"OS error (possibly path too long overall) creating directory {img_assets_full_path}: {e}")
                    raise RuntimeError(f"Cannot create image assets directory (OS error, possibly path too long): {e}") from e
            else:
                logger.error(f"OS error creating directory {img_assets_full_path}: {e}")
                raise RuntimeError(f"Cannot create image assets directory (OS error): {e}") from e
        except Exception as e: # pragma: no cover
            logger.error(f"Unexpected error creating directory {img_assets_full_path}: {e}")
            raise RuntimeError(f"Cannot create image assets directory (unexpected error): {e}") from e
        
        return img_assets_full_path, md_filename_without_ext

    def _extract_images(self, pdf_info: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract images from the PDF file using ImageExtractor.
        Returns the full report dictionary from ImageExtractor.
        """
        pdf_path_for_extraction = pdf_info.get('normalized_path') or pdf_info.get('path')
        # Default in case of early exit or error determining it
        md_file_basename_for_assets = os.path.splitext(os.path.basename(pdf_path_for_extraction or "unknown_file"))[0]
        
        if not pdf_path_for_extraction:
            logger.warning("No PDF path available in pdf_info for image extraction.")
            return {
                'success': False, 'errors': ['No PDF path available'], 'extracted_count': 0, 
                'failed_count': 0, 'problematic_images': [], 'metrics': {}, 
                'output_dir': None, 'report_path': None,
                'md_file_basename_for_assets': md_file_basename_for_assets 
            }
        
        img_assets_output_dir = None
        try:
            img_assets_output_dir, md_file_basename_for_assets = self._get_image_assets_dir(pdf_path_for_extraction, metadata)
        except RuntimeError as e:
            logger.error(f"Failed to determine or create image assets directory: {e}")
            return {
                'success': False, 'errors': [f"Failed to get/create image assets directory: {e}"], 
                'extracted_count': 0, 'failed_count': 0, 'problematic_images': [], 
                'metrics': {}, 'output_dir': None, 'report_path': None,
                'md_file_basename_for_assets': md_file_basename_for_assets
            }
        
        try:
            results_report = self.image_extractor.extract_images_from_pdf(
                pdf_path_for_extraction, img_assets_output_dir
            )
            
            extracted_c = results_report.get('extracted_count', 0)
            failed_c = results_report.get('failed_count', 0)
            logger.info(
                f"Image extraction for {pdf_path_for_extraction}: "
                f"{extracted_c} extracted, {failed_c} failed/problematic."
            )
            if results_report.get('report_path'):
                logger.info(f"Image extraction report: {results_report['report_path']}")
            
            if 'output_dir' not in results_report:
                results_report['output_dir'] = img_assets_output_dir
            
            results_report['md_file_basename_for_assets'] = md_file_basename_for_assets
            
            return results_report
        except Exception as e: # pragma: no cover
            error_msg = f"Failed to extract images from {pdf_path_for_extraction}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False, 'errors': [error_msg], 'extracted_count': 0, 
                'failed_count': 0, 'problematic_images': [], 'metrics': {}, 
                'output_dir': img_assets_output_dir, 'report_path': None,
                'md_file_basename_for_assets': md_file_basename_for_assets
            }

    def extract_and_format(self, 
                           pdf_info: Dict[str, Any], 
                           metadata_override: Optional[Dict[str, Any]] = None 
                           ) -> Dict[str, Any]:
        """
        Main public method to extract content from PDF and format as markdown.
        """
        original_pdf_path = pdf_info.get('path')

        if metadata_override:
            current_metadata = metadata_override.copy()
        elif original_pdf_path:
            current_metadata = self.extract_metadata_from_path(original_pdf_path)
        else:
            current_metadata = self.extract_metadata_from_path("unknown_path.pdf")
            logger.warning("No PDF path or metadata override. Using default metadata.")
        
        if 'unit_title_id' not in current_metadata or not current_metadata['unit_title_id']:
             current_metadata['unit_title_id'] = os.path.splitext(os.path.basename(original_pdf_path or "unknown_unit"))[0]
             logger.warning(f"Missing 'unit_title_id' in metadata, derived as {current_metadata['unit_title_id']}")

        image_extraction_results = self._extract_images(pdf_info, current_metadata)
        
        prompt_text = extraction_prompt.get_extraction_prompt(current_metadata)
        
        raw_llm_content_str: Optional[str] = None
        try:
            if 'method' not in pdf_info or \
               (pdf_info['method'] == 'direct' and 'data' not in pdf_info) or \
               (pdf_info['method'] == 'file_api' and 'path' not in pdf_info):
                err_detail = f"Invalid pdf_info for Gemini: {pdf_info.get('method')}, Info: {pdf_info}"
                logger.error(err_detail)
                return {'success': False, 'error': err_detail, 'metadata': current_metadata, 'image_extraction': image_extraction_results}

            logger.info(f"Calling LLM ({pdf_info['method']}) for {original_pdf_path or 'direct data'}")
            if pdf_info['method'] == 'direct':
                response = self.pdf_reader._generate_content_direct(pdf_info['data'], prompt_text)
            else: # 'file_api'
                response = self.pdf_reader._generate_content_file_api(pdf_info['path'], prompt_text)
            
            raw_llm_content_str = response.text
            logger.info(f"LLM call successful for {original_pdf_path or 'direct data'}.")

        except Exception as e: # pragma: no cover
            err_msg = f"LLM content extraction failed for {original_pdf_path or 'unknown_pdf'}: {str(e)}"
            logger.error(err_msg, exc_info=True)
            return {'success': False, 'error': err_msg, 'metadata': current_metadata, 'image_extraction': image_extraction_results}

        if raw_llm_content_str is not None:
            try:
                processed_markdown, final_metadata = self.post_process_markdown(
                    raw_llm_content_str, current_metadata, 
                    image_extraction_results, original_pdf_path
                )
                return {
                    'success': True, 'content': processed_markdown,
                    'metadata': final_metadata, 'image_extraction': image_extraction_results
                }
            except Exception as e: # pragma: no cover
                err_msg = f"Markdown post-processing failed for {original_pdf_path or 'unknown_pdf'}: {str(e)}"
                logger.error(err_msg, exc_info=True)
                return {
                    'success': False, 'error': err_msg, 'content': raw_llm_content_str,
                    'metadata': current_metadata, 'image_extraction': image_extraction_results
                }
        return {'success': False, 'error': "LLM call did not produce content or failed silently.", 
                'metadata': current_metadata, 'image_extraction': image_extraction_results}


    def post_process_markdown(self,
                              raw_llm_content: str,
                              base_metadata: Dict[str, Any],
                              image_extraction_results: Optional[Dict[str, Any]],
                              original_pdf_path: Optional[str] = None
                             ) -> Tuple[str, Dict[str, Any]]:
        """
        Orchestrates post-processing of raw LLM content using specialized components.
        Returns the fully processed markdown string and the final merged metadata.
        """
        logger.info("Starting markdown post-processing orchestration.")

        content_with_final_frontmatter, merged_metadata = \
            self.content_processor.process_llm_output(raw_llm_content, base_metadata)
        
        match = re.match(r'^(---\s*\n(?:.|\n)*?\n---\s*)(\n\n)?((?:.|\n)*)', content_with_final_frontmatter, re.DOTALL)

        final_frontmatter_part = ""
        body_part = ""

        if match:
            final_frontmatter_part = match.group(1)
            body_part = match.group(3)
            
            if body_part:
                if not final_frontmatter_part.endswith("\n\n"):
                    final_frontmatter_part = final_frontmatter_part.rstrip('\n') + "\n\n"
            else:
                 final_frontmatter_part = final_frontmatter_part.rstrip('\n')
            
            logger.debug(f"Split generated frontmatter. Body length: {len(body_part)}")
        else:
            logger.warning("Could not reliably split final frontmatter from body using regex. Assuming no frontmatter or malformed.")
            body_part = content_with_final_frontmatter
            final_frontmatter_part = self.frontmatter_generator.generate_frontmatter(merged_metadata)
            if body_part:
                final_frontmatter_part += "\n\n"


        body_with_sections = self.section_marker_processor.process_sections(body_part)

        actual_img_assets_dir_on_disk = None
        if image_extraction_results:
            actual_img_assets_dir_on_disk = image_extraction_results.get('output_dir')
            if not actual_img_assets_dir_on_disk and image_extraction_results.get('report_path'): # pragma: no cover
                actual_img_assets_dir_on_disk = os.path.dirname(image_extraction_results.get('report_path'))
        
        if not actual_img_assets_dir_on_disk and original_pdf_path: # pragma: no cover
            logger.warning("Reconstructing actual_img_assets_dir_on_disk using original_pdf_path as it was missing from extraction results.")
            try:
                if 'unit_title_id' not in merged_metadata or not merged_metadata['unit_title_id']: # Ensure for _get_image_assets_dir
                    merged_metadata['unit_title_id'] = os.path.splitext(os.path.basename(original_pdf_path or "unknown_unit"))[0]
                
                # _get_image_assets_dir now returns a tuple, we only need the path here
                actual_img_assets_dir_on_disk, _ = self._get_image_assets_dir(original_pdf_path, merged_metadata)
            except RuntimeError as e:
                logger.error(f"Failed to reconstruct image assets directory: {e}")
                actual_img_assets_dir_on_disk = None
        elif not actual_img_assets_dir_on_disk: # pragma: no cover
            logger.error("Could not determine actual_img_assets_dir_on_disk. Image references may be incorrect or use placeholders.")

        # Determine the correct ID to use for image link path construction.
        id_for_image_links = None
        if image_extraction_results and image_extraction_results.get('md_file_basename_for_assets'):
            id_for_image_links = image_extraction_results['md_file_basename_for_assets']
            logger.debug(f"Using 'md_file_basename_for_assets' ({id_for_image_links}) for image link construction.")
        elif original_pdf_path:
            id_for_image_links = os.path.splitext(os.path.basename(original_pdf_path))[0]
            logger.warning(
                f"Using re-derived filename base '{id_for_image_links}' for image links "
                "as 'md_file_basename_for_assets' was missing from image_extraction_results."
            )
        else:
            id_for_image_links = merged_metadata.get('unit_title_id', 'unknown_unit') # This is the "shortened" one
            logger.warning(
                f"Falling back to metadata 'unit_title_id' ({id_for_image_links}) for image links "
                "due to missing reliable basename from image extraction or original path."
            )

        body_with_linked_images = self.image_link_processor.process_image_links(
            body_with_sections,
            id_for_image_links, # This should now be the full base like "UNI0003_camb_as_physics_m1_l3"
            image_extraction_results,
            actual_img_assets_dir_on_disk
        )
        
        final_body = body_with_linked_images.strip()
        
        if final_frontmatter_part and final_body:
            if not final_frontmatter_part.endswith('\n\n'):
                final_frontmatter_part = final_frontmatter_part.rstrip('\n') + '\n\n'
            fully_processed_content = final_frontmatter_part + final_body
        elif final_frontmatter_part:
            fully_processed_content = final_frontmatter_part.rstrip('\n')
        else:
            fully_processed_content = final_body

        if fully_processed_content:
            fully_processed_content = fully_processed_content.rstrip('\n') + '\n'
        else: # pragma: no cover
            fully_processed_content = ""

        logger.info("Completed markdown post-processing orchestration.")
        return fully_processed_content, merged_metadata