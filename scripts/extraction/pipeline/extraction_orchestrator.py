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
from ..markdown_processing import MarkdownFormatter
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

        # Determine the final target markdown path
        # If the suggestion is already a valid .md path, use it directly
        # Otherwise, use DirectoryManager to resolve the correct path
        if target_markdown_path_suggestion.lower().endswith('.md'):
            # The suggestion is already a complete .md path, use it directly
            final_target_markdown_path = os.path.abspath(target_markdown_path_suggestion)
            logger.debug(f"Using provided target path directly: {final_target_markdown_path}")
        else:
            # The suggestion needs to be resolved (e.g., still has .pdf extension or is incomplete)
            final_target_markdown_path = self.directory_manager.resolve_target_path(source_pdf_path)
            logger.debug(f"Resolved target path: {final_target_markdown_path}")
        
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
                
                # 5. Log image extraction summary
                self._log_image_extraction_summary(source_pdf_path, image_extraction_results)
                
                # 6. Log successful completion with timing
                duration = datetime.now() - start_time
                logger.info(f"Successfully transformed {source_pdf_path} to {final_target_markdown_path} in {duration.total_seconds():.2f} seconds")
                return True
            else:
                logger.error(f"Extraction and formatting failed for {source_pdf_path}: {result.get('error', 'Unknown error')}")
                return False

        except Exception as e:
            duration = datetime.now() - start_time
            logger.error(f"Unexpected error transforming {source_pdf_path} after {duration.total_seconds():.2f} seconds: {e}", exc_info=True)
            return False

    def _log_image_extraction_summary(self, source_pdf_path: str, image_extraction_results: Dict):
        """Log a summary of image extraction results."""
        if not image_extraction_results:
            logger.warning(f"No image extraction results reported for {source_pdf_path}")
            return
            
        total_images = image_extraction_results.get('total_images', 0)
        successfully_extracted = image_extraction_results.get('successfully_extracted', 0)
        failed_extractions = image_extraction_results.get('failed_extractions', 0)
        
        logger.info(f"Image extraction summary for {source_pdf_path}: {successfully_extracted}/{total_images} images extracted successfully")
        
        if failed_extractions > 0:
            logger.warning(f"{failed_extractions} image extractions failed for {source_pdf_path}")
            
        # Log any specific image issues
        issues = image_extraction_results.get('issues', [])
        for issue in issues:
            issue_type = issue.get('type', ImageIssueType.EXTRACTION_FAILED)
            message = issue.get('message', 'Unknown issue')
            logger.warning(f"Image issue in {source_pdf_path}: {issue_type.value} - {message}")