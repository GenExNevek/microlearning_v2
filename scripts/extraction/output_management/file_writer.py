# scripts/extraction/output_management/file_writer.py

"""Module for file writing operations."""

import os
import logging
import shutil # For disk space check
from typing import Optional

logger = logging.getLogger(__name__)

class FileWriter:
    """Handles file writing operations, primarily for markdown content."""

    @staticmethod
    def ensure_directory(directory_path: str) -> bool:
        """
        Ensure a directory exists, creating it if necessary.
        Logs errors if creation fails.

        Args:
            directory_path: The path to the directory.

        Returns:
            True if directory exists or was created successfully, False otherwise.
        """
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

    @staticmethod
    def _check_writable(path: str) -> bool:
        """Checks if a path (file or directory) is writable."""
        if os.path.exists(path):
            return os.access(path, os.W_OK)
        # If path doesn't exist, check parent directory's writability
        parent_dir = os.path.dirname(path)
        if not parent_dir: parent_dir = '.' # Handle case where path is just a filename
        return os.access(parent_dir, os.W_OK)

    @staticmethod
    def _check_disk_space(file_path: str, content_size_bytes: int) -> bool:
        """Rudimentary check for available disk space."""
        try:
            # Get disk usage for the partition where the file will be written
            # For a new file, check the parent directory. For an existing file, its path is fine.
            target_dir = os.path.dirname(file_path) if not os.path.exists(file_path) else file_path
            if not target_dir: target_dir = '.'

            total, used, free = shutil.disk_usage(target_dir)
            if free > content_size_bytes * 1.1: # Add a small buffer (10%)
                return True
            else:
                logger.warning(
                    f"Insufficient disk space to write {content_size_bytes / (1024*1024):.2f}MB "
                    f"to {file_path}. Available: {free / (1024*1024):.2f}MB"
                )
                return False
        except Exception as e: # pragma: no cover
            logger.warning(f"Could not check disk space for {file_path}: {e}. Proceeding with caution.")
            return True # Default to true if check fails, to not block unnecessarily

    @staticmethod
    def write_markdown_file(content: str, file_path: str) -> Optional[str]:
        """
        Write markdown content to a file with error handling.

        Args:
            content: The markdown string content to write.
            file_path: The full path to the target markdown file.

        Returns:
            The file_path if successful, None otherwise.
        """
        directory = os.path.dirname(file_path)
        if not FileWriter.ensure_directory(directory):
            # Error already logged by ensure_directory
            return None

        if not FileWriter._check_writable(file_path):
            logger.error(f"No write permission for target file path: {file_path}")
            return None

        content_bytes = content.encode('utf-8')
        if not FileWriter._check_disk_space(file_path, len(content_bytes)):
            # Error already logged by _check_disk_space
            return None

        try:
            # Attempt atomic write by writing to a temporary file then renaming
            temp_file_path = file_path + ".tmp"
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # On Windows, os.replace will fail if destination exists.
            # On POSIX, it's atomic.
            # For cross-platform, remove destination first if it exists.
            if os.path.exists(file_path):
                os.remove(file_path)
            os.rename(temp_file_path, file_path)
            
            logger.info(f"Successfully wrote markdown to: {file_path}")
            return file_path
        except IOError as e:
            logger.error(f"IOError writing markdown file {file_path}: {e}", exc_info=True)
        except OSError as e: # Catches issues from os.rename or os.remove
            logger.error(f"OSError during file operation for {file_path}: {e}", exc_info=True)
        except Exception as e: # pragma: no cover
            logger.error(f"Unexpected error writing markdown file {file_path}: {e}", exc_info=True)
        finally:
            # Clean up temp file if it still exists (e.g., rename failed)
            if os.path.exists(temp_file_path): # type: ignore
                try:
                    os.remove(temp_file_path) # type: ignore
                except Exception as e_clean: # pragma: no cover
                    logger.error(f"Failed to clean up temporary file {temp_file_path}: {e_clean}")
        return None

    @staticmethod
    def create_image_assets_folder(markdown_file_path: str, image_assets_suffix: str) -> Optional[str]:
        """
        Create an image assets folder corresponding to a markdown file.
        Example: for 'lesson.md', creates 'lesson-img-assets/'.

        Args:
            markdown_file_path: Path to the markdown file.
            image_assets_suffix: Suffix for the image assets folder (e.g., "-img-assets").

        Returns:
            The path to the created image assets folder if successful, None otherwise.
        """
        directory = os.path.dirname(markdown_file_path)
        filename = os.path.basename(markdown_file_path)
        filename_without_ext = os.path.splitext(filename)[0]

        img_assets_folder_name = f"{filename_without_ext}{image_assets_suffix}"
        img_assets_full_path = os.path.join(directory, img_assets_folder_name)

        if FileWriter.ensure_directory(img_assets_full_path):
            logger.debug(f"Image assets folder ensured: {img_assets_full_path}")
            return img_assets_full_path
        else:
            # Error already logged by ensure_directory
            return None

    # mirror_directory_structure will be moved to DirectoryManager