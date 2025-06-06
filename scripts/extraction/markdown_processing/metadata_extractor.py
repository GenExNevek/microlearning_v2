# scripts/extraction/markdown_processing/metadata_extractor.py

"""Module for extracting metadata from PDF file paths."""

import os
import re
from datetime import datetime
from typing import Dict, Any

class MetadataExtractor:
    """Extracts metadata from PDF file path components."""

    def extract_metadata_from_path(self, pdf_path: str) -> Dict[str, Any]:
        """Extract metadata from PDF path components."""
        path_norm = pdf_path.replace('\\', '/')
        parts = path_norm.split('/')
        filename = os.path.basename(pdf_path)
        filename_without_ext = os.path.splitext(filename)[0]

        course_id_from_path = None
        module_id_from_path = None
        unit_id_from_path = None

        # Extract from path components (reversed, so deepest takes precedence for its type)
        for part in reversed(parts):
            part_name_only = os.path.splitext(part)[0] # In case a path part itself has an extension (unlikely for dirs)

            if not unit_id_from_path and (part_name_only.startswith('UNI') or part_name_only.startswith('unit')):
                # Try to capture the full ID part from the path segment
                m = re.match(r'^((?:UNI|unit)[A-Za-z0-9_-]*).*', part_name_only, re.IGNORECASE)
                if m: unit_id_from_path = m.group(1)
            elif not module_id_from_path and (part_name_only.startswith('MOD') or part_name_only.startswith('module')):
                m = re.match(r'^((?:MOD|module)[A-Za-z0-9_-]*).*', part_name_only, re.IGNORECASE)
                if m: module_id_from_path = m.group(1)
            elif not course_id_from_path and (part_name_only.startswith('CON') or part_name_only.startswith('course')):
                m = re.match(r'^((?:CON|course)[A-Za-z0-9_-]*).*', part_name_only, re.IGNORECASE)
                if m: course_id_from_path = m.group(1)

        # Extract from filename (this will take precedence for unit_id and unit_title_id)
        unit_id_from_filename = None
        unit_title_id_from_filename = filename_without_ext # Default

        # Regex to capture: ((ID_PREFIX)(ID_BODY_ALNUM_ETC)) (SEPARATOR (TITLE_BODY))?
        # Group 1: Full ID (e.g., "UNI-PHY101A", "unit_maths", "UNI123")
        # Group 2: Prefix (UNI or unit)
        # Group 3: Body of ID after prefix
        # Group 4: Optional separator and title (e.g., "_Kinematics")
        # Group 5: Optional title part only (e.g., "Kinematics")
        fn_structure_match = re.match(r'^( ( (?:UNI|unit) [A-Za-z0-9_-]* ) ) (?:[_-](.*))?$', 
                                      filename_without_ext, re.IGNORECASE | re.VERBOSE)
        
        if fn_structure_match:
            unit_id_from_filename = fn_structure_match.group(1) # The full ID part
            if fn_structure_match.group(4): # If there's a title part (group 4 is separator+title, so check group 4 for existence of title)
                                            # The actual title is group 5 in the original regex, but group 4 implies title exists.
                                            # Let's adjust regex slightly for easier group access.
                pass # Will use refined regex below

        # Refined regex for filename to better separate ID and Title
        # ((UNI|unit)[A-Za-z0-9-]*)  -> Group 1: The ID part (e.g. UNI-123, unit_abc)
        # (_|-)?                     -> Group 3: Optional separator
        # (.*)                       -> Group 4: The title part
        fn_match = re.match(r'^((?:UNI|unit)[A-Za-z0-9_-]*?)(?:[_-](.*))?$', filename_without_ext, re.IGNORECASE)
        if fn_match:
            potential_id = fn_match.group(1)
            potential_title = fn_match.group(2)

            if potential_id.lower() == filename_without_ext.lower() or \
               (potential_id.lower() + (("_" if "_" in filename_without_ext else "-") if potential_title else "") + (potential_title or "").lower()) == filename_without_ext.lower():
                # This complex check is to ensure the regex split is meaningful
                # e.g. UNI123 -> id=UNI123, title=None
                # e.g. UNI123_Title -> id=UNI123, title=Title
                unit_id_from_filename = potential_id
                if potential_title:
                    unit_title_id_from_filename = potential_title
                else: # Filename was just the ID
                    unit_title_id_from_filename = potential_id
            # else: # Regex match was not a clean split of ID and title, stick to defaults
            #    pass # unit_title_id_from_filename remains filename_without_ext
        # else: # Filename doesn't start with UNI/unit
        #    pass # unit_title_id_from_filename remains filename_without_ext


        # Determine final IDs, giving filename precedence for unit-related IDs
        final_unit_id = unit_id_from_filename or unit_id_from_path
        final_unit_title_id = unit_title_id_from_filename # Filename is the source for title_id

        # Phase extraction
        phase = None
        path_lower = path_norm.lower() # Use normalized path for phase check
        for phase_option in ['AS', 'A2', 'IGCSE', 'GCSE', 'IB', 'A Level']:
            if phase_option.lower().replace(" ", "") in path_lower.replace(" ", ""):
                phase = phase_option
                break
        
        return {
            'unit_id': final_unit_id or 'UNI0000',
            'unit_title_id': final_unit_title_id, # No default like UNI0000, should always be derived from filename
            'parent_module_id': module_id_from_path or 'MOD0000',
            'parent_course_id': course_id_from_path or 'COU0000',
            'phase': phase or 'Unknown',
            'batch_id': 'BAT0001', 
            'extraction_date': datetime.now().strftime('%Y-%m-%d')
        }