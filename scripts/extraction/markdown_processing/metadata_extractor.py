# scripts/extraction/markdown_processing/metadata_extractor.py

"""Module for extracting metadata from PDF file paths."""

import os
import re
from datetime import datetime
from typing import Dict, Any

# from ...config import settings # Not directly used by current logic but could be for future defaults

class MetadataExtractor:
    """Extracts metadata from PDF file path components."""

    def extract_metadata_from_path(self, pdf_path: str) -> Dict[str, Any]:
        """Extract metadata from PDF path components."""
        path = pdf_path.replace('\\', '/')
        parts = path.split('/')
        filename = os.path.basename(pdf_path)
        filename_without_ext = os.path.splitext(filename)[0]

        course_id = None
        module_id = None
        unit_id = None

        for part in reversed(parts):
            if not unit_id and (part.startswith('UNI') or part.startswith('unit')):
                unit_id = part.split('-')[0] if '-' in part else part.split('_')[0]
            elif not module_id and (part.startswith('MOD') or part.startswith('module')):
                module_id = part.split('-')[0] if '-' in part else part.split('_')[0]
            elif not course_id and (part.startswith('CON') or part.startswith('course')):
                course_id = part.split('-')[0] if '-' in part else part.split('_')[0]

        if not unit_id and (filename_without_ext.startswith('UNI') or filename_without_ext.startswith('unit')):
            unit_id = filename_without_ext.split('-')[0] if '-' in filename_without_ext else filename_without_ext.split('_')[0]

        unit_title_id = filename_without_ext
        # Try to extract a cleaner title_id if a prefix exists
        if unit_title_id.startswith('UNI') or unit_title_id.startswith('unit_'):
            # Regex to capture content after "UNI<digits>-" or "unit_<digits>_" or "UNI-" or "unit_"
            match = re.match(r'(?:UNI|unit_)\d*[-_]*(.*)', unit_title_id, re.IGNORECASE)
            if match and match.group(1): # If there's content after the prefix pattern
                unit_title_id = match.group(1)
            # Fallback if regex doesn't find a clear title part (e.g. "unit_onlyprefix" -> "onlyprefix")
            # This was the original logic: else: unit_title_id = '_'.join(unit_title_id.split('_')[1:]) if '_' in unit_title_id else unit_title_id
            # The regex above should be more comprehensive. If it doesn't match, filename_without_ext is a safe default.

        phase = None
        path_lower = pdf_path.lower()
        for phase_option in ['AS', 'A2', 'IGCSE', 'GCSE', 'IB', 'A Level']: # Order might matter for sub-strings
            if phase_option.lower().replace(" ", "") in path_lower.replace(" ", ""):
                phase = phase_option
                break
        
        return {
            'unit_id': unit_id or 'UNI0000',
            'unit_title_id': unit_title_id or os.path.splitext(filename)[0], # Fallback
            'parent_module_id': module_id or 'MOD0000',
            'parent_course_id': course_id or 'COU0000',
            'phase': phase or 'Unknown',
            'batch_id': 'BAT0001', # Default, can be overridden
            'extraction_date': datetime.now().strftime('%Y-%m-%d')
        }