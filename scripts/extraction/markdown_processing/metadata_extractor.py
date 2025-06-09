# scripts/extraction/markdown_processing/metadata_extractor.py

"""Module for extracting metadata from PDF file paths."""

import os
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MetadataExtractor:
    """Extracts metadata from PDF file path components."""

    def extract_metadata_from_path(self, pdf_path: str) -> Dict[str, Any]:
        """Extract metadata from PDF path components."""
        try:
            if pdf_path is None: # Handle None input gracefully
                pdf_path = ""
                
            # Normalise path separators and filter out empty components
            path_normalized = pdf_path.replace('\\', '/')
            parts = [part for part in path_normalized.split('/') if part.strip()]
            filename = os.path.basename(path_normalized) if path_normalized else ""
            filename_without_ext = os.path.splitext(filename)[0] if filename else ""

            course_id = None
            module_id = None
            unit_id = None

            # Extract IDs from path components (reverse order for hierarchy)
            # Only consider last few parts for typical structures like COU/MOD/UNI
            relevant_parts = parts[-4:] # Consider up to 4 levels for C/M/U and filename parent
            for part in reversed(relevant_parts):
                if not part.strip():  # Skip empty parts
                    continue
                    
                if not unit_id and (part.lower().startswith('uni') or part.lower().startswith('unit')):
                    unit_id = self._extract_id_from_component(part)
                elif not module_id and (part.lower().startswith('mod') or part.lower().startswith('module')):
                    module_id = self._extract_id_from_component(part)
                elif not course_id and (part.lower().startswith('cou') or part.lower().startswith('course')):
                    course_id = self._extract_id_from_component(part)

            # Extract unit_id from filename if not found in path or if filename is more specific
            if filename_without_ext:
                if filename_without_ext.lower().startswith('uni') or filename_without_ext.lower().startswith('unit'):
                    filename_unit_id = self._extract_id_from_component(filename_without_ext)
                    if filename_unit_id: # Prioritize filename if it yields a unit ID
                        unit_id = filename_unit_id

            # Extract unit_title_id with improved pattern matching
            unit_title_id = self._extract_unit_title_id(filename_without_ext)

            # Extract phase with correct priority order (longer patterns first)
            phase = self._extract_phase(path_normalized)
            
            default_unit_title_id = filename_without_ext if filename_without_ext else 'unknown_unit'
            
            logger.debug(f"Extracted metadata from '{pdf_path}': unit_id='{unit_id}', unit_title_id='{unit_title_id}', module_id='{module_id}', course_id='{course_id}', phase='{phase}'")
            
            return {
                'unit_id': unit_id or 'UNI0000',
                'unit_title_id': unit_title_id or default_unit_title_id,
                'parent_module_id': module_id or 'MOD0000',
                'parent_course_id': course_id or 'COU0000',
                'phase': phase or 'Unknown',
                'batch_id': 'BAT0001',  # Default, can be overridden
                'extraction_date': datetime.now().strftime('%Y-%m-%d')
            }
            
        except Exception as e: # pragma: no cover
            logger.error(f"Error extracting metadata from path '{pdf_path}': {e}", exc_info=True)
            # Return safe defaults on error
            fn_base = 'unknown_unit'
            if pdf_path and isinstance(pdf_path, str):
                 fn_base = os.path.splitext(os.path.basename(pdf_path))[0]

            return {
                'unit_id': 'UNI0000',
                'unit_title_id': fn_base,
                'parent_module_id': 'MOD0000',
                'parent_course_id': 'COU0000',
                'phase': 'Unknown',
                'batch_id': 'BAT0001',
                'extraction_date': datetime.now().strftime('%Y-%m-%d')
            }

    def _extract_id_from_component(self, component: str) -> str:
        """Extract ID from a path component, handling various delimiter patterns."""
        if not component:
            return "" # pragma: no cover
            
        # Try to match common ID patterns like COU123, MOD-456, unit_789
        # This regex looks for a prefix (uni, mod, cou) followed by numbers, or just the prefix.
        # It then takes that part.
        match = re.match(r'((?:UNI|MOD|COU|UNIT|MODULE|COURSE)[-_]?\d*|UNI\d*|MOD\d*|COU\d*)', component, re.IGNORECASE)
        if match and match.group(1):
            return match.group(1)
        
        # Fallback: Split on common delimiters and take the first part if it looks like an ID prefix
        for delimiter in ['-', '_']:
            if delimiter in component:
                first_part = component.split(delimiter)[0]
                if first_part.lower().startswith(('uni','mod','cou','unit','module','course')):
                    return first_part
        
        # If no clear ID pattern or prefix, but the component itself starts with a known prefix, return it.
        if component.lower().startswith(('uni','mod','cou','unit','module','course')):
            return component

        return "" # Return empty if no suitable ID found

    def _extract_unit_title_id(self, filename_without_ext: str) -> str:
        """Extract unit title ID with improved pattern matching."""
        if not filename_without_ext:
            return 'unknown_title_id'
            
        unit_title_id = filename_without_ext

        # Regex: (?:UNI\d*[-_]+|unit[-_]?\d*[-_]+)
        # - UNI followed by optional digits, then one or more separators (e.g., "UNI123-", "UNI_")
        # - OR unit followed by an optional separator, optional digits, then one or more separators (e.g., "unit-123-", "unit_")
        # Captures the part after this prefix.
        match = re.match(r'(?:UNI\d*[-_]+|unit[-_]?\d*[-_]+)(.*)', unit_title_id, re.IGNORECASE)
        if match and match.group(1):
            unit_title_id = match.group(1)
        else:
            # Fallback for simple "UNI_title" or "unit-title" without numbers in prefix
            # (already somewhat covered by the above, but this is more direct for simple cases)
            simple_match = re.match(r'(?:UNI[-_]+|unit[-_]+)(.*)', unit_title_id, re.IGNORECASE)
            if simple_match and simple_match.group(1):
                unit_title_id = simple_match.group(1)
            # If still no match, it might be that the filename itself is the title_id,
            # e.g., "MyAwesomeUnit.pdf" where "MyAwesomeUnit" is the title_id.
            # In this case, unit_title_id remains filename_without_ext.

        return unit_title_id if unit_title_id else filename_without_ext


    def _extract_phase(self, pdf_path: str) -> Optional[str]:
        """Extract educational phase with correct priority order."""
        if not pdf_path: return None # pragma: no cover
        path_lower = pdf_path.lower()
        
        # Order: longer patterns first to avoid premature matching (e.g., "A Level" before "AS" or "A2")
        # Use word boundaries to avoid matching substrings within words (e.g. "gas" for "as")
        phase_patterns = {
            'A Level': r'\ba level\b',
            'AS Level': r'\bas level\b', # More specific than just AS
            'A2 Level': r'\ba2 level\b', # More specific than just A2
            'IGCSE': r'\bigcse\b',
            'GCSE': r'\bgcse\b',
            'IB': r'\bib\b',
            'AS': r'\bas\b', # General AS
            'A2': r'\ba2\b'  # General A2
        }
        
        # Prioritize longer, more specific phase names first
        # Check for "A Level" before "AS" or "A2" to avoid misclassification
        if re.search(phase_patterns['A Level'], path_lower):
            return 'A Level'
        if re.search(phase_patterns['AS Level'], path_lower): # Check "AS Level" before just "AS"
            return 'AS Level'
        if re.search(phase_patterns['A2 Level'], path_lower): # Check "A2 Level" before just "A2"
            return 'A2 Level'

        # Then check other distinct phases
        for phase_name, pattern in phase_patterns.items():
            if phase_name in ['A Level', 'AS Level', 'A2 Level']: # Already checked
                continue
            if re.search(pattern, path_lower.replace(" ", "")): # Allow for "ALevel" vs "A Level" by removing spaces for match
                 logger.debug(f"Found phase '{phase_name}' in path '{pdf_path}' using pattern '{pattern}'")
                 return phase_name
            elif re.search(pattern, path_lower): # Check with spaces
                 logger.debug(f"Found phase '{phase_name}' in path '{pdf_path}' using pattern '{pattern}'")
                 return phase_name
                
        return None
