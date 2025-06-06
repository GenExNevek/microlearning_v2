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
        # Pattern to detect markdown code block: ```markdown ... ``` (non-greedy content)
        self.markdown_code_block_pattern = r'^\s*```\s*markdown\s*\n(.*?)\n```\s*$'
        
        # Patterns to detect frontmatter (non-greedy content for frontmatter and body)
        # Order matters: check for frontmatter inside markdown block first.
        self.frontmatter_patterns = [
            # Frontmatter inside a markdown block: ```markdown\n---\n...\n---\n...```
            # Captures: (1) frontmatter_text, (2) body_after_frontmatter_in_block
            r'^\s*```\s*markdown\s*\n\s*---\s*\n(.*?)\n---\s*\n*(.*?)\n```\s*$',
            # Frontmatter at the very start: --- ... ---
            # Captures: (1) frontmatter_text, (2) body_after_frontmatter
            r'^\s*---\s*\n(.*?)\n---\s*\n*(.*)'
        ]

    def process_llm_output(self,
                           raw_llm_content: str,
                           base_metadata: Dict[str, Any]
                           ) -> Tuple[str, Dict[str, Any]]:
        """
        Processes raw LLM output.
        1. Extracts and parses frontmatter provided by the LLM.
        2. Cleans the main content body (e.g., removes markdown code block wrappers).
        3. Merges LLM-extracted metadata with base metadata.
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
                body_content = match.group(2).strip() # Content after the frontmatter
                logger.debug(f"Found LLM frontmatter using pattern index {i}. Body is now: '{body_content[:100]}...'")
                break
        
        # If no frontmatter block was found by the combined patterns,
        # body_content is still the original raw_llm_content.
        # We still need to check for and remove an outer ```markdown ... ``` wrapper
        # if it exists and wasn't handled by a frontmatter pattern.
        if not llm_frontmatter_text: # Only if frontmatter wasn't already extracted
            markdown_block_match = re.search(self.markdown_code_block_pattern, body_content, re.DOTALL | re.IGNORECASE)
            if markdown_block_match:
                body_content = markdown_block_match.group(1).strip()
                logger.debug("Removed outer ```markdown ... ``` wrapper from body content (no frontmatter was inside).")
            else:
                 logger.debug("No LLM frontmatter found, and no standalone markdown block wrapper. Using content as body.")

        merged_metadata = base_metadata.copy()
        if llm_frontmatter_text:
            try:
                llm_extracted_metadata = yaml.safe_load(llm_frontmatter_text)
                if isinstance(llm_extracted_metadata, dict):
                    logger.info(f"Successfully parsed LLM frontmatter: {llm_extracted_metadata}")
                    if 'unit-title' in llm_extracted_metadata:
                        merged_metadata['unit_title'] = llm_extracted_metadata['unit-title']
                        logger.debug(f"Updated 'unit_title' from LLM: \"{merged_metadata['unit_title']}\"")
                    if 'subject' in llm_extracted_metadata:
                        merged_metadata['subject'] = llm_extracted_metadata['subject']
                        logger.debug(f"Updated 'subject' from LLM: \"{merged_metadata['subject']}\"")
                else:
                    logger.warning(f"LLM frontmatter did not parse into a dictionary: {type(llm_extracted_metadata)}. Content: '{llm_frontmatter_text}'")
            except yaml.YAMLError as e:
                logger.error(f"Error parsing LLM frontmatter: {e}. LLM frontmatter text: '{llm_frontmatter_text}'")
        else:
            logger.info("No frontmatter found in LLM response to parse.")

        final_frontmatter_str = self.frontmatter_generator.generate_frontmatter(merged_metadata)
        
        # Ensure two newlines between frontmatter and body, but only if body is not empty
        separator = "\n\n" if body_content else ""
        full_processed_content = f"{final_frontmatter_str}{separator}{body_content}"
        
        logger.info("Finished processing LLM output.")
        return full_processed_content, merged_metadata