# scripts/extraction/main.py

"""
Main command-line interface for the PDF to Markdown extraction pipeline.
Delegates processing tasks to the PipelineCoordinator.
"""

import argparse
import logging
import sys
import os # For initial CWD for log file if needed before coordinator

# Configure basic logging BEFORE importing other project modules that might log.
# This ensures that early log messages are captured.
# The PipelineCoordinator will further refine logging (e.g., add FileHandler).
# The log filename will be determined by PipelineCoordinator.
# For now, basic config to console.
logging.basicConfig(
    level=logging.INFO, # Default, will be overridden by args and coordinator
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Ensure console output
    ]
)
logger = logging.getLogger(__name__) # Get logger for this module

# Now import pipeline components
from .pipeline import PipelineCoordinator
# For --check-deps, PDFValidator is used by PipelineCoordinator, but good to ensure it's importable
# from .pdf_processing import PDFValidator 
from ..config import settings # To access BASE_DIR for global placeholder path if needed by CLI help

def main():
    parser = argparse.ArgumentParser(
        description='Extract PDF content to markdown with images.',
        formatter_class=argparse.RawTextHelpFormatter # For better help text formatting
    )
    
    # Group for processing actions
    processing_group = parser.add_mutually_exclusive_group()
    processing_group.add_argument('--file', help='Single PDF file to process.')
    processing_group.add_argument('--dir', help='Directory containing PDF files to process.')
    processing_group.add_argument('--course', help='Course ID prefix. Processes the first subdirectory in PDF_SOURCE_DIR starting with this ID.')
    processing_group.add_argument('--module', help='Module ID prefix. Processes the first subdirectory under PDF_SOURCE_DIR (recursively) starting with this ID.')
    processing_group.add_argument('--batch', help='Batch ID to process (subdirectory name in PDF_SOURCE_DIR), or "ALL" for all batches.')
    processing_group.add_argument('--all', action='store_true', help=f'Process all PDF files in the configured PDF_SOURCE_DIR ({settings.PDF_SOURCE_DIR}).')

    # Group for utility actions (can be run independently or before processing)
    utility_group = parser.add_argument_group('Utility Actions')
    utility_group.add_argument('--check-deps', action='store_true', help='Check if all critical dependencies are installed and exit.')
    utility_group.add_argument('--create-placeholders', action='store_true', 
                               help=f'Create/update placeholder images in the global assets directory ({os.path.join(settings.BASE_DIR, "assets", "placeholders")}) and exit.')

    parser.add_argument("--log-level", default="INFO", 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        help="Set the logging level (default: INFO).")
    
    args = parser.parse_args()

    # Initialize PipelineCoordinator: this sets up logging based on args.log_level
    # and prepares for task execution.
    coordinator = PipelineCoordinator(log_level_str=args.log_level)

    # Handle utility actions first, as they might exit
    if args.check_deps:
        logger.info("Executing dependency check...")
        if coordinator.run_dependency_check():
            print("All checked dependencies appear to be installed.")
            sys.exit(0)
        else:
            print("Some critical dependencies are missing. Please check the log for details.")
            sys.exit(1)

    if args.create_placeholders:
        logger.info("Executing global placeholder creation...")
        if coordinator.run_global_placeholder_creation():
            print("Global placeholder image task completed. Check logs for details.")
            sys.exit(0)
        else:
            print("Global placeholder image task failed. Check logs for details.")
            sys.exit(1)

    # Determine if any processing action was specified
    processing_action_specified = any([args.file, args.dir, args.course, args.module, args.batch, args.all])

    if not processing_action_specified:
        parser.print_help()
        logger.warning("No processing task specified. Use --help for options.")
        # If only --log-level was given, or no args, exit.
        # If --check-deps or --create-placeholders were run, sys.exit already happened.
        sys.exit(1) 

    # Execute main processing task
    results = coordinator.execute_processing_task(args)
    
    # Print summary
    coordinator.print_summary(results, processed_action=processing_action_specified)

    # Determine exit code
    # Exit with 1 if there were failures OR if a processing action was specified but nothing was effectively done
    # (e.g., batch ID not found, leading to 0 success and 0 failure but a message in results['failures'])
    if results.get('failure_count', 0) > 0 or \
       (processing_action_specified and results.get('success_count',0) == 0 and results.get('failure_count',0) == 0 and results.get('failures')):
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()