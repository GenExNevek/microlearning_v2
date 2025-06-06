# scripts/extraction/markdown_processing/__init__.py

"""
Markdown Processing Package.

This package contains modules for processing and formatting markdown content
extracted from PDFs.
"""

# Import the main MarkdownFormatter class to make it available at the package level
# This is the new, refactored MarkdownFormatter.
from .markdown_formatter import MarkdownFormatter

__all__ = ['MarkdownFormatter']