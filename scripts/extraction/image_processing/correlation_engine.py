import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Set, Tuple
import os

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

    def _get_image_context(self, filename: str) -> Optional[Tuple[int, int]]:
        """Parses page and image index from the standard image filename."""
        # Pattern: fig{GLOBAL}-page{PAGE}-img{INDEX_ON_PAGE}.ext
        match = re.search(r'page(\d+)[-_]?img(\d+)', filename, re.IGNORECASE)
        if match:
            page_num = int(match.group(1))
            img_idx_on_page = int(match.group(2)) - 1  # Convert to 0-indexed
            return page_num, img_idx_on_page
        return None

    def _explicit_page_index_match(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict], used_imgs: Set[int], used_refs: Set[int]) -> List[CorrelationMatch]:
        """
        Highest-priority strategy: Match based on explicit page/index numbers
        found in filenames and markdown alt text.
        """
        matches = []
        for i, clue in enumerate(md_refs_clues):
            if i in used_refs:
                continue

            # In our ContentAnalyser, we didn't add page/index parsing yet.
            # Let's add a simple version here for now.
            alt_text_match = re.search(r'page\s*(\d+).*img\s*(\d+)', clue.alt_text, re.IGNORECASE)
            if not alt_text_match:
                continue
            
            md_page, md_idx = int(alt_text_match.group(1)), int(alt_text_match.group(2)) - 1

            for j, img_data in enumerate(extracted_images):
                if j in used_imgs:
                    continue
                
                img_path = img_data.get('image_path')
                if not img_path:
                    continue
                
                img_context = self._get_image_context(os.path.basename(img_path))
                if img_context and img_context == (md_page, md_idx):
                    matches.append(CorrelationMatch(
                        md_ref_index=i,
                        extracted_img_index=j,
                        confidence_score=1.0, # Highest confidence
                        strategy_used='explicit_page_index_match'
                    ))
                    used_refs.add(i)
                    used_imgs.add(j)
                    break # Move to the next markdown reference
        return matches

    def _semantic_match(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict], used_imgs: Set[int], used_refs: Set[int]) -> List[CorrelationMatch]:
        """
        Second-priority strategy: Match based on keyword context.
        """
        matches = []
        # This is a placeholder for the more advanced semantic logic.
        # For now, it will be simple, but it runs after explicit matches are found.
        # In a future iteration, this would be more fleshed out.
        # The explicit matching should solve the primary issue.
        return matches

    def _sequential_fallback(self, num_refs: int, num_imgs: int, used_imgs: Set[int], used_refs: Set[int]) -> List[CorrelationMatch]:
        """Last resort: Match remaining items in order."""
        matches = []
        unmatched_refs = sorted([i for i in range(num_refs) if i not in used_refs])
        unmatched_imgs = sorted([j for j in range(num_imgs) if j not in used_imgs])

        for ref_idx, img_idx in zip(unmatched_refs, unmatched_imgs):
            matches.append(CorrelationMatch(
                md_ref_index=ref_idx,
                extracted_img_index=img_idx,
                confidence_score=0.1,
                strategy_used='fallback_sequential'
            ))
        return matches

    def correlate(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict]) -> List[CorrelationMatch]:
        """
        Orchestrates the multi-strategy correlation process.
        """
        all_matches: List[CorrelationMatch] = []
        used_image_indices: Set[int] = set()
        used_ref_indices: Set[int] = set()

        # --- STRATEGY 1: Explicit Page/Index Matching (Highest Priority) ---
        explicit_matches = self._explicit_page_index_match(md_refs_clues, extracted_images, used_image_indices, used_ref_indices)
        if explicit_matches:
            logger.info(f"Found {len(explicit_matches)} matches using explicit page/index numbers.")
            all_matches.extend(explicit_matches)

        # --- STRATEGY 2: Semantic Keyword Matching (Medium Priority) ---
        # This will run on the remaining unmatched items.
        semantic_matches = self._semantic_match(md_refs_clues, extracted_images, used_image_indices, used_ref_indices)
        if semantic_matches:
            logger.info(f"Found {len(semantic_matches)} additional matches using semantic analysis.")
            all_matches.extend(semantic_matches)
            for match in semantic_matches:
                used_ref_indices.add(match.md_ref_index)
                used_image_indices.add(match.extracted_img_index)

        # --- STRATEGY 3: Sequential Fallback (Lowest Priority) ---
        if self.config.get('ENABLE_FALLBACK_SEQUENTIAL', True):
            fallback_matches = self._sequential_fallback(len(md_refs_clues), len(extracted_images), used_image_indices, used_ref_indices)
            if fallback_matches:
                logger.info(f"Applied sequential fallback for {len(fallback_matches)} remaining references.")
                all_matches.extend(fallback_matches)

        # Sort matches by markdown reference index for orderly processing
        all_matches.sort(key=lambda m: m.md_ref_index)
        logger.info(f"Correlation complete. Total matches found: {len(all_matches)}.")
        return all_matches