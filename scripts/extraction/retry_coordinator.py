# scripts/extraction/retry_coordinator.py

"""Coordinates image extraction attempts across different strategies with retry logic."""

import fitz
from PIL import Image
import logging
import time
from typing import Dict, List, Optional, Tuple, Any

from .extraction_strategies.base_strategy import BaseExtractionStrategy, StrategyTuple

logger = logging.getLogger(__name__)

class RetryCoordinator:
    """
    Orchestrates image extraction using a list of strategies with retry logic.
    """

    def __init__(self, strategies: List[StrategyTuple], config: Dict[str, Any]):
        """
        Initialize the RetryCoordinator.

        Args:
            strategies: A list of tuples, where each tuple is (StrategyClass, strategy_name).
            config: Configuration dictionary.
        """
        self.strategies = [(strategy_class(config), name) for strategy_class, name in strategies]
        self.config = config
        self.max_retries = self.config.get("max_extraction_retries", 3)
        self.retry_enabled = self.config.get("retry_failed_extractions", True)

    def coordinate_extraction(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        img_index: int,
        initial_extraction_info: Optional[Dict] = None
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt to extract a single image, trying strategies sequentially with retries.

        Args:
            pdf_document: The PyMuPDF document object.
            img_info: The image information tuple.
            page_num: The 1-indexed page number.
            img_index: The 0-indexed image index on the page.
            initial_extraction_info: Optional dictionary to initialize extraction info.

        Returns:
            Tuple containing:
            - The extracted PIL Image object, or None if all attempts failed.
            - A dictionary with cumulative extraction details and history.
        """
        xref = img_info[0]
        base_info = {
            'xref': xref,
            'page': page_num,
            'index_on_page': img_index,
            'attempts': [],
            'success': False,
            'final_error': None,
            'issue_type': 'extraction_failed'
        }
        if initial_extraction_info:
            base_info.update(initial_extraction_info)

        extracted_image = None
        attempt_count = 0
        strategy_successful = False

        # Iterate through strategies
        for strategy_instance, strategy_name in self.strategies:
            attempt_info = {
                'attempt_num': attempt_count + 1,
                'strategy': strategy_name,
                'start_time': time.time(),
                'success': False,
                'error': None,
                'issue_type': None,
                'details': {}
            }
            base_info['attempts'].append(attempt_info)
            attempt_count += 1

            logger.debug(f"Attempt {attempt_count}: Trying strategy '{strategy_name}' for xref {xref} on page {page_num}")

            # Call the strategy's extract method
            current_extraction_info = attempt_info['details'] # Pass the details dict for strategy to fill
            extracted_image, updated_extraction_info = strategy_instance.extract(
                 pdf_document, img_info, page_num, current_extraction_info
            )
            attempt_info.update(updated_extraction_info) # Update attempt_info with details and success status
            attempt_info['end_time'] = time.time()
            attempt_info['duration'] = attempt_info['end_time'] - attempt_info['start_time']


            if extracted_image is not None and attempt_info.get('success', False):
                strategy_successful = True
                break # Success, no need to try other strategies

            # Log strategy failure
            logger.debug(f"Strategy '{strategy_name}' failed for xref {xref} on page {page_num}: {attempt_info.get('error', 'No specific error provided.')}")


        # After trying all strategies (or first successful one)
        base_info['attempt_count'] = attempt_count # Total attempts across strategies
        if extracted_image is not None and strategy_successful:
            base_info['success'] = True
            # Take final success info from the successful attempt's details
            successful_attempt_info = base_info['attempts'][-1]['details']
            base_info['dimensions'] = successful_attempt_info.get('dimensions')
            base_info['mode'] = successful_attempt_info.get('mode')
            base_info['extraction_method'] = successful_attempt_info.get('extraction_method')
            if 'warning' in successful_attempt_info:
                 base_info['warning'] = successful_attempt_info['warning']

            logger.debug(f"Extraction successful after {attempt_count} attempts for xref {xref} on page {page_num}")

        else:
            base_info['success'] = False
            base_info['final_error'] = f"All {attempt_count} extraction attempts failed."
            # Propagate the last known issue type if available
            last_attempt = base_info['attempts'][-1] if base_info['attempts'] else {}
            base_info['issue_type'] = last_attempt.get('issue_type', 'extraction_failed')
            logger.error(f"Extraction failed after {attempt_count} attempts for xref {xref} on page {page_num}. Last error: {last_attempt.get('error', 'Unknown error.')}")


        return extracted_image, base_info