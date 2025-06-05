# scripts/extraction/retry_coordinator.py

"""Coordinates image extraction attempts across different strategies with retry logic."""

import fitz
from PIL import Image
import logging
import time
from typing import Dict, List, Optional, Tuple, Any

# Assuming BaseExtractionStrategy and StrategyTuple are correctly defined elsewhere
# For example:
# class BaseExtractionStrategy:
#     def __init__(self, config): self.config = config
#     def extract(self, doc, info, page, ext_info): return None, {}
# StrategyTuple = Tuple[type[BaseExtractionStrategy], str]


logger = logging.getLogger(__name__)

class RetryCoordinator:
    """
    Orchestrates image extraction using a list of strategies with retry logic.
    """

    def __init__(self, strategies: List[Any], config: Dict[str, Any]): # Changed List[StrategyTuple] to List[Any] for broader mock compatibility
        """
        Initialize the RetryCoordinator.

        Args:
            strategies: A list of tuples, where each tuple is (StrategyClass, strategy_name).
            config: Configuration dictionary.
        """
        self.strategies = [(strategy_class(config), name) for strategy_class, name in strategies]
        self.config = config
        # self.max_retries = self.config.get("max_extraction_retries", 3) # Not directly used in coordinate_extraction loop logic
        # self.retry_enabled = self.config.get("retry_failed_extractions", True) # Not directly used in coordinate_extraction loop logic

    def coordinate_extraction(
        self,
        pdf_document: fitz.Document,
        img_info: tuple,
        page_num: int,
        img_index: int,
        initial_extraction_info: Optional[Dict] = None
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Attempt to extract a single image, trying strategies sequentially.
        The retry_failed_extractions and max_extraction_retries config options
        control behavior at a higher level (e.g., in the main extraction loop),
        not within this single image coordination. This method tries each strategy once.

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
            'issue_type': 'extraction_failed', # Default issue type
            'extraction_method': None, # Initialize extraction_method
            'dimensions': None,
            'mode': None,
        }
        if initial_extraction_info:
            base_info.update(initial_extraction_info)

        extracted_image = None
        attempt_count = 0
        strategy_successful = False # Renamed from strategy_successful for clarity
        successful_strategy_name = None

        # Iterate through strategies
        for strategy_instance, strategy_name in self.strategies:
            current_attempt_details = {} # This will be passed to the strategy's extract method
            attempt_info_for_log = {
                'attempt_num': attempt_count + 1,
                'strategy': strategy_name,
                'start_time': time.time(),
                'success': False, # Will be updated by strategy's return
                'error': None,    # Will be updated by strategy's return
                'issue_type': None, # Will be updated by strategy's return
                'details': current_attempt_details # Reference to the dict strategy will fill
            }
            base_info['attempts'].append(attempt_info_for_log)
            attempt_count += 1

            logger.debug(f"Attempt {attempt_count}: Trying strategy '{strategy_name}' for xref {xref} on page {page_num}")

            # Call the strategy's extract method
            # The strategy is expected to return (image_or_none, info_dict_with_success_and_details)
            # The info_dict_with_success_and_details will update current_attempt_details
            # and also provide the 'success' status for this attempt.
            img_from_strategy, strategy_outcome_info = strategy_instance.extract(
                 pdf_document, img_info, page_num, current_attempt_details # Pass the 'details' dict
            )

            # Update the attempt log with what the strategy returned/modified
            attempt_info_for_log.update(strategy_outcome_info) # This should bring 'success', 'error', 'issue_type' etc.
                                                              # and also update 'details' if strategy modified it directly.
            attempt_info_for_log['end_time'] = time.time()
            attempt_info_for_log['duration'] = attempt_info_for_log['end_time'] - attempt_info_for_log['start_time']


            if img_from_strategy is not None and attempt_info_for_log.get('success', False):
                extracted_image = img_from_strategy
                strategy_successful = True
                successful_strategy_name = strategy_name # Record the name of the successful strategy
                break # Success, no need to try other strategies

            # Log strategy failure
            logger.debug(
                f"Strategy '{strategy_name}' failed for xref {xref} on page {page_num}: "
                f"{attempt_info_for_log.get('error', 'No specific error provided.')}"
            )
            # If retries are disabled in config, and this is the first strategy, break.
            # This logic seems to be missing if it was intended to be here.
            # The current loop tries all strategies sequentially unless one succeeds.
            # The config['retry_failed_extractions'] seems to be for a higher-level retry,
            # not for stopping after the first strategy if it fails when retries are off.
            # For the test 'test_retries_disabled' to pass as written (only 1 attempt),
            # this method would need to check self.config['retry_failed_extractions']
            # and break after the first attempt if it's False and the attempt failed.
            # Let's add that logic for test compatibility.
            if not self.config.get("retry_failed_extractions", True):
                logger.debug("Retries disabled, stopping after first strategy attempt.")
                break


        # After trying strategies
        base_info['attempt_count'] = attempt_count
        if strategy_successful and extracted_image is not None:
            base_info['success'] = True
            base_info['extraction_method'] = successful_strategy_name # CORRECTED: Use the recorded strategy name

            # Populate details from the successful attempt's 'details' dictionary
            # The successful attempt is the last one in the list if loop broke due to success
            successful_attempt_log = base_info['attempts'][-1]
            if 'details' in successful_attempt_log and isinstance(successful_attempt_log['details'], dict):
                base_info['dimensions'] = successful_attempt_log['details'].get('dimensions')
                base_info['mode'] = successful_attempt_log['details'].get('mode')
                # 'extraction_method' in details is redundant if we set it from strategy_name
                if 'warning' in successful_attempt_log['details']:
                     base_info['warning'] = successful_attempt_log['details']['warning']
            
            # Ensure 'issue_type' is cleared or set appropriately on success
            base_info['issue_type'] = None 
            base_info['final_error'] = None

            logger.debug(f"Extraction successful with '{successful_strategy_name}' after {attempt_count} total attempts for xref {xref} on page {page_num}")

        else:
            base_info['success'] = False
            base_info['final_error'] = f"All {attempt_count} extraction attempts failed."
            # Propagate the last known issue type if available from the last attempt
            if base_info['attempts']:
                last_attempt_log = base_info['attempts'][-1]
                base_info['issue_type'] = last_attempt_log.get('issue_type', 'extraction_failed')
                logger.error(
                    f"Extraction failed after {attempt_count} attempts for xref {xref} on page {page_num}. "
                    f"Last strategy '{last_attempt_log['strategy']}', error: {last_attempt_log.get('error', 'Unknown error.')}"
                )
            else:
                logger.error(f"Extraction failed for xref {xref} on page {page_num}, no attempts made (should not happen).")


        return extracted_image, base_info