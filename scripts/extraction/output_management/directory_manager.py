# scripts/extraction/output_management/directory_manager.py

"""Module for directory structure management and validation."""

import os
import logging
import shutil
from typing import Callable, Dict, Any, Optional, Tuple

from ...config import settings # For default paths like PDF_SOURCE_DIR, MARKDOWN_TARGET_DIR

logger = logging.getLogger(__name__)

class DirectoryManager:
    """Manages directory structures, mirroring, and path resolution."""

    def __init__(self, pdf_source_dir: Optional[str] = None, markdown_target_dir: Optional[str] = None):
        self.pdf_source_dir = os.path.abspath(pdf_source_dir or settings.PDF_SOURCE_DIR)
        self.markdown_target_dir = os.path.abspath(markdown_target_dir or settings.MARKDOWN_TARGET_DIR)
        logger.debug(f"DirectoryManager initialized with PDF source: {self.pdf_source_dir}, Markdown target: {self.markdown_target_dir}")

    def ensure_directory(self, directory_path: str) -> bool:
        """Ensures a directory exists, creating it if necessary. (Helper, similar to FileWriter's)"""
        if not os.path.exists(directory_path):
            try:
                os.makedirs(directory_path, exist_ok=True)
                logger.debug(f"Created directory: {directory_path}")
                return True
            except OSError as e:
                logger.error(f"Failed to create directory {directory_path}: {e}", exc_info=True)
                return False
        elif not os.path.isdir(directory_path):
            logger.error(f"Path exists but is not a directory: {directory_path}")
            return False
        return True
    
    def validate_path_permissions(self, path: str, mode: str = 'read') -> Tuple[bool, str]:
        """Validates read/write permissions for a path."""
        # This can reuse logic from PDFValidator or be a common utility
        if not os.path.exists(path):
            return False, f"Path does not exist: {path}"

        access_mode = os.R_OK if mode == 'read' else os.W_OK
        if os.access(path, access_mode):
            return True, f"{mode.capitalize()} permission granted for: {path}"
        else:
            return False, f"No {mode} permission for: {path}"


    def resolve_target_path(self, source_pdf_path: str, custom_target_dir: Optional[str] = None) -> str:
        """
        Resolves the target markdown file path based on the source PDF path,
        maintaining relative structure from `pdf_source_dir` to `markdown_target_dir`.
        Handles cases where source_pdf_path is outside `pdf_source_dir`.

        Args:
            source_pdf_path: Absolute or relative path to the source PDF.
            custom_target_dir: Optional custom base target directory. Uses self.markdown_target_dir if None.

        Returns:
            The absolute path for the target markdown file.
        """
        abs_source_pdf_path = os.path.abspath(source_pdf_path)
        target_base_dir = os.path.abspath(custom_target_dir or self.markdown_target_dir)

        rel_path_to_source_file_dir: str
        source_filename = os.path.basename(abs_source_pdf_path)
        
        # Normalize paths to handle potential trailing slashes and OS differences
        norm_abs_source_pdf_path = os.path.normpath(abs_source_pdf_path)
        norm_pdf_source_dir = os.path.normpath(self.pdf_source_dir)

        try:
            if norm_abs_source_pdf_path.startswith(norm_pdf_source_dir + os.sep) or norm_abs_source_pdf_path == norm_pdf_source_dir : # Check if it's inside or is the dir itself
                 # Path of the source file relative to pdf_source_dir
                rel_path_to_source_file = os.path.relpath(norm_abs_source_pdf_path, norm_pdf_source_dir)
            else:
                # File is outside the standard source dir.
                # Place it in a subfolder in the target named after the PDF's original parent directory.
                logger.warning(
                    f"PDF path {source_pdf_path} is not relative to configured PDF_SOURCE_DIR {self.pdf_source_dir}. "
                    f"Using a nested structure under target based on PDF's parent directory."
                )
                pdf_parent_dir_name = os.path.basename(os.path.dirname(norm_abs_source_pdf_path))
                if not pdf_parent_dir_name:  # If PDF is in root (e.g. "C:\file.pdf")
                    pdf_parent_dir_name = "_external_root_pdfs"
                rel_path_to_source_file = os.path.join(pdf_parent_dir_name, source_filename)
        except ValueError: # Catches issues like different drives on Windows for relpath
            logger.warning(
                f"Could not determine relative path for {source_pdf_path} (e.g., different drives). "
                f"Placing in '_external_pdfs' subdirectory under target."
            )
            target_filename_only = os.path.basename(norm_abs_source_pdf_path)
            rel_path_to_source_file = os.path.join("_external_pdfs", target_filename_only)

        # Change extension from .pdf to .md
        target_rel_path_md = os.path.splitext(rel_path_to_source_file)[0] + ".md"
        
        # Construct full target path
        abs_target_md_path = os.path.join(target_base_dir, target_rel_path_md)
        return os.path.normpath(abs_target_md_path)


    def mirror_directory_structure(
        self,
        source_dir_to_walk: str,
        target_base_dir_for_mirroring: str,
        transform_func: Callable[[str, str], bool]
    ) -> Dict[str, Any]:
        """
        Mirrors directory structure from a source to a target, applying a transformation
        function to files. This function is extracted from the original FileWriter.

        Args:
            source_dir_to_walk: The source directory to traverse.
            target_base_dir_for_mirroring: The base directory in the target where the
                                           mirrored structure will be created.
            transform_func: A function that takes (source_file_path, target_file_path)
                            and returns a boolean indicating success of transformation.

        Returns:
            A dictionary summarizing the operation:
            {'success_count': int, 'failure_count': int, 'failures': list[str]}
        """
        abs_source_dir_to_walk = os.path.abspath(source_dir_to_walk)
        abs_target_base_dir = os.path.abspath(target_base_dir_for_mirroring)

        if not os.path.isdir(abs_source_dir_to_walk):
            logger.error(f"Source directory for mirroring does not exist or is not a directory: {abs_source_dir_to_walk}")
            return {'success_count': 0, 'failure_count': 0, 'failures': [f"Source directory not found: {abs_source_dir_to_walk}"]}

        self.ensure_directory(abs_target_base_dir) # Ensure base target exists

        summary = {'success_count': 0, 'failure_count': 0, 'failures': []}

        for root, _, files in os.walk(abs_source_dir_to_walk):
            # Calculate path relative to the directory being walked to mirror structure correctly
            rel_subdir_path = os.path.relpath(root, abs_source_dir_to_walk)
            
            current_target_dir = os.path.join(abs_target_base_dir, rel_subdir_path)
            if rel_subdir_path == '.': # Avoids adding '.' to the path
                current_target_dir = abs_target_base_dir
            
            self.ensure_directory(current_target_dir)

            for file_name in files:
                source_file_path = os.path.join(root, file_name)
                # Target file name might change extension, transform_func handles this.
                # For now, construct a potential target path with same filename for structure.
                # The transform_func will ultimately decide the final target_file name (e.g. .pdf -> .md)
                # The `resolve_target_path` method is better for individual file target pathing.
                # Here, we pass a structurally mirrored path to transform_func.
                # The transform_func (like ExtractionOrchestrator.transform_pdf_to_markdown)
                # will internally use resolve_target_path or similar logic for the final name.
                
                # Let transform_func determine the exact target file name based on source.
                # We provide the target *directory* for the file.
                # The `target_file_path_for_transform_func` is what the transform_func will use
                # to place its output.
                target_file_path_for_transform_func = os.path.join(current_target_dir, file_name)


                try:
                    # The transform_func is expected to handle the .pdf -> .md change
                    # and place the file correctly within current_target_dir
                    if transform_func(source_file_path, target_file_path_for_transform_func):
                        summary['success_count'] += 1
                    else:
                        summary['failure_count'] += 1
                        summary['failures'].append(source_file_path) # Log source if transform reported False
                except Exception as e: # pragma: no cover
                    logger.error(f"Error transforming file {source_file_path}: {e}", exc_info=True)
                    summary['failure_count'] += 1
                    summary['failures'].append(f"{source_file_path} (Exception: {str(e)})")
        
        logger.info(
            f"Directory mirroring complete for {abs_source_dir_to_walk} to {abs_target_base_dir}. "
            f"Success: {summary['success_count']}, Failures: {summary['failure_count']}."
        )
        return summary