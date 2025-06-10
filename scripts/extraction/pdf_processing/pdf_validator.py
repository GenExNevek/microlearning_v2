# scripts/extraction/pdf_processing/pdf_validator.py

"""Module for PDF validation and system dependency checks."""

import os
import logging
import sys
from typing import Tuple, Optional

import fitz # PyMuPDF

from ...config import settings # For path configurations if needed

logger = logging.getLogger(__name__)

# Gemini API constraints (from "Document understanding.md" and general knowledge)
GEMINI_MAX_PAGES_PRO_FLASH = 3600  # For Gemini 1.5 Pro and 1.5 Flash
GEMINI_DIRECT_UPLOAD_LIMIT_MB = 20 # Total request size
GEMINI_FILE_API_LIMIT_MB = 50    # Per file for File API

class PDFValidator:
    """Validates PDF files and system dependencies for the extraction pipeline."""

    def validate_system_dependencies(self) -> bool:
        """Validate that critical system dependencies are properly installed."""
        deps_ok = True
        try:
            import fitz # PyMuPDF
            logger.debug(f"PyMuPDF (fitz) version {fitz.__doc__} is installed.")
        except ImportError:
            logger.error("CRITICAL: PyMuPDF (fitz) is NOT installed. Please run `pip install PyMuPDF`.")
            deps_ok = False
        
        try:
            from PIL import Image, ImageDraw, ImageFont
            logger.debug(f"Pillow (PIL) version {Image.__version__} is installed.")
        except ImportError:
            logger.error("CRITICAL: Pillow (PIL) is NOT installed. Please run `pip install Pillow`.")
            deps_ok = False
        
        try:
            import google.generativeai
            logger.debug(f"Google Generative AI (google-generativeai) version {google.generativeai.__version__} is installed.")
        except ImportError:
            logger.error("CRITICAL: Google Generative AI (google-generativeai) is NOT installed. Please run `pip install google-generativeai`.")
            deps_ok = False
        
        try:
            import yaml
            logger.debug("PyYAML is installed.") # Version check can be added if needed
        except ImportError:
            logger.warning("PyYAML is NOT installed. `pip install PyYAML` (recommended for frontmatter parsing if LLM provides it).")
            # Not strictly critical for core if LLM doesn't use YAML frontmatter, but good to have.
        
        try:
            import tenacity
            logger.debug("Tenacity is installed.") # Version check can be added if needed
        except ImportError:
            logger.warning("Tenacity is NOT installed. `pip install tenacity` (recommended for robust API calls).")

        if deps_ok:
            logger.info("Core system dependencies verified.")
        else:
            logger.error("One or more critical system dependencies are missing. Please install them.")
        return deps_ok

    def validate_pdf_file(self, pdf_path: str) -> Tuple[bool, str]:
        """
        Validate a single PDF file for basic readability and Gemini compatibility.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            A tuple (is_valid: bool, message: str).
        """
        if not os.path.exists(pdf_path):
            return False, f"PDF file does not exist: {pdf_path}"
        if not os.path.isfile(pdf_path):
            return False, f"Path is not a file: {pdf_path}"
        if not pdf_path.lower().endswith('.pdf'):
            return False, f"File is not a PDF (by extension): {pdf_path}"

        try:
            file_size_bytes = os.path.getsize(pdf_path)
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Check against absolute max for File API
            if file_size_mb > GEMINI_FILE_API_LIMIT_MB:
                return False, (f"PDF size ({file_size_mb:.2f}MB) exceeds Gemini File API limit "
                               f"of {GEMINI_FILE_API_LIMIT_MB}MB: {pdf_path}")

            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            doc.close()

            if num_pages == 0:
                return False, f"PDF is empty (0 pages): {pdf_path}"
            if num_pages > GEMINI_MAX_PAGES_PRO_FLASH: # Assuming usage of Pro/Flash
                return False, (f"PDF has {num_pages} pages, exceeding Gemini limit "
                               f"of {GEMINI_MAX_PAGES_PRO_FLASH} pages: {pdf_path}")
            
            logger.debug(f"PDF validated: {pdf_path}, Pages: {num_pages}, Size: {file_size_mb:.2f}MB")
            return True, f"PDF is valid. Pages: {num_pages}, Size: {file_size_mb:.2f}MB."

        except fitz.FitzError as e: # Generic PyMuPDF error
            return False, f"PDF is corrupted or unreadable by PyMuPDF: {pdf_path}. Error: {e}"
        except Exception as e:
            return False, f"Unexpected error validating PDF {pdf_path}: {e}"

    def check_path_permissions(self, path: str, mode: str = 'read') -> Tuple[bool, str]:
        """
        Check read/write permissions for a given path.

        Args:
            path: The file or directory path to check.
            mode: 'read' or 'write'. For directories, 'write' checks if files can be created.

        Returns:
            A tuple (has_permission: bool, message: str).
        """
        if not os.path.exists(path):
            return False, f"Path does not exist: {path}"

        if mode == 'read':
            if os.access(path, os.R_OK):
                return True, f"Read permission granted for: {path}"
            else:
                return False, f"No read permission for: {path}"
        elif mode == 'write':
            if os.path.isdir(path): # Check if we can write a test file in a directory
                # For a directory, os.W_OK checks if you can create files in it.
                if os.access(path, os.W_OK):
                    return True, f"Write permission (to create files) granted for directory: {path}"
                else:
                    return False, f"No write permission (to create files) for directory: {path}"
            else: # For a file
                if os.access(path, os.W_OK):
                    return True, f"Write permission granted for file: {path}"
                else:
                    return False, f"No write permission for file: {path}"
        else:
            return False, f"Invalid permission mode: {mode}. Use 'read' or 'write'."

    def validate_source_directory(self, dir_path: str) -> Tuple[bool, str]:
        """Validates the PDF source directory."""
        if not os.path.exists(dir_path):
            return False, f"Source directory does not exist: {dir_path}"
        if not os.path.isdir(dir_path):
            return False, f"Source path is not a directory: {dir_path}"
        
        perm_ok, msg = self.check_path_permissions(dir_path, 'read')
        if not perm_ok:
            return False, msg
        
        return True, f"Source directory '{dir_path}' is valid and readable."

    def validate_target_directory(self, dir_path: str, create_if_not_exists: bool = True) -> Tuple[bool, str]:
        """Validates the Markdown target directory."""
        if os.path.exists(dir_path):
            if not os.path.isdir(dir_path):
                return False, f"Target path exists but is not a directory: {dir_path}"
            perm_ok, msg = self.check_path_permissions(dir_path, 'write')
            if not perm_ok:
                return False, msg
            return True, f"Target directory '{dir_path}' is valid and writable."
        elif create_if_not_exists:
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"Target directory created: {dir_path}")
                perm_ok, msg = self.check_path_permissions(dir_path, 'write') # Check after creation
                if not perm_ok: # Should ideally not happen if makedirs succeeded
                    return False, f"Target directory created but no write permission: {dir_path}. {msg}"
                return True, f"Target directory created and is writable: {dir_path}"
            except Exception as e:
                return False, f"Failed to create target directory {dir_path}: {e}"
        else:
            return False, f"Target directory does not exist and creation is disabled: {dir_path}"