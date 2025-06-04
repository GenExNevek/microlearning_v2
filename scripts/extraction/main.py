# scripts/extraction/main.py

"""Main script for orchestrating the PDF to markdown extraction pipeline."""

import os
import argparse
import logging
import shutil
from typing import Dict
from datetime import datetime
# Assuming pdf_reader, markdown_formatter, file_writer are in the same package
from .pdf_reader import PDFReader
from .markdown_formatter import MarkdownFormatter
from .file_writer import FileWriter
# The old generate_extraction_report is removed, reporter handles it
# from .image_extractor import generate_extraction_report # REMOVED
# Import the refactored ImageExtractor class
from .image_extractor import ImageExtractor
# Import settings - path depends on directory structure
from ..config import settings # Assuming config is in the parent directory

# Configure logging
# Note: Moved basicConfig outside if __name__ == "__main__": for earlier setup
# but keep handlers configurable if needed later.
# For now, keeping it simple as in the original file structure intent.
log_filename = f"extraction_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def transform_pdf_to_markdown(source_file: str, target_file: str) -> bool:
    """
    Transform a PDF file to a markdown file.

    Args:
        source_file: Path to source PDF file
        target_file: Path to target markdown file

    Returns:
        Boolean indicating success or failure
    """
    # Skip non-PDF files
    if not source_file.lower().endswith('.pdf'):
        logger.info(f"Skipping non-PDF file: {source_file}")
        return False

    # Change file extension from .pdf to .md
    target_file = target_file.replace('.pdf', '.md')

    # Get directories
    target_dir = os.path.dirname(target_file)

    # Create the directory if it doesn't exist
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create target directory {target_dir}: {e}")
        return False


    # Process the PDF file
    reader = PDFReader()
    # MarkdownFormatter now initializes ImageExtractor internally
    formatter = MarkdownFormatter(reader)

    logger.info(f"Starting transformation: {source_file} -> {target_file}")

    try:
        # Read the PDF
        pdf_info = reader.read_pdf_from_path(source_file)

        # Extract metadata from the path
        metadata = formatter.extract_metadata_from_path(source_file)

        # Extract and format the content (this now includes image extraction orchestrated by formatter)
        # The result includes the full image extraction summary from the reporter
        result = formatter.extract_and_format(pdf_info, metadata)

        # Access the image extraction results from the returned result dictionary
        image_extraction_results = result.get('image_extraction', {})

        if result['success']:
            # Write the markdown file
            FileWriter.write_markdown_file(result['content'], target_file)

            # Create image assets folder (already created during extraction, but ensure it exists)
            # The formatter's _get_image_assets_dir ensures this, but calling it here
            # provides the path needed for placeholder creation.
            img_assets_folder = formatter._get_image_assets_dir(source_file, metadata)
            FileWriter.create_image_assets_folder(target_file) # Double check ensures folder structure


            # Process image extraction results - handles placeholders and logs summary
            # The report file is now saved by the ImageExtractor itself via its reporter.
            # We only need to check for issues here and create placeholders if necessary.
            process_image_extraction_issues(
                image_extraction_results,
                img_assets_folder
            )

            # Log the results
            logger.info(f"Transformed: {source_file} -> {target_file}")

            # Log image extraction summary based on the results dict
            img_extracted_count = image_extraction_results.get('extracted_count', 0)
            img_failed_count = image_extraction_results.get('failed_count', 0) # Includes validation/processing failures
            img_validation_failures = image_extraction_results.get('metrics', {}).get('validation_failures', 0) # Specific validation fail count
            img_problematic_count = len(image_extraction_results.get('problematic_images', []))
            img_report_path = image_extraction_results.get('report_path')


            if img_failed_count > 0 or img_problematic_count > 0:
                logger.warning(
                    f"Image extraction issues found for {source_file}: "
                    f"{img_extracted_count} extracted OK, "
                    f"{img_failed_count} problematic/failed, "
                    f"({img_validation_failures} validation issues)"
                )
                if img_report_path:
                     logger.warning(f"Image extraction report saved to: {img_report_path}")

            else:
                logger.info(f"Successfully extracted {img_extracted_count} images for {source_file} to: {img_assets_folder}")

            # Log any top-level errors captured during the extraction process (e.g. PDF open failure)
            if image_extraction_results.get('errors'):
                for error in image_extraction_results['errors']:
                    logger.error(f"Image extraction process error: {error}") # Use error level for top-level errors

            return True
        else:
            logger.error(f"Error transforming {source_file}: {result.get('error', 'Unknown error')}")

            # Log image extraction errors/issues captured within the extraction results
            if image_extraction_results.get('errors'):
                for error in image_extraction_results['errors']:
                    logger.error(f"Image extraction process error: {error}") # Use error level here too

            # Also log details about problematic images if extraction results are available
            if image_extraction_results.get('problematic_images'):
                 logger.error(f"Details for problematic images in {source_file}:")
                 for p_img in image_extraction_results['problematic_images']:
                     logger.error(f"  - Page {p_img.get('page', '?')}, Index {p_img.get('index_on_page', '?')}: Issue '{p_img.get('issue_type', 'unknown')}' - {p_img.get('issue', 'No details')}")


            return False

    except Exception as e:
        logger.error(f"Exception processing {source_file}: {str(e)}", exc_info=True) # Log traceback for unexpected exceptions
        return False


# Renamed and simplified this function
def process_image_extraction_issues(extraction_results: Dict, img_assets_folder: str) -> bool:
    """
    Check for issues in image extraction results and create placeholder images if needed.
    The report generation itself is handled by the ImageExtractor's reporter component.

    Args:
        extraction_results: Results dictionary from ImageExtractor (via formatter).
        img_assets_folder: Image assets folder path.

    Returns:
        Boolean indicating whether there were issues with image extraction/processing.
    """
    # Check if we have results and problematic images
    problematic_count = len(extraction_results.get('problematic_images', []))
    failed_count = extraction_results.get('failed_count', 0) # Total images not successfully saved+validated

    # Determine if there were issues
    has_issues = problematic_count > 0 or failed_count > 0

    # Create placeholder images if needed
    if has_issues:
        logger.debug(f"Problematic images found ({problematic_count}), creating placeholder images in {img_assets_folder}")
        create_placeholder_images(img_assets_folder)

    return has_issues


def create_placeholder_images(img_assets_folder):
    """
    Create or copy placeholder images for different issue types.

    Args:
        img_assets_folder: Folder to place placeholder images
    """
    # Define placeholder types and source files
    # Paths adjusted assuming 'assets' is in the BASE_DIR, sibling to 'scripts'
    base_asset_path = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')

    placeholders = {
        'placeholder-blank.png': os.path.join(base_asset_path, 'blank-image.png'),
        'placeholder-corrupt.png': os.path.join(base_asset_path, 'corrupt-image.png'),
        'placeholder-error.png': os.path.join(base_asset_path, 'error-image.png') # Generic error placeholder
    }

    # Create or use builtin placeholders if needed
    for placeholder_name, source_path in placeholders.items():
        target_path = os.path.join(img_assets_folder, placeholder_name)

        # Only create if it doesn't exist
        if not os.path.exists(target_path):
            try:
                if os.path.exists(source_path):
                    # Copy existing placeholder
                    shutil.copy2(source_path, target_path)
                    logger.debug(f"Copied placeholder image: {placeholder_name} to {target_path}")
                else:
                    # Create a simple text-based placeholder image if source doesn't exist
                    # Import Pillow inside function to keep it optional if not needed for placeholders
                    from PIL import Image, ImageDraw, ImageFont
                    img = Image.new('RGB', (400, 300), color=(240, 240, 240))
                    d = ImageDraw.Draw(img)

                    # Try to use a system font, fallback to default
                    try:
                        # Prefer a common sans-serif font
                        font = ImageFont.truetype("arial.ttf", 20) # Use .ttf extension for common check
                    except IOError:
                         try:
                              font = ImageFont.truetype("DejaVuSans.ttf", 20) # Another common alternative
                         except IOError:
                              font = ImageFont.load_default() # Fallback


                    issue_type_display = placeholder_name.replace('placeholder-', '').replace('.png', '').replace('-', ' ').title()
                    message = f"Image Issue: {issue_type_display}"
                    message_line2 = "See report for details."

                    # Add text to the image
                    try:
                        # Calculate text size to center
                        text_bbox_line1 = d.textbbox((0,0), message, font=font)
                        text_width_line1 = text_bbox_line1[2] - text_bbox_line1[0]
                        text_height_line1 = text_bbox_line1[3] - text_bbox_line1[1]

                        text_bbox_line2 = d.textbbox((0,0), message_line2, font=font)
                        text_width_line2 = text_bbox_line2[2] - text_bbox_line2[0]
                        text_height_line2 = text_bbox_line2[3] - text_bbox_line2[1]


                        img_width, img_height = img.size
                        y_pos1 = (img_height - text_height_line1 - text_height_line2 - 5) / 2 # 5px spacing between lines
                        y_pos2 = y_pos1 + text_height_line1 + 5

                        d.text(
                            ((img_width - text_width_line1) / 2, y_pos1),
                            message,
                            fill=(200, 0, 0),
                            font=font
                        )
                        d.text(
                            ((img_width - text_width_line2) / 2, y_pos2),
                            message_line2,
                            fill=(150, 0, 0),
                            font=font
                        )
                    except Exception as text_e:
                        # Fallback if text drawing fails (e.g., font issues)
                        logger.warning(f"Failed to draw text on placeholder {placeholder_name}: {text_e}. Saving blank.")


                    # Save the placeholder
                    img.save(target_path)

                    logger.debug(f"Created text-based placeholder image: {target_path}")

            except ImportError:
                 logger.warning(f"Pillow not installed. Cannot create or copy placeholder images. Please install it (`pip install Pillow`).")
                 break # Stop trying to create placeholders if Pillow is missing
            except Exception as e:
                logger.warning(f"Failed to create or copy placeholder image {placeholder_name} from {source_path}: {e}")


def process_single_file(pdf_path: str) -> Dict:
    """Process a single PDF file."""
    # Normalize path
    pdf_path = os.path.normpath(pdf_path)

    # Determine the target path
    # Ensure the source_dir is an absolute path for reliable relpath
    abs_pdf_source_dir = os.path.abspath(settings.PDF_SOURCE_DIR)
    abs_pdf_path = os.path.abspath(pdf_path)

    # Handle cases where the file is not strictly within PDF_SOURCE_DIR
    try:
        rel_path = os.path.relpath(abs_pdf_path, abs_pdf_source_dir)
        target_path = os.path.join(settings.MARKDOWN_TARGET_DIR, rel_path)
    except ValueError:
        # If on different drives or otherwise not relative, just use the basename
        logger.warning(f"PDF path {pdf_path} is not relative to PDF_SOURCE_DIR {settings.PDF_SOURCE_DIR}. Using basename for target.")
        target_filename = os.path.basename(pdf_path)
        target_path = os.path.join(settings.MARKDOWN_TARGET_DIR, target_filename)


    # Process the file
    success = transform_pdf_to_markdown(pdf_path, target_path)

    return {
        'success_count': 1 if success else 0,
        'failure_count': 0 if success else 1,
        'failures': [] if success else [pdf_path]
    }


def process_directory(directory_path: str) -> Dict:
    """Process all PDF files in a directory and its subdirectories."""
    # Normalize path
    directory_path = os.path.normpath(directory_path)

    # Determine the source and target base directories for mirroring
    # Ensure both paths are absolute for reliable commonpath
    abs_directory_path = os.path.abspath(directory_path)
    abs_pdf_source_dir = os.path.abspath(settings.PDF_SOURCE_DIR)


    common = os.path.commonpath([abs_directory_path, abs_pdf_source_dir])

    if common == abs_pdf_source_dir:
        # The directory is within the source directory structure
        rel_path_from_source = os.path.relpath(abs_directory_path, abs_pdf_source_dir)
        source_dir_to_walk = directory_path # Walk starting from the specified directory
        target_base_dir_for_mirroring = os.path.join(settings.MARKDOWN_TARGET_DIR, rel_path_from_source) # Mirror relative structure under target
        logger.info(f"Processing directory within source structure: {source_dir_to_walk}")
        logger.info(f"Mirroring to target base: {target_base_dir_for_mirroring}")

    else:
        # The directory is outside the defined source directory.
        # Treat the specified directory as the base source and mirror directly under the target root.
        source_dir_to_walk = directory_path
        target_base_dir_for_mirroring = settings.MARKDOWN_TARGET_DIR
        logger.warning(f"Directory {directory_path} is outside PDF_SOURCE_DIR {settings.PDF_SOURCE_DIR}.")
        logger.info(f"Processing directory as base: {source_dir_to_walk}")
        logger.info(f"Mirroring to target base: {target_base_dir_for_mirroring}")


    # Mirror the directory structure and transform files
    # Use the source_dir_to_walk as the base for relpath inside mirror_directory_structure
    results = FileWriter.mirror_directory_structure(
        source_dir_to_walk,
        target_base_dir_for_mirroring,
        transform_func=transform_pdf_to_markdown,
        source_base_for_relpath=source_dir_to_walk # Tell mirror func the base for relative path calculations
    )

    return results


def process_batch(batch_id=None):
    """
    Process a batch of PDF files.

    Args:
        batch_id: Optional batch ID to filter by

    Returns:
        Results dictionary with counts
    """
    # This is a placeholder for future batch processing based on the tracking spreadsheet
    # For now, if batch_id is None or "ALL", process all files in the source directory.
    # If a specific batch_id is given, this would ideally filter files based on metadata/tracking.
    # For the current scope, if a batch_id is provided, assume it maps to a directory name or similar logic.
    logger.info(f"Processing batch: {batch_id or 'ALL'}")

    if batch_id and batch_id.upper() != 'ALL':
         # Placeholder logic: assume batch_id is a subdirectory name within PDF_SOURCE_DIR
         batch_directory = os.path.join(settings.PDF_SOURCE_DIR, batch_id)
         if os.path.isdir(batch_directory):
             logger.info(f"Attempting to process directory for batch ID: {batch_directory}")
             return process_directory(batch_directory)
         else:
             logger.error(f"Directory not found for batch ID: {batch_id} at {batch_directory}")
             return {'success_count': 0, 'failure_count': 0, 'failures': []}
    else:
        # Process the entire source directory if no specific batch ID or 'ALL' is specified
        return process_directory(settings.PDF_SOURCE_DIR)


def validate_image_extraction():
    """Validate that image extraction dependencies are properly installed."""
    try:
        import fitz  # PyMuPDF
        # Pillow is needed for Image processing and placeholder creation
        from PIL import Image, ImageDraw, ImageFont # Import Image specifically here
        logger.info("Image extraction dependencies (PyMuPDF, Pillow) are properly installed.")
        return True
    except ImportError as e:
        logger.warning(f"Image extraction dependency missing: {e}")
        logger.warning("Please install: pip install PyMuPDF Pillow")
        return False
    except Exception as e:
        # Catch any other unexpected errors during import check
        logger.warning(f"An unexpected error occurred while checking image extraction dependencies: {e}")
        return False


def main():
    """Main entry point for the extraction script."""
    parser = argparse.ArgumentParser(description='Extract Rise PDF content to markdown with images.')
    parser.add_argument('--file', help='Single PDF file to process')
    parser.add_argument('--dir', help='Directory containing PDF files to process')
    parser.add_argument('--course', help='Course ID to process (e.g., CON0001). Looks for directory starting with this ID in PDF_SOURCE_DIR.')
    parser.add_argument('--module', help='Module ID to process (e.g., MOD0001). Looks for subdirectory starting with this ID within PDF_SOURCE_DIR.')
    parser.add_argument('--batch', help='Batch ID to process. Currently assumes batch ID is a subdirectory name in PDF_SOURCE_DIR, or "ALL" for the whole directory.')
    parser.add_argument('--all', action='store_true', help='Process all PDF files in the configured PDF_SOURCE_DIR')
    parser.add_argument('--check-deps', action='store_true', help='Check if all dependencies are installed')
    parser.add_argument('--create-placeholders', action='store_true', help='Create or update placeholder images in the assets directory')
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set the logging level (default: INFO).")


    args = parser.parse_args()

    # Set logging level dynamically after parsing args but before significant work
    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {args.log_level}')
    logging.getLogger().setLevel(numeric_level)
    logger.info(f"Logging level set to {args.log_level}")

    # Check dependencies if requested
    if args.check_deps:
        if validate_image_extraction():
            print("All image extraction dependencies are properly installed.")
        else:
            print("Image extraction dependencies are missing. Please check the logs.")
        # Check other dependencies if needed (e.g., Pillow might be needed even if PyMuPDF isn't for some tasks)
        try:
            from PIL import Image # Check Pillow specifically as it's used in placeholders
            print("Pillow library is installed.")
        except ImportError:
             print("Pillow library is not installed. `pip install Pillow` is recommended.")
        return

    # Create placeholder images if requested
    if args.create_placeholders:
        placeholder_dir = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')
        os.makedirs(placeholder_dir, exist_ok=True)
        logger.info(f"Creating/updating placeholder images in {placeholder_dir}")
        create_placeholder_images(placeholder_dir) # This function handles creation/copying
        print(f"Completed creating/updating placeholder images in {placeholder_dir}")
        return

    # Validate image extraction capabilities
    # This check is now non-blocking, just logs a warning
    if not validate_image_extraction():
        logger.warning("Image extraction functionality may be limited due to missing dependencies.")

    # Track the time taken
    start_time = datetime.now()

    # Initialize results
    results = {
        'success_count': 0,
        'failure_count': 0,
        'failures': [] # List of file paths that failed
    }

    # Determine which processing method to use
    if args.file:
        # Process a single file
        results = process_single_file(args.file)
    elif args.dir:
        # Process a directory
        results = process_directory(args.dir)
    elif args.course:
        # Process a course directory (looks for directory starting with course ID)
        course_dir = None
        try:
            # Search only in the top level of PDF_SOURCE_DIR for course directories
            for item in os.listdir(settings.PDF_SOURCE_DIR):
                item_path = os.path.join(settings.PDF_SOURCE_DIR, item)
                if os.path.isdir(item_path) and item.lower().startswith(args.course.lower()):
                    course_dir = item_path
                    break
        except FileNotFoundError:
             logger.error(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
             results['failures'].append(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
             results['failure_count'] += 1


        if course_dir:
            logger.info(f"Processing course directory: {args.course} ({course_dir})")
            results = process_directory(course_dir)
        else:
            logger.error(f"Course directory not found starting with: {args.course} within {settings.PDF_SOURCE_DIR}")
            results['failures'].append(f"Course directory not found: {args.course}")
            results['failure_count'] += 1

    elif args.module:
        # Process a module directory (looks for subdirectory starting with module ID anywhere under PDF_SOURCE_DIR)
        module_dir = None
        try:
            for root, dirs, files in os.walk(settings.PDF_SOURCE_DIR):
                for d in dirs:
                    if d.lower().startswith(args.module.lower()):
                        module_dir = os.path.join(root, d)
                        break
                if module_dir:
                    break # Stop walking once found
        except FileNotFoundError:
             logger.error(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
             results['failures'].append(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
             results['failure_count'] += 1


        if module_dir:
            logger.info(f"Processing module directory: {args.module} ({module_dir})")
            results = process_directory(module_dir)
        else:
            logger.error(f"Module directory not found starting with: {args.module} under {settings.PDF_SOURCE_DIR}")
            results['failures'].append(f"Module directory not found: {args.module}")
            results['failure_count'] += 1

    elif args.batch:
        # Process a batch
        results = process_batch(args.batch) # process_batch handles lookup/logging
    elif args.all:
        # Process all
        logger.info(f"Processing all PDF files in {settings.PDF_SOURCE_DIR}")
        results = process_directory(settings.PDF_SOURCE_DIR)
    else:
        # No option specified
        logger.error("No processing option specified. Use --help for available options.")
        parser.print_help()
        sys.exit(1) # Exit with error code


    # Calculate elapsed time
    elapsed_time = datetime.now() - start_time

    # Log the final summary
    logger.info(f"--- Processing Summary ---")
    logger.info(f"Processing complete in {elapsed_time}")
    logger.info(f"Total files processed: {results['success_count'] + results['failure_count']}")
    logger.info(f"Successfully transformed: {results['success_count']}")
    logger.info(f"Failed transformations: {results['failure_count']}")

    if results['failure_count'] > 0:
        logger.warning("Failed files:")
        for failure in results['failures']:
            logger.warning(f"  - {failure}")

    logger.info(f"Detailed log saved to: {log_filename}")
    logger.info("Image extraction reports (if any issues) are saved alongside the markdown files in their respective '-img-assets' folders.")
    logger.info("------------------------")


    # Exit with a non-zero code if there were failures
    if results['failure_count'] > 0:
         sys.exit(1)
    else:
         sys.exit(0)


if __name__ == "__main__":
    import sys
    main()