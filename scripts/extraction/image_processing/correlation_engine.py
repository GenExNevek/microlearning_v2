import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Set

from ...config import settings
from ..markdown_processing.content_analyser import ContextClues
from .image_analyser import AnalysisResult

logger = logging.getLogger(__name__)

@dataclass
class CorrelationMatch:
    """Represents a confident match between a markdown reference and an extracted image."""
    md_ref_index: int
    extracted_img_index: int
    confidence_score: float
    strategy_used: str

class CorrelationEngine:
    """
    Core correlation logic using multiple strategies to match markdown image
    references with extracted image data.
    """
    def __init__(self):
        self.config = settings.CORRELATION_CONFIG
        self.weights = {
            'semantic': self.config.get('SEMANTIC_MATCH_WEIGHT', 0.6),
            'position': self.config.get('POSITION_PROXIMITY_WEIGHT', 0.4),
        }

    def _semantic_score(self, md_clues: ContextClues, img_analysis: AnalysisResult) -> float:
        """Calculates a score based on keyword matches with image content type."""
        score = 0.0
        if not md_clues.keywords:
            return 0.0

        # Simple keyword matching against image content type
        # Example: if markdown keywords include 'graph', 'chart', 'data' and image type is 'diagram'
        diagram_keywords = {'graph', 'chart', 'plot', 'diagram', 'flowchart', 'figure'}
        photo_keywords = {'photo', 'photograph', 'picture', 'snapshot', 'view'}

        # Give a high score if keywords strongly suggest the classified content type
        if any(k in diagram_keywords for k in md_clues.keywords) and img_analysis.content_type == 'diagram':
            score = 0.8
        elif any(k in photo_keywords for k in md_clues.keywords) and img_analysis.content_type == 'photograph':
            score = 0.7
        
        # Boost score slightly for any overlapping keywords (this is a naive example)
        # A more advanced version could use word embeddings (e.g., spaCy)
        # For now, we'll keep it simple.
        
        return score

    def correlate(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict]) -> List[CorrelationMatch]:
        """
        Orchestrates the multi-strategy correlation process.

        Args:
            md_refs_clues: A list of ContextClues objects, one for each markdown reference.
            extracted_images: A list of dicts from the reporter, each containing image path and analysis.

        Returns:
            A list of CorrelationMatch objects representing the best pairings.
        """
        num_refs = len(md_refs_clues)
        num_imgs = len(extracted_images)
        
        # Create a scoring matrix: rows are markdown refs, columns are images
        score_matrix = [[0.0 for _ in range(num_imgs)] for _ in range(num_refs)]

        # --- Populate Score Matrix ---
        for i in range(num_refs):
            for j in range(num_imgs):
                md_clue = md_refs_clues[i]
                img_data = extracted_images[j]
                img_analysis = img_data['analysis']
                
                # 1. Calculate Semantic Score
                semantic_score = self._semantic_score(md_clue, img_analysis)
                
                # 2. Calculate Positional Score (based on order)
                # This gives a higher score to images that appear in a similar order as the refs
                position_diff = abs(i - j)
                position_score = max(0, 1.0 - (position_diff / num_refs))
                
                # 3. Combine scores with weights
                total_score = (semantic_score * self.weights['semantic']) + \
                              (position_score * self.weights['position'])
                
                score_matrix[i][j] = round(total_score, 4)

        # --- Find Best Matches (Greedy Algorithm) ---
        matches: List[CorrelationMatch] = []
        matched_img_indices: Set[int] = set()
        matched_ref_indices: Set[int] = set()

        # Iterate until no more high-confidence matches can be found
        while True:
            best_score = -1.0
            best_match = None
            
            # Find the highest score in the matrix for unmatched items
            for i in range(num_refs):
                if i in matched_ref_indices:
                    continue
                for j in range(num_imgs):
                    if j in matched_img_indices:
                        continue
                    
                    if score_matrix[i][j] > best_score:
                        best_score = score_matrix[i][j]
                        best_match = (i, j)

            min_confidence = self.config.get('REQUIRE_MINIMUM_CONFIDENCE', 0.4)
            if best_match and best_score >= min_confidence:
                ref_idx, img_idx = best_match
                matches.append(CorrelationMatch(
                    md_ref_index=ref_idx,
                    extracted_img_index=img_idx,
                    confidence_score=best_score,
                    strategy_used='semantic_position_blend'
                ))
                matched_ref_indices.add(ref_idx)
                matched_img_indices.add(img_idx)
            else:
                # No more confident matches found
                break
        
        logger.info(f"Correlation complete. Found {len(matches)} high-confidence matches.")
        
        # --- Fallback for unmatched references (if enabled) ---
        if self.config.get('ENABLE_FALLBACK_SEQUENTIAL', True):
            unmatched_refs = [i for i in range(num_refs) if i not in matched_ref_indices]
            unmatched_imgs = [j for j in range(num_imgs) if j not in matched_img_indices]
            
            for ref_idx in unmatched_refs:
                if unmatched_imgs:
                    # Match with the next available image in sequential order
                    img_idx = unmatched_imgs.pop(0)
                    matches.append(CorrelationMatch(
                        md_ref_index=ref_idx,
                        extracted_img_index=img_idx,
                        confidence_score=0.1, # Low confidence score for fallback
                        strategy_used='fallback_sequential'
                    ))
                    logger.debug(f"Applying fallback sequential match for MD ref {ref_idx} to image {img_idx}")

        # Sort matches by markdown reference index for orderly processing later
        matches.sort(key=lambda m: m.md_ref_index)
        return matches