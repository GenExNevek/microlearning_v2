
# scripts/extraction/markdown_processing/section_marker_processor.py

"""Module for validating and injecting required section markers in markdown."""

import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class SectionMarkerProcessor:
    """Validates and injects required HTML comment section markers."""

    DEFAULT_REQUIRED_SECTIONS: List[str] = [
        'INTRODUCTION',
        'LEARNING-OBJECTIVES',
        'MAIN-CONTENT-AREA',
        'KEY-TAKEAWAYS'
    ]

    # Sections that typically have a heading associated with them if added
    SECTIONS_WITH_DEFAULT_HEADINGS: Dict[str, str] = {
        'INTRODUCTION': "## Introduction",
        'LEARNING-OBJECTIVES': "## Learning Objectives",
        'KEY-TAKEAWAYS': "## Key Takeaways",
        # 'KNOWLEDGE-CHECK': "## Knowledge Check", # Add if made default required
        # 'REFERENCES': "## References" # Add if made default required
    }

    def __init__(self, required_sections: Optional[List[str]] = None):
        self.required_sections = required_sections if required_sections is not None else self.DEFAULT_REQUIRED_SECTIONS
        logger.debug(f"SectionMarkerProcessor initialised with required sections: {self.required_sections}")

    def process_sections(self, content: str) -> str:
        """
        Ensures all required section markers are present in the content.
        Adds missing markers and standardises spacing around them.
        """
        logger.info("Processing section markers.")
        processed_content = content

        for section_name in self.required_sections:
            section_marker = f"<!-- SECTION: {section_name} -->"
            
            # Check if marker exists (case-insensitive for robustness)
            if not re.search(re.escape(section_marker), processed_content, re.IGNORECASE):
                logger.warning(f"Missing section marker for: {section_name}. Adding it.")
                
                if section_name == 'MAIN-CONTENT-AREA':
                    h2_match = re.search(r'^(##\s+.+)', processed_content, re.MULTILINE)
                    if h2_match:
                        insert_pos = h2_match.start()
                        processed_content = (
                            processed_content[:insert_pos] +
                            f"\n\n{section_marker}\n\n" + # Ensure newlines around marker
                            processed_content[insert_pos:]
                        )
                        logger.debug(f"Inserted {section_marker} before first H2 heading.")
                    else:
                        # If no H2, append MAIN-CONTENT-AREA marker. It might be an empty doc or only H1s.
                        processed_content += f"\n\n{section_marker}\n\n"
                        logger.debug(f"Appended {section_marker} as no H2 heading was found for placement.")
                else:
                    # For other sections, append them with a default heading if applicable
                    section_heading_text = self.SECTIONS_WITH_DEFAULT_HEADINGS.get(section_name)
                    if section_heading_text:
                        processed_content += f"\n\n{section_marker}\n\n{section_heading_text}\n\n"
                    else: # If no default heading, just add the marker
                        processed_content += f"\n\n{section_marker}\n\n"
                    logger.debug(f"Appended {section_marker} (and possibly a default heading).")
            else:
                logger.debug(f"Section marker for {section_name} already present.")

        # ***ENHANCED: Improved spacing standardisation using match object methods***
        # Standardise spacing around all section markers (existing or newly added)
        # Ensure two newlines before and after each marker.
        def replace_marker_spacing(match_obj):
            """
            ***FIXED: Use efficient match_obj.start()/end() instead of find()***
            Efficiently determine proper spacing using match object position information.
            """
            marker_text = match_obj.group(2) # The marker itself e.g. <!-- SECTION: ... -->
            # Original surrounding whitespace: group(1) is before, group(3) is after
            
            marker_start_pos = match_obj.start(2) # Start of the marker itself
            marker_end_pos = match_obj.end(2)     # End of the marker itself
            content_length = len(match_obj.string)
            
            # Determine if we're at the very start or end of content based on the marker's position
            # This needs to consider the original match boundaries (including whitespace)
            # to correctly assess if the marker is truly at the start/end of the *entire content string*.
            
            # A simpler approach: check character before marker_start_pos and after marker_end_pos
            # within the full string.
            
            pre_newlines = "\n\n"
            post_newlines = "\n\n"

            # Check if marker is at the very beginning of the string
            # We look at match_obj.start(0) which is the start of the whole match (including leading whitespace)
            if match_obj.start(0) == 0:
                pre_newlines = ""
            
            # Check if marker is at the very end of the string
            # We look at match_obj.end(0) which is the end of the whole match (including trailing whitespace)
            if match_obj.end(0) == content_length:
                post_newlines = "\n" # Typically one newline at EOF is fine, or "" if it's the only content.
                                     # Let's aim for consistency: if it's the only thing, no newlines.
                                     # If it's at end but not start, then \n\n before, and nothing after.
                                     # The strip() later will handle final EOF newlines.
                if pre_newlines == "": # Only content is the marker
                    post_newlines = ""
                else:
                    post_newlines = "" # Marker is at end, but not start.

            return f"{pre_newlines}{marker_text}{post_newlines}"


        # Apply spacing normalisation to all section markers
        # This regex captures:
        # group(1): optional whitespace before the marker
        # group(2): the marker itself
        # group(3): optional whitespace after the marker
        processed_content = re.sub(r'(\s*)(<!-- SECTION: .*? -->)(\s*)',
                                   replace_marker_spacing,
                                   processed_content, flags=re.DOTALL)
        
        # ***ENHANCED: More sophisticated cleanup***
        # Clean up excessive newlines that might result from additions/substitutions
        # Allow up to triple newlines for intentional spacing, but remove more than that
        processed_content = re.sub(r'\n{4,}', '\n\n\n', processed_content)
        
        # Strip leading/trailing whitespace, but ensure a single trailing newline if content exists
        processed_content = processed_content.strip()
        if processed_content:
            processed_content += '\n'
        
        logger.info("Finished processing section markers.")
        return processed_content