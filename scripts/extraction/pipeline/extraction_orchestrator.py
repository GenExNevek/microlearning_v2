# scripts/extraction/pipeline/extraction_orchestrator.py

"""
Module for the core PDF-to-markdown transformation logic for a single file.
"""

import os
import logging
import shutil
from typing import Dict, Optional
from datetime import datetime

from ...config import settings
from ..pdf_processing import PDFReader
from ..markdown_formatter import MarkdownFormatter
from ..output_management import FileWriter, DirectoryManager
from ...utils.image_validation import ImageIssueType

logger = logging.getLogger(__name__)

class ExtractionOrchestrator:
    """
    Orchestrates the transformation of a single PDF file to markdown,
    including image extraction and placeholder management.
    """

    def __init__(self,
                 pdf_reader: Optional[PDFReader] = None,
                 markdown_formatter: Optional[MarkdownFormatter] = None,
                 file_writer: Optional[FileWriter] = None,
                 directory_manager: Optional[DirectoryManager] = None):
        self.pdf_reader = pdf_reader or PDFReader()
        # MarkdownFormatter initializes ImageExtractor internally
        self.markdown_formatter = markdown_formatter or MarkdownFormatter(self.pdf_reader)
        self.file_writer = file_writer or FileWriter()
        self.directory_manager = directory_manager or DirectoryManager()
        
        logger.info("ExtractionOrchestrator initialized.")

    def transform_pdf_to_markdown(self, source_pdf_path: str, target_markdown_path_suggestion: str) -> bool:
        """
        Transforms a single PDF file to a markdown file.
        This method encapsulates the logic from the original main.py's transform_pdf_to_markdown.

        Args:
            source_pdf_path: Path to the source PDF file.
            target_markdown_path_suggestion: A suggested path for the target markdown file.
                                             The actual path might be modified (e.g. .pdf -> .md).

        Returns:
            Boolean indicating success or failure of the transformation.
        """
        start_time = datetime.now()
        
        if not source_pdf_path.lower().endswith('.pdf'):
            logger.info(f"Skipping non-PDF file: {source_pdf_path}")
            return False

        # Determine the final target markdown path using DirectoryManager for consistency
        # The suggestion might already be correct, but this ensures proper extension and structure.
        # The DirectoryManager's resolve_target_path is designed for this.
        # It expects the source PDF path and will derive the .md path in the target structure.
        # The target_markdown_path_suggestion's directory part can be used as custom_target_dir
        # if it's different from the default configured markdown_target_dir.
        
        # We need the target directory from the suggestion to pass to resolve_target_path
        # if it's meant to override the default.
        custom_target_dir_from_suggestion = os.path.dirname(target_markdown_path_suggestion)
        
        final_target_markdown_path = self.directory_manager.resolve_target_path(
            source_pdf_path,
            custom_target_dir=custom_target_dir_from_suggestion
        )
        
        target_markdown_dir = os.path.dirname(final_target_markdown_path)

        if not self.directory_manager.ensure_directory(target_markdown_dir):
            logger.error(f"Failed to create or access target directory {target_markdown_dir} for {final_target_markdown_path}")
            return False

        logger.info(f"Starting transformation: {source_pdf_path} -> {final_target_markdown_path}")

        try:
            # 1. Read PDF (determines method: direct or file_api)
            # The threshold for File API is handled within PDFReader
            pdf_info = self.pdf_reader.read_pdf_from_path(source_pdf_path)
            if pdf_info.get('error'):
                logger.error(f"Failed to read PDF {source_pdf_path}: {pdf_info['error']}")
                return False

            # 2. Extract metadata (path-based)
            # MarkdownFormatter's extract_metadata_from_path uses its internal MetadataExtractor
            path_based_metadata = self.markdown_formatter.extract_metadata_from_path(source_pdf_path)
            
            # 3. Core extraction and formatting (LLM call, image extraction, markdown processing)
            # MarkdownFormatter.extract_and_format now returns a dict with 'content', 'metadata', 'image_extraction'
            # It internally calls its _extract_images method.
            result = self.markdown_formatter.extract_and_format(pdf_info, path_based_metadata)
            
            image_extraction_results = result.get('image_extraction', {}) # This is the report from ImageExtractor

            if result.get('success'):
                # 4. Write markdown file
                if not self.file_writer.write_markdown_file(result['content'], final_target_markdown_path):
                    logger.error(f"Failed to write markdown file: {final_target_markdown_path}")
                    # Continue to log image issues even if write fails, but overall transform is False
                    self._log_image_extraction_summary(source_pdf_path, image_extraction_results)
                    return False
                
                # 5. Process image extraction issues (e.g., create placeholders in the specific asset folder)
                # Determine the actual image assets folder path on disk.
                # This path should come from the image_extraction_results if available.
                img_assets_folder_disk_path = None
                if image_extraction_results and image_extraction_results.get('output_dir'):
                    img_assets_folder_disk_path = image_extraction_results['output_dir']
                elif image_extraction_results and image_extraction_results.get('report_path'): # Fallback
                     img_assets_folder_disk_path = os.path.dirname(image_extraction_results['report_path'])
                else: # Fallback: reconstruct using formatter's logic (less ideal but a backup)
                     logger.warning("Could not determine image assets folder from extraction report for placeholder creation, reconstructing.")
                     # This requires the metadata that was used by the formatter to create the path.
                     # The formatter's _get_image_assets_dir uses the *final* metadata.
                     final_metadata_from_result = result.get('metadata', path_based_metadata)
                     try:
                        img_assets_folder_disk_path, _ = self.markdown_formatter._get_image_assets_dir(source_pdf_path, final_metadata_from_result)
                     except RuntimeError as e:
                        logger.error(f"Error reconstructing image assets folder path: {e}")


                if img_assets_folder_disk_path:
                    self._process_image_extraction_issues_for_file(
                        image_extraction_results,
                        img_assets_folder_disk_path
                    )
                else:
                    logger.warning(f"Could not determine image assets folder for {source_pdf_path}. Skipping placeholder creation for this file.")

                self._log_image_extraction_summary(source_pdf_path, image_extraction_results)
                elapsed_time = datetime.now() - start_time
                logger.info(f"Successfully transformed: {source_pdf_path} -> {final_target_markdown_path} in {elapsed_time}")
                return True
            else:
                logger.error(f"Error transforming {source_pdf_path}: {result.get('error', 'Unknown error in markdown_formatter')}")
                self._log_image_extraction_summary(source_pdf_path, image_extraction_results, is_error_context=True)
                return False

        except Exception as e: # pragma: no cover
            logger.error(f"Unhandled exception processing {source_pdf_path}: {str(e)}", exc_info=True)
            return False

    def _log_image_extraction_summary(self, source_file: str, image_extraction_results: Dict, is_error_context: bool = False):
        """Logs a summary of image extraction results."""
        if not image_extraction_results:
            logger.info(f"No image extraction results to log for {source_file}.")
            return

        context_msg = "(during failed transform)" if is_error_context else ""
        
        extracted_ok = image_extraction_results.get('extracted_count', 0)
        failed_processing_or_extraction = image_extraction_results.get('failed_count', 0)
        # problematic_count from reporter is len(problematic_images)
        problematic_reported = image_extraction_results.get('problematic_count', len(image_extraction_results.get('problematic_images',[])))
        report_file_path = image_extraction_results.get('report_path')

        if failed_processing_or_extraction > 0 or problematic_reported > 0:
            logger.warning(
                f"Image extraction for {source_file} {context_msg}: "
                f"{extracted_ok} extracted successfully, "
                f"{failed_processing_or_extraction} failed extraction/processing/validation, "
                f"{problematic_reported} images reported as problematic."
            )
            if report_file_path:
                logger.warning(f"Detailed image extraction report: {report_file_path}")
        else:
            logger.info(f"Image extraction for {source_file} {context_msg}: {extracted_ok} images extracted successfully.")
            if report_file_path:
                logger.info(f"Image extraction report: {report_file_path}")
        
        for err_msg in image_extraction_results.get('errors', []):
            logger.error(f"Image extraction top-level error for {source_file} {context_msg}: {err_msg}")
        
        if is_error_context and image_extraction_results.get('problematic_images'):
            logger.error(f"Problematic image details for {source_file} {context_msg}:")
            for p_img in image_extraction_results['problematic_images']:
                logger.error(f"  - Page {p_img.get('page_num','?')}, Index {p_img.get('img_index_on_page','?')}: {p_img.get('issue_type','unknown')} - {p_img.get('issue_details','no details')}")


    def _process_image_extraction_issues_for_file(self, extraction_results: Dict, img_assets_folder_disk_path: str):
        """
        Checks for issues in image extraction results for a specific file's assets
        and creates placeholder images if needed.
        """
        if extraction_results.get('problematic_images') or extraction_results.get('failed_count', 0) > 0:
            logger.info(f"Image extraction issues detected for {os.path.basename(img_assets_folder_disk_path)}. Ensuring placeholders in {img_assets_folder_disk_path}")
            self.create_placeholder_images_in_folder(img_assets_folder_disk_path) # Call the shared method
        else:
            logger.debug(f"No problematic images reported. Placeholder check skipped for {img_assets_folder_disk_path}")

    def create_placeholder_images_in_folder(self, target_assets_folder_disk_path: str):
        """
        Creates or copies standard placeholder images into a specified assets folder.
        This is the logic from main.py's create_placeholder_images.

        Args:
            target_assets_folder_disk_path: Folder to place placeholder images (e.g., a specific unit's asset folder or global).
        """
        # Source of global placeholders
        global_placeholders_dir = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')
        
        # Ensure global placeholder source dir exists (it might contain pre-made placeholders)
        if not self.directory_manager.ensure_directory(global_placeholders_dir):
            logger.error(f"Cannot create or access global placeholder source directory: {global_placeholders_dir}. Placeholders may not be copied.")
            # We can still try to generate them directly in the target.

        # Ensure target assets dir exists
        if not self.directory_manager.ensure_directory(target_assets_folder_disk_path):
            logger.error(f"Cannot create or access target assets directory: {target_assets_folder_disk_path}. Cannot create placeholders.")
            return

        placeholders_to_create = {
            # filename: text_for_generation
            'placeholder-blank.png': "Blank Image Detected",
            'placeholder-corrupt.png': "Corrupt Image Data",
            'placeholder-error.png': "Image Extraction Error",
            'placeholder-missing.png': "Image Not Found",
            # Add more based on ImageIssueType or common scenarios
        }

        for placeholder_filename, message_text in placeholders_to_create.items():
            target_placeholder_path = os.path.join(target_assets_folder_disk_path, placeholder_filename)
            source_placeholder_path = os.path.join(global_placeholders_dir, placeholder_filename)

            if os.path.exists(target_placeholder_path):
                # logger.debug(f"Placeholder {placeholder_filename} already exists in {target_assets_folder_disk_path}")
                continue

            # Try copying from global placeholders first
            if os.path.exists(source_placeholder_path):
                try:
                    shutil.copy2(source_placeholder_path, target_placeholder_path)
                    logger.debug(f"Copied global placeholder {source_placeholder_path} to {target_placeholder_path}")
                    continue # Copied successfully
                except Exception as e:
                    logger.warning(f"Failed to copy global placeholder {source_placeholder_path} to {target_placeholder_path}: {e}. Will try to generate.")
            
            # If source doesn't exist or copy failed, generate a new one
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new('RGB', (300, 200), color=(220, 220, 220))
                draw = ImageDraw.Draw(img)
                try:
                    # Attempt to load a common font, fall back to default
                    font = ImageFont.truetype("arial.ttf", 15)
                except IOError:
                    font = ImageFont.load_default()
                
                # Simple text centering
                text_bbox = draw.textbbox((0,0), message_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                x = (img.width - text_width) / 2
                y = (img.height - text_height) / 2
                
                draw.text((x, y), message_text, fill=(0, 0, 0), font=font)
                img.save(target_placeholder_path)
                logger.debug(f"Generated placeholder image: {target_placeholder_path}")
            except ImportError: # pragma: no cover
                logger.error("Pillow (PIL) not installed. Cannot generate placeholder images. Please install `Pillow`.")
                break # Stop trying if Pillow is missing for all subsequent placeholders
            except Exception as e: # pragma: no cover
                logger.error(f"Failed to generate placeholder image {target_placeholder_path}: {e}")