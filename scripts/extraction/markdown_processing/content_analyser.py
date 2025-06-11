import re
from dataclasses import dataclass, field
from typing import List, Optional

# A basic list of "stop words" to be ignored during keyword extraction.
STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'in', 'on', 'of', 'for', 'with', 'is', 'are', 'was', 'were',
    'image', 'of', 'a', 'diagram', 'showing', 'figure', 'fig', 'illustration', 'photo', 'picture'
}

@dataclass
class ContextClues:
    """Holds contextual information extracted from around an image reference in markdown."""
    alt_text: str
    surrounding_text: str
    keywords: List[str] = field(default_factory=list)
    figure_number: Optional[str] = None
    
class ContentAnalyser:
    """
    Analyzes markdown content to extract contextual clues about expected images.
    """

    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extracts and cleans a list of keywords from a given text string.
        """
        if not text:
            return []
        
        # Remove punctuation and convert to lowercase
        cleaned_text = re.sub(r'[^\w\s]', '', text.lower())
        
        # Split into words and filter out stop words and short words
        keywords = [
            word for word in cleaned_text.split() 
            if word not in STOP_WORDS and len(word) > 2
        ]
        return list(set(keywords)) # Return unique keywords

    def analyse_markdown_context(self, markdown_text: str, img_ref_match: re.Match) -> ContextClues:
        """
        Extracts contextual clues from the markdown text surrounding an image reference.

        Args:
            markdown_text: The full markdown content string.
            img_ref_match: A regex match object for an image tag `!\[(.*?)\]\((.*?)\)`.

        Returns:
            A ContextClues object populated with the findings.
        """
        alt_text = img_ref_match.group(1)
        
        # Extract surrounding text (e.g., 250 characters before and after the match)
        start_pos = max(0, img_ref_match.start() - 250)
        end_pos = min(len(markdown_text), img_ref_match.end() + 250)
        surrounding_text = markdown_text[start_pos:end_pos]
        
        # Combine alt text and surrounding text for a richer keyword set
        combined_text_for_keywords = alt_text + " " + surrounding_text
        keywords = self._extract_keywords(combined_text_for_keywords)
        
        # Simple pattern matching for figure numbers in the surrounding text
        figure_match = re.search(r'(figure|fig)\.?\s*([\d\.]+)', surrounding_text, re.IGNORECASE)
        figure_number = figure_match.group(2) if figure_match else None
        
        return ContextClues(
            alt_text=alt_text,
            surrounding_text=surrounding_text,
            keywords=keywords,
            figure_number=figure_number
        )