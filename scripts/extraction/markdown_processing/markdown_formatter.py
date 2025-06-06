# scripts/extraction/markdown_processing/markdown_formatter.py

"""
Main orchestrator for formatting extracted PDF content as markdown.
This class coordinates various specialist processors.
"""

import os
import re # For final cleanup
import logging
from typing import Dict, Optional, Any, Tuple

from ...config import settings, extraction_prompt # Relative import for settings and prompt
from ..image_extractor import ImageExtractor # From parent package
from ..pdf_reader import PDFReader # From parent package, for type hint

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

    def _get_image_assets_dir(self, pdf_path: str, metadata: Dict[str, Any]) -> str:
        """
        Determine the image assets directory path on disk.
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
        except ValueError:
            logger.warning(f"Could not determine relative path for {pdf_path}. Using basename.")
            rel_path = os.path.basename(pdf_path)
        
        md_rel_base = os.path.splitext(rel_path)[0]
        target_md_parent_dir = os.path.join(settings.MARKDOWN_TARGET_DIR, os.path.dirname(md_rel_base))
        md_filename_without_ext = os.path.basename(md_rel_base)
        img_assets_dir_name = f"{md_filename_without_ext}{settings.IMAGE_ASSETS_SUFFIX}"
        img_assets_full_path = os.path.join(target_md_parent_dir, img_assets_dir_name)
        
        os.makedirs(img_assets_full_path, exist_ok=True)
        return img_assets_full_path

    def _extract_images(self, pdf_info: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract images from the PDF file using ImageExtractor.
        Returns the full report dictionary from ImageExtractor.
        """
        pdf_path_for_extraction = pdf_info.get('normalized_path') or pdf_info.get('path')
        
        if not pdf_path_for_extraction:
            logger.warning("No PDF path available in pdf_info for image extraction.")
            return {
                'success': False, 'errors': ['No PDF path available'], 'extracted_count': 0, 
                'failed_count': 0, 'problematic_images': [], 'metrics': {}, 
                'output_dir': None, 'report_path': None
            }
        
        img_assets_output_dir = self._get_image_assets_dir(pdf_path_for_extraction, metadata)
        
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
            
            if 'output_dir' not in results_report: # Ensure output_dir is in the report
                results_report['output_dir'] = img_assets_output_dir
            
            return results_report
        except Exception as e:
            error_msg = f"Failed to extract images from {pdf_path_for_extraction}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False, 'errors': [error_msg], 'extracted_count': 0, 
                'failed_count': 0, 'problematic_images': [], 'metrics': {}, 
                'output_dir': img_assets_output_dir, 'report_path': None
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
            current_metadata = metadata_override
        elif original_pdf_path:
            current_metadata = self.extract_metadata_from_path(original_pdf_path)
        else:
            current_metadata = self.extract_metadata_from_path("unknown_path.pdf") # Default
            logger.warning("No PDF path or metadata override. Using default metadata.")
        
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

        except Exception as e:
            err_msg = f"LLM content extraction failed for {original_pdf_path}: {str(e)}"
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
            except Exception as e:
                err_msg = f"Markdown post-processing failed for {original_pdf_path}: {str(e)}"
                logger.error(err_msg, exc_info=True)
                return {
                    'success': False, 'error': err_msg, 'content': raw_llm_content_str,
                    'metadata': current_metadata, 'image_extraction': image_extraction_results
                }
        # This case should ideally be caught by the try-except block for LLM call
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
        
        # Split the final frontmatter from the body to process body independently
        # ContentProcessor ensures frontmatter ends with "\n---\n\n" or "\n---" if body is empty
        # A robust split looks for the end of the frontmatter block.
        frontmatter_end_marker = "\n---\n"
        fm_end_pos = content_with_final_frontmatter.find(frontmatter_end_marker)
        
        final_frontmatter_part = ""
        body_part = content_with_final_frontmatter # Default if no frontmatter found (should not happen)

        if fm_end_pos != -1:
            # Position after the marker itself
            actual_fm_end_pos = fm_end_pos + len(frontmatter_end_marker)
            final_frontmatter_part = content_with_final_frontmatter[:actual_fm_end_pos]
            body_part = content_with_final_frontmatter[actual_fm_end_pos:].lstrip('\n') # Remove leading newlines from body
        else:
            logger.warning("Could not reliably split final frontmatter from body. Processing entire content as body.")
            # This implies ContentProcessor might not have produced valid frontmatter.
            # For safety, we might want to regenerate frontmatter here based on merged_metadata
            # or assume no frontmatter was intended if ContentProcessor failed.
            # For now, assume body_part is the whole thing and final_frontmatter_part is empty.

        body_with_sections = self.section_marker_processor.process_sections(body_part)

        actual_img_assets_dir_on_disk = None
        if image_extraction_results:
            actual_img_assets_dir_on_disk = image_extraction_results.get('output_dir')
            if not actual_img_assets_dir_on_disk and image_extraction_results.get('report_path'):
                actual_img_assets_dir_on_disk = os.path.dirname(image_extraction_results.get('report_path'))
        
        if not actual_img_assets_dir_on_disk and original_pdf_path:
            logger.warning("Reconstructing actual_img_assets_dir_on_disk using original_pdf_path.")
            actual_img_assets_dir_on_disk = self._get_image_assets_dir(original_pdf_path, merged_metadata)
        elif not actual_img_assets_dir_on_disk:
            logger.error("Could not determine actual_img_assets_dir_on_disk. Image references may be incorrect.")

        body_with_linked_images = self.image_link_processor.process_image_links(
            body_with_sections,
            merged_metadata.get('unit_title_id', 'unknown_unit'),
            image_extraction_results,
            actual_img_assets_dir_on_disk
        )
        
        # Final cleanup from original post_process_markdown
        final_body = re.sub(r'(\n*)(<!--.*?-->)(\n*)', r'\n\n\2\n\n', body_with_linked_images)
        final_body = re.sub(r'\n{3,}', '\n\n', final_body).strip()

        fully_processed_content = final_frontmatter_part + final_body
        if final_frontmatter_part and final_body: # Ensure newline between them if both exist
             fully_processed_content = final_frontmatter_part.rstrip('\n') + "\n\n" + final_body

        logger.info("Completed markdown post-processing orchestration.")
        return fully_processed_content, merged_metadata