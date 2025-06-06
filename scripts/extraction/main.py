# scripts/extraction/main.py

"""Main script for orchestrating the PDF to markdown extraction pipeline."""

import os
import argparse
import logging
import shutil
import sys # Added for sys.exit
from typing import Dict, List # Added List
from datetime import datetime

from .pdf_reader import PDFReader
from .markdown_formatter import MarkdownFormatter
from .file_writer import FileWriter
# ImageExtractor is used by MarkdownFormatter, not directly here usually.
# from .image_extractor import ImageExtractor # Not directly needed here if formatter handles it
from ..config import settings
from ..utils.image_validation import ImageIssueType # For placeholder logic

# Configure logging
log_filename = f"extraction_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
# Basic config is set globally, but handlers can be adjusted if needed.
# The provided main.py already had this structure.
logging.basicConfig(
    level=logging.INFO, # Default, will be overridden by args
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # Added %(name)s
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
    if not source_file.lower().endswith('.pdf'):
        logger.info(f"Skipping non-PDF file: {source_file}")
        return False

    target_file = target_file.replace('.pdf', '.md').replace('.PDF', '.md')
    target_dir = os.path.dirname(target_file)

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create target directory {target_dir}: {e}")
        return False

    reader = PDFReader()
    formatter = MarkdownFormatter(reader) # MarkdownFormatter initializes ImageExtractor

    logger.info(f"Starting transformation: {source_file} -> {target_file}")

    try:
        pdf_info = reader.read_pdf_from_path(source_file)
        if pdf_info.get('error'):
            logger.error(f"Failed to read PDF {source_file}: {pdf_info['error']}")
            return False

        metadata = formatter.extract_metadata_from_path(source_file)
        
        # extract_and_format now returns the image_extraction_results (the report dict)
        result = formatter.extract_and_format(pdf_info, metadata)

        image_extraction_results = result.get('image_extraction', {})

        if result['success']:
            FileWriter.write_markdown_file(result['content'], target_file)
            
            # Image assets folder is created by ImageExtractor/reporter or by _get_image_assets_dir
            # We need the path for placeholder creation.
            # The report from ImageExtractor should contain the output_dir or report_path.
            img_assets_folder_disk_path = None
            if image_extraction_results and image_extraction_results.get('report_path'):
                 img_assets_folder_disk_path = os.path.dirname(image_extraction_results['report_path'])
            elif image_extraction_results and image_extraction_results.get('output_dir'): # Ideal key
                 img_assets_folder_disk_path = image_extraction_results['output_dir']
            else: # Fallback: reconstruct using formatter's logic (less ideal but a backup)
                 logger.warning("Could not determine image assets folder from extraction report, reconstructing.")
                 img_assets_folder_disk_path = formatter._get_image_assets_dir(source_file, metadata)

            if img_assets_folder_disk_path:
                # This function now primarily handles placeholder creation based on issues.
                # The report itself is saved by the ExtractionReporter component.
                process_image_extraction_issues(
                    image_extraction_results,
                    img_assets_folder_disk_path # Pass the actual disk path
                )
            else:
                logger.warning(f"Could not determine image assets folder for {source_file}. Skipping placeholder creation.")


            logger.info(f"Transformed: {source_file} -> {target_file}")

            # Log image extraction summary from the report
            # Using keys from ExtractionReporter's output
            extracted_ok = image_extraction_results.get('extracted_count', 0)
            failed_processing_or_extraction = image_extraction_results.get('failed_count', 0)
            problematic_reported = image_extraction_results.get('problematic_count', len(image_extraction_results.get('problematic_images',[])))
            report_file_path = image_extraction_results.get('report_path')

            if failed_processing_or_extraction > 0 or problematic_reported > 0:
                logger.warning(
                    f"Image extraction for {source_file}: "
                    f"{extracted_ok} extracted successfully, "
                    f"{failed_processing_or_extraction} failed extraction/processing/validation, "
                    f"{problematic_reported} images reported as problematic."
                )
                if report_file_path:
                    logger.warning(f"Detailed image extraction report: {report_file_path}")
                # Log specific errors from the report if any
                for err_msg in image_extraction_results.get('errors', []):
                    logger.error(f"Image extraction top-level error for {source_file}: {err_msg}")
            else:
                logger.info(f"Image extraction for {source_file}: {extracted_ok} images extracted successfully.")
                if report_file_path: # Log path even on full success
                    logger.info(f"Image extraction report: {report_file_path}")
            
            return True
        else:
            logger.error(f"Error transforming {source_file}: {result.get('error', 'Unknown error')}")
            # Log image extraction issues even if main transformation failed
            if image_extraction_results:
                for err_msg in image_extraction_results.get('errors', []):
                    logger.error(f"Image extraction top-level error for {source_file} (during failed transform): {err_msg}")
                if image_extraction_results.get('problematic_images'):
                    logger.error(f"Problematic image details for {source_file} (during failed transform):")
                    for p_img in image_extraction_results['problematic_images']:
                        logger.error(f"  - Page {p_img.get('page','?')}, Index {p_img.get('index_on_page','?')}: {p_img.get('issue_type','unknown')} - {p_img.get('issue','no details')}")
            return False

    except Exception as e:
        logger.error(f"Unhandled exception processing {source_file}: {str(e)}", exc_info=True)
        return False


def process_image_extraction_issues(extraction_results: Dict, img_assets_folder_disk_path: str):
    """
    Check for issues in image extraction results and create placeholder images if needed.
    The report generation itself is handled by the ImageExtractor's reporter component.

    Args:
        extraction_results: Results dictionary from ImageExtractor (via formatter).
        img_assets_folder_disk_path: Actual disk path to the image assets folder.
    """
    # Check if we have results and problematic images
    # 'failed_count' in the report means images that didn't make it through the pipeline successfully
    # 'problematic_images' list contains details on those that failed or had validation issues
    
    # We need to create placeholders if any image that *should* have been extracted
    # ended up being problematic (e.g. blank, corrupt, or failed extraction).
    # The markdown formatter will try to link to these placeholders.
    
    # If there are problematic images, ensure placeholders are available.
    if extraction_results.get('problematic_images') or extraction_results.get('failed_count', 0) > 0:
        logger.info(f"Image extraction issues detected for associated PDF. Ensuring placeholders in {img_assets_folder_disk_path}")
        create_placeholder_images(img_assets_folder_disk_path)
    else:
        logger.debug(f"No problematic images reported for associated PDF. Placeholder check skipped for {img_assets_folder_disk_path}")


def create_placeholder_images(img_assets_folder_disk_path: str):
    """
    Create or copy placeholder images for different issue types into the specified assets folder.
    Args:
        img_assets_folder_disk_path: Folder to place placeholder images.
    """
    base_asset_path = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')
    os.makedirs(base_asset_path, exist_ok=True) # Ensure source placeholder dir exists
    os.makedirs(img_assets_folder_disk_path, exist_ok=True) # Ensure target assets dir exists

    placeholders_to_create = {
        'placeholder-blank.png': "Blank Image",
        'placeholder-corrupt.png': "Corrupt Image",
        'placeholder-error.png': "Extraction Error", # Generic error
        # Add more if ImageIssueType has more specific placeholders
    }

    for placeholder_filename, message_text in placeholders_to_create.items():
        target_placeholder_path = os.path.join(img_assets_folder_disk_path, placeholder_filename)
        source_placeholder_path = os.path.join(base_asset_path, placeholder_filename)

        if os.path.exists(target_placeholder_path):
            # logger.debug(f"Placeholder {placeholder_filename} already exists in {img_assets_folder_disk_path}")
            continue

        if os.path.exists(source_placeholder_path):
            try:
                shutil.copy2(source_placeholder_path, target_placeholder_path)
                logger.debug(f"Copied placeholder {source_placeholder_path} to {target_placeholder_path}")
                continue
            except Exception as e:
                logger.warning(f"Failed to copy placeholder {source_placeholder_path} to {target_placeholder_path}: {e}. Will try to generate.")
        
        # If source doesn't exist or copy failed, generate a new one
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (300, 200), color=(220, 220, 220))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 15)
            except IOError:
                font = ImageFont.load_default()
            
            text_bbox = draw.textbbox((0,0), message_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            x = (img.width - text_width) / 2
            y = (img.height - text_height) / 2
            draw.text((x, y), message_text, fill=(0, 0, 0), font=font)
            img.save(target_placeholder_path)
            logger.debug(f"Generated placeholder image: {target_placeholder_path}")
        except ImportError:
            logger.error("Pillow not installed. Cannot generate placeholder images. Please install `Pillow`.")
            break # Stop trying if Pillow is missing
        except Exception as e:
            logger.error(f"Failed to generate placeholder image {target_placeholder_path}: {e}")


def process_single_file(pdf_path: str) -> Dict:
    """Process a single PDF file."""
    pdf_path = os.path.normpath(pdf_path)
    abs_pdf_source_dir = os.path.abspath(settings.PDF_SOURCE_DIR)
    abs_pdf_path = os.path.abspath(pdf_path)

    try:
        if abs_pdf_path.startswith(abs_pdf_source_dir):
            rel_path = os.path.relpath(abs_pdf_path, abs_pdf_source_dir)
        else: # File is outside the standard source dir
            logger.warning(f"PDF path {pdf_path} is not relative to PDF_SOURCE_DIR {settings.PDF_SOURCE_DIR}. Using basename for target.")
            # Place it in a subfolder named after the PDF's original parent directory to avoid flat structure
            pdf_parent_dir_name = os.path.basename(os.path.dirname(abs_pdf_path))
            if not pdf_parent_dir_name: pdf_parent_dir_name = "_external_pdfs" # Fallback
            rel_path = os.path.join(pdf_parent_dir_name, os.path.basename(pdf_path))
        
        target_path = os.path.join(settings.MARKDOWN_TARGET_DIR, rel_path)
    except ValueError: # Catches issues like different drives on Windows for relpath
        target_filename = os.path.basename(pdf_path)
        target_path = os.path.join(settings.MARKDOWN_TARGET_DIR, "_external_pdfs", target_filename)

    success = transform_pdf_to_markdown(pdf_path, target_path)
    return {
        'success_count': 1 if success else 0,
        'failure_count': 0 if success else 1,
        'failures': [] if success else [pdf_path]
    }

def process_directory(directory_path: str) -> Dict:
    """Process all PDF files in a directory and its subdirectories."""
    directory_path = os.path.normpath(directory_path)
    abs_directory_path = os.path.abspath(directory_path)
    abs_pdf_source_dir = os.path.abspath(settings.PDF_SOURCE_DIR)

    source_dir_to_walk = abs_directory_path
    
    # Determine target base for mirroring
    if abs_directory_path.startswith(abs_pdf_source_dir):
        rel_subdir = os.path.relpath(abs_directory_path, abs_pdf_source_dir)
        target_base_dir_for_mirroring = os.path.join(settings.MARKDOWN_TARGET_DIR, rel_subdir)
    else: # Directory to process is outside the main PDF_SOURCE_DIR
        # Mirror its structure directly under MARKDOWN_TARGET_DIR, perhaps in a subdir named after the input dir
        dir_name = os.path.basename(abs_directory_path)
        target_base_dir_for_mirroring = os.path.join(settings.MARKDOWN_TARGET_DIR, dir_name)
        logger.warning(f"Directory {directory_path} is outside PDF_SOURCE_DIR. Mirroring to {target_base_dir_for_mirroring}")

    logger.info(f"Processing directory: {source_dir_to_walk}")
    logger.info(f"Mirroring to target base: {target_base_dir_for_mirroring}")

    return FileWriter.mirror_directory_structure(
        source_dir_to_walk,
        target_base_dir_for_mirroring,
        transform_func=transform_pdf_to_markdown,
        source_base_for_relpath=source_dir_to_walk 
    )

def process_batch(batch_id=None):
    """Process a batch of PDF files."""
    logger.info(f"Processing batch: {batch_id or 'ALL'}")
    if batch_id and batch_id.upper() != 'ALL':
         batch_directory = os.path.join(settings.PDF_SOURCE_DIR, batch_id)
         if os.path.isdir(batch_directory):
             logger.info(f"Processing directory for batch ID: {batch_directory}")
             return process_directory(batch_directory)
         else:
             logger.error(f"Directory not found for batch ID: {batch_id} at {batch_directory}")
             return {'success_count': 0, 'failure_count': 0, 'failures': [f"Batch directory {batch_directory} not found"]}
    else:
        return process_directory(settings.PDF_SOURCE_DIR)

def validate_dependencies(): # Renamed for clarity
    """Validate that critical dependencies are properly installed."""
    deps_ok = True
    try:
        import fitz
        logger.debug("PyMuPDF (fitz) is installed.")
    except ImportError:
        logger.error("PyMuPDF (fitz) is NOT installed. `pip install PyMuPDF`")
        deps_ok = False
    try:
        from PIL import Image
        logger.debug("Pillow (PIL) is installed.")
    except ImportError:
        logger.error("Pillow (PIL) is NOT installed. `pip install Pillow`")
        deps_ok = False
    try:
        import google.generativeai
        logger.debug("Google Generative AI (google-generativeai) is installed.")
    except ImportError:
        logger.error("Google Generative AI (google-generativeai) is NOT installed. `pip install google-generativeai`")
        deps_ok = False
    # Add other critical dependency checks here (e.g., tenacity, PyYAML)
    try:
        import yaml
        logger.debug("PyYAML is installed.")
    except ImportError:
        logger.warning("PyYAML is NOT installed. `pip install PyYAML` (needed for frontmatter parsing if LLM provides it)")
        # Not strictly critical for core if LLM doesn't use YAML frontmatter, but good to have.
    try:
        import tenacity
        logger.debug("Tenacity is installed.")
    except ImportError:
        logger.warning("Tenacity is NOT installed. `pip install tenacity` (needed for robust API calls)")

    if deps_ok:
        logger.info("Core dependencies seem to be installed.")
    else:
        logger.error("One or more critical dependencies are missing. Please install them.")
    return deps_ok


def main():
    parser = argparse.ArgumentParser(description='Extract PDF content to markdown with images.')
    parser.add_argument('--file', help='Single PDF file to process')
    parser.add_argument('--dir', help='Directory containing PDF files to process')
    parser.add_argument('--course', help='Course ID to process (e.g., CON0001). Looks for directory starting with this ID in PDF_SOURCE_DIR.')
    parser.add_argument('--module', help='Module ID to process (e.g., MOD0001). Looks for subdirectory starting with this ID within PDF_SOURCE_DIR.')
    parser.add_argument('--batch', help='Batch ID to process. Assumes batch ID is a subdirectory name in PDF_SOURCE_DIR, or "ALL".')
    parser.add_argument('--all', action='store_true', help='Process all PDF files in the configured PDF_SOURCE_DIR')
    parser.add_argument('--check-deps', action='store_true', help='Check if all dependencies are installed and exit.')
    parser.add_argument('--create-placeholders', action='store_true', help='Create or update placeholder images in the global assets/placeholders directory and exit.')
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Set the logging level.")
    args = parser.parse_args()

    # Set logging level
    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        logging.getLogger().error(f'Invalid log level: {args.log_level}')
        sys.exit(1)
    logging.getLogger().setLevel(numeric_level)
    # Also set level for specific loggers if they were configured with a higher default
    logging.getLogger('scripts.extraction').setLevel(numeric_level)


    logger.info(f"Logging level set to {args.log_level.upper()}")


    if args.check_deps:
        if validate_dependencies():
            print("All checked dependencies appear to be installed.")
        else:
            print("Some dependencies are missing. Please check the log.")
        sys.exit(0)

    if args.create_placeholders:
        placeholder_dir = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')
        logger.info(f"Ensuring global placeholder images in {placeholder_dir}")
        create_placeholder_images(placeholder_dir) # This function handles creation/copying
        print(f"Global placeholder image task complete for {placeholder_dir}. Check logs for details.")
        sys.exit(0)

    if not validate_dependencies(): # Run check by default if not just checking deps
        logger.critical("Critical dependencies missing. Aborting.")
        sys.exit(1)

    start_time = datetime.now()
    results = {'success_count': 0, 'failure_count': 0, 'failures': []}
    processed_action = False

    if args.file:
        processed_action = True
        results = process_single_file(args.file)
    elif args.dir:
        processed_action = True
        results = process_directory(args.dir)
    elif args.course:
        processed_action = True
        course_dir_found = False
        # Simplified search: assumes course ID is a prefix of a directory in PDF_SOURCE_DIR
        try:
            for item in os.listdir(settings.PDF_SOURCE_DIR):
                item_path = os.path.join(settings.PDF_SOURCE_DIR, item)
                if os.path.isdir(item_path) and item.lower().startswith(args.course.lower()):
                    logger.info(f"Processing course directory: {item_path}")
                    results = process_directory(item_path)
                    course_dir_found = True
                    break
            if not course_dir_found:
                logger.error(f"Course directory starting with '{args.course}' not found in {settings.PDF_SOURCE_DIR}")
                results['failures'].append(f"Course directory for {args.course} not found.")
                results['failure_count'] = 1 # Count this as a failure to process the request
        except FileNotFoundError:
            logger.error(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
            results['failures'].append(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
            results['failure_count'] = 1
            
    elif args.module:
        processed_action = True
        module_dir_found = False
        try:
            for root, dirs, _ in os.walk(settings.PDF_SOURCE_DIR):
                for d_name in dirs:
                    if d_name.lower().startswith(args.module.lower()):
                        module_path = os.path.join(root, d_name)
                        logger.info(f"Processing module directory: {module_path}")
                        results = process_directory(module_path)
                        module_dir_found = True
                        break
                if module_dir_found: break
            if not module_dir_found:
                logger.error(f"Module directory starting with '{args.module}' not found under {settings.PDF_SOURCE_DIR}")
                results['failures'].append(f"Module directory for {args.module} not found.")
                results['failure_count'] = 1
        except FileNotFoundError:
            logger.error(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
            results['failures'].append(f"PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
            results['failure_count'] = 1

    elif args.batch:
        processed_action = True
        results = process_batch(args.batch)
    elif args.all:
        processed_action = True
        results = process_directory(settings.PDF_SOURCE_DIR)
    
    if not processed_action:
        logger.error("No processing option specified. Use --help for available options.")
        parser.print_help()
        sys.exit(1)

    elapsed_time = datetime.now() - start_time
    logger.info("--- Processing Summary ---")
    logger.info(f"Completed in {elapsed_time}")
    total_attempted = results['success_count'] + results['failure_count']
    # If a high-level operation like finding a course dir failed, success/failure counts might be low.
    # The 'failures' list will contain the reason.
    if total_attempted == 0 and results['failures']: # e.g. dir not found
         logger.info(f"No files processed. Reason: {results['failures'][0]}")
    else:
        logger.info(f"Total files/operations attempted: {total_attempted}")
        logger.info(f"Successful transformations: {results['success_count']}")
        logger.info(f"Failed transformations/operations: {results['failure_count']}")

    if results['failures']:
        logger.warning("Details of failures:")
        for failure_path_or_msg in results['failures']:
            logger.warning(f"  - {failure_path_or_msg}")
    logger.info(f"Detailed log: {log_filename}")
    logger.info("--- End of Summary ---")

    sys.exit(1 if results['failure_count'] > 0 or (not processed_action and not args.check_deps and not args.create_placeholders) else 0)

if __name__ == "__main__":
    main()