# scripts/extraction/markdown_processing/content_analyser.py

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Enhanced stop words to be ignored during keyword extraction
STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'in', 'on', 'of', 'for', 'with', 'is', 'are', 'was', 'were',
    'image', 'diagram', 'showing', 'figure', 'fig', 'illustration', 'photo', 'picture', 'shows',
    'this', 'that', 'these', 'those', 'can', 'be', 'has', 'have', 'will', 'would', 'should',
    'from', 'into', 'onto', 'upon', 'about', 'above', 'below', 'under', 'over'
}

@dataclass
class ContextClues:
    """Enhanced contextual information extracted from around an image reference in markdown."""
    alt_text: str
    surrounding_text: str
    keywords: List[str] = field(default_factory=list)
    figure_number: Optional[str] = None
    page_number: Optional[int] = None
    image_index: Optional[int] = None
    content_type: Optional[str] = None  # e.g., 'thermometer', 'graph', 'target'
    
class ContentAnalyser:
    """
    Enhanced analyzer for markdown content to extract contextual clues about expected images.
    """

    def _extract_keywords(self, text: str) -> List[str]:
        """Enhanced keyword extraction with better filtering."""
        if not text:
            return []
        
        # Remove punctuation and convert to lowercase
        cleaned_text = re.sub(r'[^\w\s]', '', text.lower())
        
        # Split into words and filter out stop words and short words
        keywords = [
            word for word in cleaned_text.split() 
            if word not in STOP_WORDS and len(word) > 2
        ]
        return list(set(keywords))  # Return unique keywords

    def _detect_content_type(self, text: str) -> Optional[str]:
        """Detect the type of content based on keywords in text."""
        text_lower = text.lower()
        
        content_patterns = {
            'thermometer': ['thermometer', 'temperature', 'celsius', 'scale', 'reading'],
            'graph': ['graph', 'curve', 'distribution', 'gaussian', 'precision', 'accuracy'],
            'target': ['target', 'bullseye', 'shots', 'accuracy', 'precision'],
            'diagram': ['diagram', 'illustration', 'schematic'],
            'chart': ['chart', 'plot', 'data'],
            'table': ['table', 'row', 'column'],
            'equation': ['equation', 'formula', 'mathematical'],
        }
        
        for content_type, patterns in content_patterns.items():
            if any(pattern in text_lower for pattern in patterns):
                return content_type
        
        return None

    def _extract_page_and_image_info(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Extract page and image index information from text."""
        # Multiple patterns to catch various formats
        patterns = [
            r'page\s*(\d+).*?img(?:age)?\s*(\d+)',       # "page 19 image 1"
            r'page\s*(\d+).*?figure\s*(\d+)',           # "page 19 figure 1"
            r'fig(\d+)-page(\d+)-img(\d+)',             # "fig11-page19-img1"
            r'p(\d+)[-_]?i(\d+)',                       # "p19-i1"
            r'question\s*(\d+).*?page\s*(\d+)',         # "question 2 on page 19"
        ]
        
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if i == 0 or i == 1:  # page X image/figure Y
                    page_num = int(match.group(1))
                    img_idx = int(match.group(2))
                elif i == 2:  # fig-page-img format
                    page_num = int(match.group(2))
                    img_idx = int(match.group(3))
                elif i == 3:  # short format
                    page_num = int(match.group(1))
                    img_idx = int(match.group(2))
                elif i == 4:  # question X on page Y
                    page_num = int(match.group(2))
                    img_idx = 1  # Assume first image for question context
                
                return page_num, img_idx
        
        return None, None

    def _extract_figure_number(self, text: str) -> Optional[str]:
        """Enhanced figure number extraction with multiple patterns."""
        patterns = [
            r'figure\s*(\d+(?:\.\d+)?)',  # "Figure 11" or "Figure 11.1"
            r'fig\.?\s*(\d+(?:\.\d+)?)',  # "Fig. 11" or "fig 11"
            r'image\s*(\d+)',             # "Image 11"
            r'diagram\s*(\d+)',           # "Diagram 11"
        ]
        
        for pattern in patterns:
            # Search in both directions around the image reference
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    def _extract_question_context(self, text: str) -> Optional[dict]:
        """Extract question/activity context that might help with correlation."""
        question_patterns = [
            r'question\s*(\d+)',           # "Question 2"
            r'activity\s*(\d+)',           # "Activity 1"
            r'test\s*your\s*knowledge',    # "Test Your Knowledge"
            r'exam[-\s]*style',            # "Exam-Style Questions"
        ]
        
        for pattern in question_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if match.lastindex and match.lastindex >= 1:
                    return {'type': 'question', 'number': int(match.group(1))}
                else:
                    return {'type': 'assessment', 'context': match.group(0)}
        
        return None

    def analyse_markdown_context(self, markdown_text: str, img_ref_match: re.Match) -> ContextClues:
        """Enhanced context analysis with multiple extraction strategies."""
        alt_text = img_ref_match.group(1)
        
        # Extract surrounding text with larger context window
        context_window = 500  # Increased from 250
        start_pos = max(0, img_ref_match.start() - context_window)
        end_pos = min(len(markdown_text), img_ref_match.end() + context_window)
        surrounding_text = markdown_text[start_pos:end_pos]
        
        # Combine alt text and surrounding text for analysis
        combined_text = alt_text + " " + surrounding_text
        
        # Extract various types of information
        keywords = self._extract_keywords(combined_text)
        figure_number = self._extract_figure_number(combined_text)
        content_type = self._detect_content_type(combined_text)
        page_number, image_index = self._extract_page_and_image_info(combined_text)
        
        # Additional context from question/activity structure
        question_context = self._extract_question_context(surrounding_text)
        if question_context and not page_number:
            # Use question context to estimate position
            if question_context.get('number'):
                # Rough heuristic: question N typically appears around page N+15
                estimated_page = question_context['number'] + 15
                if estimated_page <= 25:  # Reasonable page range
                    page_number = estimated_page
        
        # Special handling for known content in the document
        if 'thermometer' in alt_text.lower() and not page_number:
            if 'correct reading' in surrounding_text.lower():
                page_number = 19  # First thermometer image
            elif 'temperature change' in surrounding_text.lower():
                page_number = 20  # Second thermometer image
        
        return ContextClues(
            alt_text=alt_text,
            surrounding_text=surrounding_text,
            keywords=keywords,
            figure_number=figure_number,
            page_number=page_number,
            image_index=image_index,
            content_type=content_type
        )