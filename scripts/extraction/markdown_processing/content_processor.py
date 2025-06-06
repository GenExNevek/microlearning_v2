# scripts/extraction/markdown_processing/content_processor.py

"""Module for processing raw Gemini content into clean markdown, including frontmatter."""

import re
import yaml
import logging
from typing import Dict, Any, Tuple

from .frontmatter_generator import FrontmatterGenerator # Sibling import

logger = logging.getLogger(__name__)

class ContentProcessor:
    """Processes raw LLM content, handles frontmatter, and cleans the main body."""

    def __init__(self, frontmatter_generator: FrontmatterGenerator):
        self.frontmatter_generator = frontmatter_generator
        
        # ***ENHANCED: Expanded pattern to handle various markdown code block variations***
        # Pattern to detect markdown code block: ```markdown|md|Markdown|MARKDOWN ... ``` (case-insensitive, non-greedy content)
        self.markdown_code_block_pattern = r'^\s*```\s*(?:markdown|md)\s*\n(.*?)\n```\s*$'
        
        # ***ENHANCED: More robust frontmatter patterns***
        # Order matters: check for frontmatter inside markdown block first.
        self.frontmatter_patterns = [
            # Frontmatter inside a markdown block: ```markdown\n---\n...\n---\n...```
            # Captures: (1) frontmatter_text, (2) body_after_frontmatter_in_block
            r'^\s*```\s*(?:markdown|md)\s*\n\s*---\s*\n(.*?)\n---\s*\n*(.*?)\n```\s*$',
            # ***ENHANCED: Handle frontmatter with optional trailing newlines before closing ---***
            # Frontmatter at the very start: --- ... ---
            # Captures: (1) frontmatter_text, (2) body_after_frontmatter
            r'^\s*---\s*\n(.*?)\n---\s*\n*(.*)',
            # ***ENHANCED: Handle frontmatter that ends without trailing newline (EOF case)***
            # Frontmatter at start but ending at EOF: --- ... ---$
            r'^\s*---\s*\n(.*?)\n---\s*$'
        ]

    def process_llm_output(self,
                           raw_llm_content: str,
                           base_metadata: Dict[str, Any]
                           ) -> Tuple[str, Dict[str, Any]]:
        """
        Processes raw LLM output.
        1. Extracts and parses frontmatter provided by the LLM.
        2. Cleans the main content body (e.g., removes markdown code block wrappers).
        3. Merges LLM-extracted metadata with base metadata, validating types for specific fields.
        4. Generates the final frontmatter using the merged metadata.
        5. Combines final frontmatter and cleaned body.

        Returns:
            A tuple containing:
            - The fully processed markdown string (final_frontmatter + cleaned_body).
            - The merged metadata dictionary.
        """
        logger.info("Processing LLM output.")

        llm_frontmatter_text = None
        body_content = raw_llm_content.strip() # Start with stripped raw content

        # Try to find and extract frontmatter using defined patterns
        for i, pattern in enumerate(self.frontmatter_patterns):
            match = re.search(pattern, body_content, re.DOTALL | re.IGNORECASE)
            if match:
                llm_frontmatter_text = match.group(1).strip()
                # ***ENHANCED: Handle patterns that may not have a body group (EOF case)***
                try:
                    body_content = match.group(2).strip() if len(match.groups()) >= 2 else ""
                except IndexError:
                    body_content = ""
                logger.debug(f"Found LLM frontmatter using pattern index {i}. Body length: {len(body_content)}")
                break
        
        if not llm_frontmatter_text: 
            # ***ENHANCED: Case-insensitive matching for markdown code blocks***
            markdown_block_match = re.search(self.markdown_code_block_pattern, body_content, re.DOTALL | re.IGNORECASE)
            if markdown_block_match:
                body_content = markdown_block_match.group(1).strip()
                logger.debug("Removed outer ```markdown ... ``` wrapper from body content (no frontmatter was inside).")
            else:
                 logger.debug("No LLM frontmatter found, and no standalone markdown block wrapper. Using content as body.")

        merged_metadata = base_metadata.copy()
        if llm_frontmatter_text:
            try:
                # ***ENHANCED: Better error handling for YAML parsing***
                llm_extracted_metadata = yaml.safe_load(llm_frontmatter_text)
                
                if isinstance(llm_extracted_metadata, dict):
                    logger.info(f"Successfully parsed LLM frontmatter with {len(llm_extracted_metadata)} fields")

                    # ***ENHANCED: More robust field validation and merging***
                    self._merge_metadata_field(llm_extracted_metadata, merged_metadata, 'unit-title', 'unit_title')
                    self._merge_metadata_field(llm_extracted_metadata, merged_metadata, 'subject', 'subject')
                    
                    # ***ENHANCED: Handle additional common LLM fields***
                    self._merge_metadata_field(llm_extracted_metadata, merged_metadata, 'title', 'unit_title')  # Alternative field name
                    self._merge_metadata_field(llm_extracted_metadata, merged_metadata, 'course', 'subject')     # Alternative field name
                    
                elif llm_extracted_metadata is None:
                    logger.warning("LLM frontmatter parsed as None (empty YAML). Using base metadata only.")
                else:
                    logger.warning(f"LLM frontmatter did not parse into a dictionary: {type(llm_extracted_metadata)}. Content: '{llm_frontmatter_text[:100]}...'")
                    
            except yaml.YAMLError as e:
                logger.error(f"Error parsing LLM frontmatter as YAML: {e}")
                logger.debug(f"Problematic YAML content: '{llm_frontmatter_text}'")
                # ***ENHANCED: Attempt to extract key fields even from malformed YAML***
                self._extract_fallback_metadata(llm_frontmatter_text, merged_metadata)
            except Exception as e:
                logger.error(f"Unexpected error processing LLM frontmatter: {e}")
                logger.debug(f"Frontmatter content: '{llm_frontmatter_text}'")
        else:
            logger.info("No frontmatter found in LLM response to parse.")

        final_frontmatter_str = self.frontmatter_generator.generate_frontmatter(merged_metadata)
        
        separator = "\n\n" if body_content else ""
        full_processed_content = f"{final_frontmatter_str}{separator}{body_content}"
        
        logger.info("Finished processing LLM output.")
        return full_processed_content, merged_metadata

    def _merge_metadata_field(self, 
                             llm_metadata: Dict[str, Any], 
                             merged_metadata: Dict[str, Any], 
                             llm_key: str, 
                             merged_key: str) -> None:
        """
        ***ENHANCED: Robust field merging with validation***
        Safely merge a field from LLM metadata to merged metadata with type validation.
        """
        llm_value = llm_metadata.get(llm_key)
        if llm_value is not None:
            if isinstance(llm_value, str) and llm_value.strip():
                merged_metadata[merged_key] = llm_value.strip()
                logger.debug(f"Updated '{merged_key}' from LLM '{llm_key}': \"{merged_metadata[merged_key]}\"")
            elif not isinstance(llm_value, str):
                logger.warning(f"LLM '{llm_key}' (value: '{llm_value}') is not a string ({type(llm_value)}). Using base/default: \"{merged_metadata.get(merged_key)}\"")
            else:
                logger.warning(f"LLM '{llm_key}' is empty string. Using base/default: \"{merged_metadata.get(merged_key)}\"")

    def _extract_fallback_metadata(self, 
                                  malformed_yaml: str, 
                                  merged_metadata: Dict[str, Any]) -> None:
        """
        ***ENHANCED: Fallback extraction for malformed YAML***
        Attempt to extract key metadata fields even from malformed YAML using regex.
        """
        logger.info("Attempting fallback metadata extraction from malformed YAML")
        
        # Common patterns for key fields
        fallback_patterns = {
            'unit_title': [
                r'unit-title\s*:\s*["\']?(.*?)["\']?\s*(?:\n|$)',
                r'title\s*:\s*["\']?(.*?)["\']?\s*(?:\n|$)',
                r'unit_title\s*:\s*["\']?(.*?)["\']?\s*(?:\n|$)'
            ],
            'subject': [
                r'subject\s*:\s*["\']?(.*?)["\']?\s*(?:\n|$)',
                r'course\s*:\s*["\']?(.*?)["\']?\s*(?:\n|$)'
            ]
        }
        
        for field_key, patterns in fallback_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, malformed_yaml, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value and value not in ['""', "''"]:  # Avoid empty quoted strings
                        merged_metadata[field_key] = value
                        logger.info(f"Extracted '{field_key}' via fallback: \"{value}\"")
                        break