# scripts/extraction/output_management/__init__.py

"""
Package for output management, including file writing and directory structuring.

This package includes:
- FileWriter: For writing content to files, especially markdown.
- DirectoryManager: For managing directory structures, mirroring, and path resolution.
"""

from .file_writer import FileWriter
from .directory_manager import DirectoryManager

__all__ = [
    'FileWriter',
    'DirectoryManager'
]