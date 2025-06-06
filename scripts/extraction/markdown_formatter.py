# scripts/extraction/markdown_formatter.py (Legacy Wrapper)

"""
Module for formatting extracted content as markdown.
This is a backward compatibility wrapper for the refactored MarkdownFormatter.
"""

import logging

# Import the new, refactored MarkdownFormatter from its new location
# The `as NewMarkdownFormatter` is mostly for clarity within this file if needed,
# but the goal is to re-export it as `MarkdownFormatter`.
from .markdown_processing.markdown_formatter import MarkdownFormatter

logger = logging.getLogger(__name__)

# Re-export the new MarkdownFormatter under the old path.
# No need to redefine the class here; just assign the imported one.
# MarkdownFormatter = NewMarkdownFormatter # This line is redundant if imported directly as MarkdownFormatter

__all__ = ['MarkdownFormatter']

logger.info(
    "INFO: 'scripts.extraction.markdown_formatter.MarkdownFormatter' is a wrapper. "
    "The refactored implementation is in 'scripts.extraction.markdown_processing.markdown_formatter'."
)

# Original file imports that are now handled by the new MarkdownFormatter or its components:
# import re
# import os
# import yaml
# from datetime import datetime
# from typing import Dict, Optional, Any
# from ..config.extraction_prompt import get_extraction_prompt
# from ..config import settings
# from .image_extractor import ImageExtractor
# from ..utils.image_validation import ImageIssueType