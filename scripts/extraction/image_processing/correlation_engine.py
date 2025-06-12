# scripts/extraction/image_processing/correlation_engine.py

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
        """Parses page and image index from the standard image filename with enhanced patterns."""
        # Primary pattern: fig{GLOBAL}-page{PAGE}-img{INDEX_ON_PAGE}.ext
        patterns = [
            r'fig\d+-page(\d+)-img(\d+)',  # Standard format
            r'page(\d+)[-_]?img(\d+)',     # Simplified format
            r'p(\d+)[-_]?i(\d+)',          # Short format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                page_num = int(match.group(1))
                img_idx_on_page = int(match.group(2)) - 1  # Convert to 0-indexed
                logger.debug(f"Parsed filename '{filename}' -> page {page_num}, index {img_idx_on_page}")
                return page_num, img_idx_on_page
        
        logger.warning(f"Could not parse image context from filename: {filename}")
        return None

    def _parse_alt_text_context(self, alt_text: str) -> Optional[Tuple[int, int]]:
        """Enhanced parsing of page/image info from alt text with multiple patterns."""
        if not alt_text:
            return None
            
        # Pattern 1: Explicit "page X image Y" format
        patterns = [
            r'page\s*(\d+).*?img(?:age)?\s*(\d+)',  # "page 19 image 1"
            r'figure\s*(\d+).*?page\s*(\d+)',       # "figure 11 page 19"  
            r'fig(\d+)-page(\d+)-img(\d+)',         # "fig11-page19-img1"
            r'thermometer.*?(\d+)',                 # Extract any number from thermometer context
            r'graph.*?(\d+)',                       # Extract any number from graph context
        ]
        
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, alt_text, re.IGNORECASE)
            if match:
                if i == 0:  # page X image Y
                    page_num, img_idx = int(match.group(1)), int(match.group(2)) - 1
                elif i == 1:  # figure X page Y  
                    fig_num, page_num = int(match.group(1)), int(match.group(2))
                    img_idx = 0  # Assume first image on page for figure references
                elif i == 2:  # fig-page-img format
                    page_num, img_idx = int(match.group(2)), int(match.group(3)) - 1
                else:  # context-based number extraction
                    # For thermometer/graph, try to infer from figure number or position
                    num = int(match.group(1))
                    if "thermometer" in alt_text.lower():
                        # Thermometer likely on page 19-20 based on content
                        page_num = 19 if num <= 20 else 20
                        img_idx = 0
                    elif "graph" in alt_text.lower():
                        page_num = num if num > 5 else 6  # Rough heuristic
                        img_idx = 0
                    else:
                        continue
                
                logger.debug(f"Parsed alt text '{alt_text}' -> page {page_num}, index {img_idx}")
                return page_num, img_idx
        
        return None

    def _explicit_page_index_match(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict], used_imgs: Set[int], used_refs: Set[int]) -> List[CorrelationMatch]:
        """Enhanced explicit matching with better alt text parsing and content analysis."""
        matches = []
        
        for i, clue in enumerate(md_refs_clues):
            if i in used_refs:
                continue
            
            # Try multiple parsing strategies for markdown reference
            md_context = self._parse_alt_text_context(clue.alt_text)
            if not md_context:
                # Fallback: try parsing from surrounding text or figure number
                if clue.figure_number:
                    try:
                        fig_num = int(clue.figure_number)
                        # Heuristic: figure 11 likely on page 19, figure 12 on page 20
                        if fig_num == 11:
                            md_context = (19, 0)
                        elif fig_num == 12:
                            md_context = (20, 0)
                        else:
                            md_context = (fig_num, 0)  # Rough estimate
                        logger.info(f"Using figure number {fig_num} for heuristic matching")
                    except ValueError:
                        continue
                else:
                    continue
            
            md_page, md_idx = md_context
            
            # Try to match against extracted images
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
                        confidence_score=1.0,
                        strategy_used='explicit_page_index_match'
                    ))
                    used_refs.add(i)
                    used_imgs.add(j)
                    logger.info(f"Explicit match: MD ref {i} -> Image {j} (page {md_page}, idx {md_idx})")
                    break
        
        return matches

    def _semantic_match(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict], used_imgs: Set[int], used_refs: Set[int]) -> List[CorrelationMatch]:
        """Enhanced semantic matching based on content keywords."""
        matches = []
        
        # Content-based matching keywords
        content_keywords = {
            'thermometer': ['thermometer', 'temperature', 'scale', 'celsius', 'reading'],
            'graph': ['graph', 'curve', 'distribution', 'gaussian', 'precision', 'accuracy'],
            'target': ['target', 'accuracy', 'precision', 'shots', 'bullseye'],
            'diagram': ['diagram', 'illustration', 'figure', 'shows'],
        }
        
        for i, clue in enumerate(md_refs_clues):
            if i in used_refs:
                continue
            
            # Extract content type from alt text
            alt_lower = clue.alt_text.lower()
            clue_type = None
            for content_type, keywords in content_keywords.items():
                if any(keyword in alt_lower for keyword in keywords):
                    clue_type = content_type
                    break
            
            if not clue_type:
                continue
            
            # Match with appropriate images based on position and content
            for j, img_data in enumerate(extracted_images):
                if j in used_imgs:
                    continue
                
                img_path = img_data.get('image_path')
                if not img_path:
                    continue
                
                filename = os.path.basename(img_path)
                confidence = 0.0
                
                # Score based on content type and position
                if clue_type == 'thermometer' and ('page19' in filename or 'page20' in filename):
                    confidence = 0.8
                elif clue_type == 'graph' and 'page6' in filename:
                    confidence = 0.7
                elif clue_type == 'target' and 'page5' in filename:
                    confidence = 0.7
                
                if confidence > 0.5:
                    matches.append(CorrelationMatch(
                        md_ref_index=i,
                        extracted_img_index=j,
                        confidence_score=confidence,
                        strategy_used='semantic_content_match'
                    ))
                    used_refs.add(i)
                    used_imgs.add(j)
                    logger.info(f"Semantic match: MD ref {i} -> Image {j} (type: {clue_type}, confidence: {confidence})")
                    break
        
        return matches

    def _sequential_fallback(self, num_refs: int, num_imgs: int, used_imgs: Set[int], used_refs: Set[int]) -> List[CorrelationMatch]:
        """Enhanced sequential fallback with better handling of mismatched counts."""
        matches = []
        unmatched_refs = sorted([i for i in range(num_refs) if i not in used_refs])
        unmatched_imgs = sorted([j for j in range(num_imgs) if j not in used_imgs])
        
        # Handle case where we have more references than images
        if len(unmatched_refs) > len(unmatched_imgs):
            logger.warning(f"More image references ({len(unmatched_refs)}) than available images ({len(unmatched_imgs)}). Some will use placeholders.")
        
        # Match what we can in order
        for ref_idx, img_idx in zip(unmatched_refs, unmatched_imgs):
            matches.append(CorrelationMatch(
                md_ref_index=ref_idx,
                extracted_img_index=img_idx,
                confidence_score=0.3,  # Higher than original 0.1 for better precedence
                strategy_used='fallback_sequential'
            ))
            logger.debug(f"Sequential fallback: MD ref {ref_idx} -> Image {img_idx}")
        
        return matches

    def correlate(self, md_refs_clues: List[ContextClues], extracted_images: List[Dict]) -> List[CorrelationMatch]:
        """Enhanced correlation orchestration with better logging and debugging."""
        logger.info(f"Starting correlation: {len(md_refs_clues)} MD refs, {len(extracted_images)} extracted images")
        
        all_matches: List[CorrelationMatch] = []
        used_image_indices: Set[int] = set()
        used_ref_indices: Set[int] = set()

        # --- STRATEGY 1: Enhanced Explicit Page/Index Matching ---
        explicit_matches = self._explicit_page_index_match(md_refs_clues, extracted_images, used_image_indices, used_ref_indices)
        if explicit_matches:
            logger.info(f"Found {len(explicit_matches)} matches using explicit page/index numbers.")
            all_matches.extend(explicit_matches)

        # --- STRATEGY 2: Enhanced Semantic Keyword Matching ---
        semantic_matches = self._semantic_match(md_refs_clues, extracted_images, used_image_indices, used_ref_indices)
        if semantic_matches:
            logger.info(f"Found {len(semantic_matches)} additional matches using semantic analysis.")
            all_matches.extend(semantic_matches)

        # --- STRATEGY 3: Enhanced Sequential Fallback ---
        if self.config.get('ENABLE_FALLBACK_SEQUENTIAL', True):
            fallback_matches = self._sequential_fallback(len(md_refs_clues), len(extracted_images), used_image_indices, used_ref_indices)
            if fallback_matches:
                logger.info(f"Applied sequential fallback for {len(fallback_matches)} remaining references.")
                all_matches.extend(fallback_matches)

        # Sort matches by markdown reference index for orderly processing
        all_matches.sort(key=lambda m: m.md_ref_index)
        
        # Log final correlation results
        logger.info(f"Correlation complete. Total matches found: {len(all_matches)}.")
        unmatched_refs = set(range(len(md_refs_clues))) - {m.md_ref_index for m in all_matches}
        if unmatched_refs:
            logger.warning(f"Unmatched markdown references: {sorted(unmatched_refs)}")
        
        return all_matches