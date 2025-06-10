# scripts/extraction/pipeline/batch_processor.py

"""
Module for batch processing of PDF files.
"""

import os
import logging
from typing import Dict, List, Any, Optional

from ...config import settings
from .extraction_orchestrator import ExtractionOrchestrator
from ..output_management import DirectoryManager

logger = logging.getLogger(__name__)

class BatchProcessor:
    """
    Handles batch operations on multiple PDF files, coordinating with
    the ExtractionOrchestrator for individual file transformations.
    """

    def __init__(self,
                 extraction_orchestrator: Optional[ExtractionOrchestrator] = None,
                 directory_manager: Optional[DirectoryManager] = None):
        self.orchestrator = extraction_orchestrator or ExtractionOrchestrator()
        self.directory_manager = directory_manager or DirectoryManager()
        logger.info("BatchProcessor initialized.")

    def process_single_file(self, pdf_path: str) -> Dict[str, Any]:
        """
        Processes a single PDF file.
        This method encapsulates logic from the original main.py's process_single_file.

        Args:
            pdf_path: Path to the single PDF file to process.

        Returns:
            A dictionary summarizing the result:
            {'success_count': int, 'failure_count': int, 'failures': list[str]}
        """
        logger.info(f"Processing single file: {pdf_path}")
        
        # DirectoryManager resolves the final target path based on source and configured target structure
        # The second argument to orchestrator.transform_pdf_to_markdown is a suggestion;
        # the orchestrator itself might refine it or use DirectoryManager.resolve_target_path.
        # For simplicity, we can let the orchestrator handle the final target path resolution
        # by passing a "nominal" target path.
        # Let's use the DirectoryManager here to get the correct target path suggestion.
        target_markdown_path = self.directory_manager.resolve_target_path(pdf_path)
        
        success = self.orchestrator.transform_pdf_to_markdown(pdf_path, target_markdown_path)
        
        return {
            'success_count': 1 if success else 0,
            'failure_count': 0 if success else 1,
            'failures': [] if success else [pdf_path]
        }

    def process_directory(self, source_directory_path: str) -> Dict[str, Any]:
        """
        Processes all PDF files in a given directory and its subdirectories.
        The output structure will mirror the source directory structure under the
        configured MARKDOWN_TARGET_DIR or a target derived from source_directory_path
        if it's outside PDF_SOURCE_DIR.

        Args:
            source_directory_path: Path to the directory containing PDF files.

        Returns:
            A dictionary summarizing the results.
        """
        abs_source_directory_path = os.path.abspath(source_directory_path)
        logger.info(f"Processing directory: {abs_source_directory_path}")

        # Determine the base target directory for mirroring
        # If source_directory_path is within settings.PDF_SOURCE_DIR, mirror relative to that.
        # Otherwise, mirror the source_directory_path's basename into settings.MARKDOWN_TARGET_DIR.
        
        norm_pdf_source_dir = os.path.normpath(settings.PDF_SOURCE_DIR)
        norm_abs_source_dir = os.path.normpath(abs_source_directory_path)
        norm_markdown_target_dir = os.path.normpath(settings.MARKDOWN_TARGET_DIR)

        target_base_for_mirroring: str
        if norm_abs_source_dir.startswith(norm_pdf_source_dir + os.sep) or norm_abs_source_dir == norm_pdf_source_dir:
            rel_subdir = os.path.relpath(norm_abs_source_dir, norm_pdf_source_dir)
            target_base_for_mirroring = os.path.join(norm_markdown_target_dir, rel_subdir)
        else:
            # Directory to process is outside the main PDF_SOURCE_DIR
            dir_name = os.path.basename(norm_abs_source_dir)
            target_base_for_mirroring = os.path.join(norm_markdown_target_dir, dir_name)
            logger.warning(
                f"Directory {source_directory_path} is outside PDF_SOURCE_DIR. "
                f"Mirroring its structure under {target_base_for_mirroring}"
            )
        
        target_base_for_mirroring = os.path.normpath(target_base_for_mirroring)
        
        # The transform_func for mirror_directory_structure is the orchestrator's method.
        # It needs (source_file, target_file_suggestion)
        # The mirror_directory_structure will provide a structurally correct target_file_suggestion.
        results = self.directory_manager.mirror_directory_structure(
            source_dir_to_walk=abs_source_directory_path,
            target_base_dir_for_mirroring=target_base_for_mirroring,
            transform_func=self.orchestrator.transform_pdf_to_markdown
        )
        return results

    def process_batch_by_id(self, batch_id: Optional[str]) -> Dict[str, Any]:
        """
        Processes a batch of PDF files based on a batch ID.
        If batch_id is None or "ALL", processes the entire PDF_SOURCE_DIR.
        Otherwise, assumes batch_id is a subdirectory within PDF_SOURCE_DIR.

        Args:
            batch_id: The ID of the batch (subdirectory name) or None/"ALL".

        Returns:
            A dictionary summarizing the results.
        """
        if not batch_id or batch_id.upper() == 'ALL':
            logger.info("Processing all batches in PDF_SOURCE_DIR.")
            return self.process_directory(settings.PDF_SOURCE_DIR)
        else:
            batch_directory = os.path.join(settings.PDF_SOURCE_DIR, batch_id)
            if os.path.isdir(batch_directory):
                logger.info(f"Processing batch ID '{batch_id}' from directory: {batch_directory}")
                return self.process_directory(batch_directory)
            else:
                err_msg = f"Directory not found for batch ID '{batch_id}' at {batch_directory}"
                logger.error(err_msg)
                return {'success_count': 0, 'failure_count': 0, 'failures': [err_msg]}
    
    def process_by_course_id(self, course_id_prefix: str) -> Dict[str, Any]:
        """Processes PDFs in a directory starting with the given course ID prefix."""
        logger.info(f"Attempting to process by course ID prefix: {course_id_prefix}")
        try:
            for item in os.listdir(settings.PDF_SOURCE_DIR):
                item_path = os.path.join(settings.PDF_SOURCE_DIR, item)
                if os.path.isdir(item_path) and item.lower().startswith(course_id_prefix.lower()):
                    logger.info(f"Found and processing course directory: {item_path}")
                    return self.process_directory(item_path)
            
            err_msg = f"Course directory starting with '{course_id_prefix}' not found in {settings.PDF_SOURCE_DIR}"
            logger.error(err_msg)
            return {'success_count': 0, 'failure_count': 1, 'failures': [err_msg]}
        except FileNotFoundError:
            err_msg = f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}"
            logger.error(err_msg)
            return {'success_count': 0, 'failure_count': 1, 'failures': [err_msg]}


    def process_by_module_id(self, module_id_prefix: str) -> Dict[str, Any]:
        """Processes PDFs in a directory (anywhere under PDF_SOURCE_DIR) starting with the module ID prefix."""
        logger.info(f"Attempting to process by module ID prefix: {module_id_prefix}")
        try:
            for root, dirs, _ in os.walk(settings.PDF_SOURCE_DIR):
                for dir_name in dirs:
                    if dir_name.lower().startswith(module_id_prefix.lower()):
                        module_path = os.path.join(root, dir_name)
                        logger.info(f"Found and processing module directory: {module_path}")
                        return self.process_directory(module_path)
            
            err_msg = f"Module directory starting with '{module_id_prefix}' not found under {settings.PDF_SOURCE_DIR}"
            logger.error(err_msg)
            return {'success_count': 0, 'failure_count': 1, 'failures': [err_msg]}
        except FileNotFoundError:
            err_msg = f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}"
            logger.error(err_msg)
            return {'success_count': 0, 'failure_count': 1, 'failures': [err_msg]}