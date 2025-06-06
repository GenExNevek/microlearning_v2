# scripts/extraction/markdown_processing/metadata_extractor.py

"""Module for extracting metadata from PDF file paths."""

import os
import re
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MetadataExtractor:
    """Extracts metadata from PDF file path components."""

    def extract_metadata_from_path(self, pdf_path: str) -> Dict[str, Any]:
        """Extract metadata from PDF path components."""
        try:
            # Normalise path separators and filter out empty components
            path = pdf_path.replace('\\', '/')
            parts = [part for part in path.split('/') if part.strip()]
            filename = os.path.basename(pdf_path)
            filename_without_ext = os.path.splitext(filename)[0]

            course_id = None
            module_id = None
            unit_id = None

            # Extract IDs from path components (reverse order for hierarchy)
            for part in reversed(parts):
                if not part.strip():  # Skip empty parts
                    continue
                    
                if not unit_id and (part.startswith('UNI') or part.lower().startswith('unit')):
                    unit_id = self._extract_id_from_component(part)
                elif not module_id and (part.startswith('MOD') or part.lower().startswith('module') or part.lower().startswith('mod')):
                    module_id = self._extract_id_from_component(part)
                elif not course_id and (part.startswith('COU') or part.lower().startswith('course') or part.lower().startswith('cou')):
                    course_id = self._extract_id_from_component(part)

            # Extract unit_id from filename if not found in path
            if not unit_id and filename_without_ext:
                if filename_without_ext.startswith('UNI') or filename_without_ext.lower().startswith('unit'):
                    unit_id = self._extract_id_from_component(filename_without_ext)

            # Extract unit_title_id with improved pattern matching
            unit_title_id = self._extract_unit_title_id(filename_without_ext)

            # Extract phase with correct priority order (longer patterns first)
            phase = self._extract_phase(pdf_path)
            
            logger.debug(f"Extracted metadata from '{pdf_path}': unit_id='{unit_id}', unit_title_id='{unit_title_id}', module_id='{module_id}', course_id='{course_id}', phase='{phase}'")
            
            return {
                'unit_id': unit_id or 'UNI0000',
                'unit_title_id': unit_title_id,
                'parent_module_id': module_id or 'MOD0000',
                'parent_course_id': course_id or 'COU0000',
                'phase': phase or 'Unknown',
                'batch_id': 'BAT0001',  # Default, can be overridden
                'extraction_date': datetime.now().strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            logger.error(f"Error extracting metadata from path '{pdf_path}': {e}")
            # Return safe defaults on error
            return {
                'unit_id': 'UNI0000',
                'unit_title_id': os.path.splitext(os.path.basename(pdf_path))[0] if pdf_path else 'unknown_unit',
                'parent_module_id': 'MOD0000',
                'parent_course_id': 'COU0000',
                'phase': 'Unknown',
                'batch_id': 'BAT0001',
                'extraction_date': datetime.now().strftime('%Y-%m-%d')
            }

    def _extract_id_from_component(self, component: str) -> str:
        """Extract ID from a path component, handling various delimiter patterns."""
        if not component:
            return ""
            
        # Split on common delimiters and take the first part as the ID
        for delimiter in ['-', '_']:
            if delimiter in component:
                return component.split(delimiter)[0]
        
        # If no delimiters, return the whole component
        return component

    def _extract_unit_title_id(self, filename_without_ext: str) -> str:
        """Extract unit title ID with improved pattern matching."""
        if not filename_without_ext:
            return 'unknown_title_id'
            
        unit_title_id = filename_without_ext

        # *Improved regex pattern to handle UNI prefix variations*
        # Matches: UNI<digits>_, UNI<digits>-, UNI_, UNI-, unit_<digits>_, unit_, etc.
        match = re.match(r'(?:UNI\d*[-_]+|unit[-_]?\d*[-_]+)(.*)', unit_title_id, re.IGNORECASE)
        if match and match.group(1):  # If there's content after the prefix pattern
            unit_title_id = match.group(1)
        else:
            # *Enhanced fallback logic for underscore-separated patterns*
            if '_' in unit_title_id and (unit_title_id.lower().startswith('uni') or unit_title_id.lower().startswith('unit')):
                parts = unit_title_id.split('_')
                if len(parts) > 1:
                    # Skip the first part (which should be the UNI/unit prefix) and join the rest
                    unit_title_id = '_'.join(parts[1:])

        return unit_title_id or filename_without_ext

    def _extract_phase(self, pdf_path: str) -> str:
        """Extract educational phase with correct priority order."""
        path_lower = pdf_path.lower()
        
        # *Corrected order: longer patterns first to avoid premature matching*
        phase_patterns = ['A Level', 'AS', 'A2', 'IGCSE', 'GCSE', 'IB']
        
        for phase_option in phase_patterns:
            # Remove spaces for comparison to handle variations like "ALevel" vs "A Level"
            if phase_option.lower().replace(" ", "") in path_lower.replace(" ", ""):
                logger.debug(f"Found phase '{phase_option}' in path '{pdf_path}'")
                return phase_option
                
        return None