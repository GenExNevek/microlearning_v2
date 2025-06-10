# scripts/extraction/pipeline/pipeline_coordinator.py

"""
High-level coordinator for the PDF extraction pipeline.
Manages overall workflow, configuration, logging, and CLI command delegation.
"""

import os
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional

from ...config import settings
from .batch_processor import BatchProcessor
from .extraction_orchestrator import ExtractionOrchestrator # For global placeholder creation
from ..pdf_processing import PDFValidator
from ..output_management import DirectoryManager # For global placeholder creation path

logger = logging.getLogger(__name__)

class PipelineCoordinator:
    """
    Coordinates the entire PDF to Markdown extraction pipeline,
    including setup, command delegation, and summary reporting.
    """

    def __init__(self, log_level_str: str = "INFO"):
        self.log_level_str = log_level_str
        self._configure_logging()

        self.pdf_validator = PDFValidator()
        # ExtractionOrchestrator is needed by BatchProcessor, and also for global placeholder creation
        self.extraction_orchestrator = ExtractionOrchestrator()
        self.batch_processor = BatchProcessor(extraction_orchestrator=self.extraction_orchestrator)
        
        self.start_time = datetime.now()
        self.log_filename = f"extraction_log_{self.start_time.strftime('%Y%m%d_%H%M%S')}.log"
        self._setup_file_logger()

        logger.info("PipelineCoordinator initialized.")
        logger.info(f"Logging to console and to file: {self.log_filename}")


    def _configure_logging(self):
        """Sets the global logging level."""
        numeric_level = getattr(logging, self.log_level_str.upper(), None)
        if not isinstance(numeric_level, int):
            # This should ideally not happen if arg parsing choices are used
            logging.getLogger().critical(f'Invalid log level: {self.log_level_str}. Defaulting to INFO.')
            numeric_level = logging.INFO
        
        # Configure root logger
        # StreamHandler is typically added by basicConfig or by the initial main.py setup.
        # We ensure the level is set.
        logging.getLogger().setLevel(numeric_level)
        
        # If specific loggers (like 'scripts.extraction') were configured with a higher default,
        # ensure they also adhere to the requested level.
        # This assumes a base logger for the 'scripts' package or similar.
        logging.getLogger('scripts').setLevel(numeric_level) # Example for a parent logger
        
        logger.info(f"Logging level set to {self.log_level_str.upper()}")

    def _setup_file_logger(self):
        """Adds a FileHandler to the root logger."""
        root_logger = logging.getLogger()
        # Remove existing FileHandlers to avoid duplicate logging if re-initialized
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                if hasattr(handler, 'baseFilename') and os.path.basename(handler.baseFilename).startswith("extraction_log_"):
                    root_logger.removeHandler(handler)
                    handler.close()

        file_handler = logging.FileHandler(self.log_filename)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


    def run_dependency_check(self) -> bool:
        """Runs system dependency validation."""
        logger.info("Performing system dependency check...")
        return self.pdf_validator.validate_system_dependencies()

    def run_global_placeholder_creation(self) -> bool:
        """Creates or updates placeholder images in the global assets/placeholders directory."""
        global_placeholder_dir = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')
        logger.info(f"Ensuring global placeholder images in: {global_placeholder_dir}")
        try:
            # The create_placeholder_images_in_folder method is part of ExtractionOrchestrator
            # It needs a DirectoryManager instance, which it has by default.
            self.extraction_orchestrator.create_placeholder_images_in_folder(global_placeholder_dir)
            logger.info(f"Global placeholder image task complete for {global_placeholder_dir}.")
            return True
        except Exception as e: # pragma: no cover
            logger.error(f"Failed during global placeholder creation: {e}", exc_info=True)
            return False

    def execute_processing_task(self, args: Any) -> Dict[str, Any]:
        """
        Executes the main processing task based on parsed CLI arguments.

        Args:
            args: Parsed arguments object from argparse.

        Returns:
            A dictionary summarizing the results of the task.
        """
        results: Dict[str, Any] = {'success_count': 0, 'failure_count': 0, 'failures': []}
        processed_action = False

        if not self.run_dependency_check(): # Always run dep check before main tasks
            logger.critical("Critical dependencies missing. Aborting main processing task.")
            results['failures'].append("Critical dependencies missing.")
            results['failure_count'] = 1 # Represent this as a failure
            return results

        if args.file:
            processed_action = True
            results = self.batch_processor.process_single_file(args.file)
        elif args.dir:
            processed_action = True
            results = self.batch_processor.process_directory(args.dir)
        elif args.course:
            processed_action = True
            results = self.batch_processor.process_by_course_id(args.course)
        elif args.module:
            processed_action = True
            results = self.batch_processor.process_by_module_id(args.module)
        elif args.batch: # Covers "ALL" or specific batch ID
            processed_action = True
            results = self.batch_processor.process_batch_by_id(args.batch)
        elif args.all:
            processed_action = True
            # Process all implies processing the root PDF_SOURCE_DIR
            results = self.batch_processor.process_batch_by_id("ALL") 
        
        if not processed_action:
            # This case should ideally be caught by argparse (e.g. if no action arg is required)
            # or handled in main.py before calling execute_processing_task.
            # If it reaches here, it means no processing task was matched from args.
            logger.error("No processing task specified or matched.")
            results['failures'].append("No processing task specified.")
            # No specific file failed, but the operation itself did not proceed.
            # We might not increment failure_count here unless it's a "task failure".
            # Let main.py handle exit code based on processed_action.
        
        return results

    def print_summary(self, results: Dict[str, Any], processed_action: bool):
        """Prints a summary of the processing results."""
        elapsed_time = datetime.now() - self.start_time
        logger.info("--- Processing Summary ---")
        logger.info(f"Completed in {elapsed_time}")
        
        if not processed_action and not (results.get('success_count',0) > 0 or results.get('failure_count',0) > 0):
             if results.get('failures'):
                 logger.info(f"No files processed. Reason: {results['failures'][0]}")
             else:
                 logger.info("No processing actions were performed (e.g., only --check-deps or --create-placeholders was run).")

        else: # Some processing action was attempted
            total_attempted = results.get('success_count', 0) + results.get('failure_count', 0)
            if total_attempted == 0 and results.get('failures'): # e.g. dir not found for batch
                logger.info(f"No files processed. Reason: {results['failures'][0]}")
            else:
                logger.info(f"Total files/operations attempted: {total_attempted}")
                logger.info(f"Successful transformations: {results.get('success_count', 0)}")
                logger.info(f"Failed transformations/operations: {results.get('failure_count', 0)}")

        if results.get('failures'):
            logger.warning("Details of failures/issues:")
            for failure_path_or_msg in results['failures']:
                logger.warning(f"  - {failure_path_or_msg}")
        
        logger.info(f"Detailed log available at: {self.log_filename}")
        logger.info("--- End of Summary ---")