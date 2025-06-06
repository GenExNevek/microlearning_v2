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
        logger.debug(f"SectionMarkerProcessor initialized with required sections: {self.required_sections}")

    def process_sections(self, content: str) -> str:
        """
        Ensures all required section markers are present in the content.
        Adds missing markers and standardizes spacing around them.
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

        # Standardize spacing around all section markers (existing or newly added)
        # Ensure two newlines before and after each marker.
        # This regex also handles cases where markers might be at the very start/end of content.
        def replace_marker_spacing(match_obj):
            pre_newlines = "\n\n" if match_obj.string.find(match_obj.group(2)) > 0 else ""
            post_newlines = "\n\n" if match_obj.string.find(match_obj.group(2)) + len(match_obj.group(2)) < len(match_obj.string) else "\n" # Single if at very end
            return f"{pre_newlines}{match_obj.group(2)}{post_newlines}"

        processed_content = re.sub(r'(\s*)(<!-- SECTION: .*? -->)(\s*)',
                                   replace_marker_spacing,
                                   processed_content, flags=re.DOTALL)
        
        # Clean up excessive newlines that might result from additions/substitutions
        processed_content = re.sub(r'\n{3,}', '\n\n', processed_content).strip()
        
        logger.info("Finished processing section markers.")
        return processed_content