"""Main script for orchestrating the PDF to markdown extraction pipeline."""

import os
import argparse
import logging
import shutil
from datetime import datetime
from .pdf_reader import PDFReader
from .markdown_formatter import MarkdownFormatter
from .file_writer import FileWriter
from .image_extractor import ImageExtractor, generate_extraction_report
from ..config import settings

# Configure logging
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


def transform_pdf_to_markdown(source_file, target_file):
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
        return False
        
    # Change file extension from .pdf to .md
    target_file = target_file.replace('.pdf', '.md')
    
    # Get directories
    target_dir = os.path.dirname(target_file)
    
    # Create the directory if it doesn't exist
    os.makedirs(target_dir, exist_ok=True)
    
    # Process the PDF file
    reader = PDFReader()
    formatter = MarkdownFormatter(reader)
    
    try:
        # Read the PDF
        pdf_info = reader.read_pdf_from_path(source_file)
        
        # Extract metadata from the path
        metadata = formatter.extract_metadata_from_path(source_file)
        
        # Extract and format the content (this now includes image extraction)
        result = formatter.extract_and_format(pdf_info, metadata)
        
        if result['success']:
            # Write the markdown file
            FileWriter.write_markdown_file(result['content'], target_file)
            
            # Create image assets folder (already created during extraction, but ensure it exists)
            img_assets_folder = FileWriter.create_image_assets_folder(target_file)
            
            # Process image extraction results - write report directly to img_assets_folder
            has_image_issues = process_image_extraction_results(
                result.get('image_extraction', {}),
                source_file, 
                target_file,
                img_assets_folder
            )
            
            # Log the results
            logger.info(f"Transformed: {source_file} -> {target_file}")
            
            # Log image extraction results if available
            if 'image_extraction' in result:
                img_count = result['image_extraction'].get('extracted_count', 0)
                failed_count = result['image_extraction'].get('failed_count', 0)
                validation_failures = result['image_extraction'].get('validation_failures', 0)
                
                if failed_count > 0 or validation_failures > 0:
                    logger.warning(
                        f"Image extraction issues: {img_count} extracted, "
                        f"{failed_count} failed, {validation_failures} validation issues"
                    )
                else:
                    logger.info(f"Extracted {img_count} images to: {img_assets_folder}")
                
                # Log any extraction errors
                if result['image_extraction'].get('errors'):
                    for error in result['image_extraction']['errors']:
                        logger.warning(f"Image extraction warning: {error}")
            
            return True
        else:
            logger.error(f"Error transforming {source_file}: {result.get('error', 'Unknown error')}")
            
            # Log image extraction errors if any
            if 'image_extraction' in result and result['image_extraction'].get('errors'):
                for error in result['image_extraction']['errors']:
                    logger.error(f"Image extraction error: {error}")
            
            return False
            
    except Exception as e:
        logger.error(f"Exception processing {source_file}: {str(e)}")
        return False


def process_image_extraction_results(extraction_results, source_file, target_file, img_assets_folder):
    """
    Process image extraction results and generate a single diagnostic report in the img-assets folder.
    
    Args:
        extraction_results: Results from image extraction
        source_file: Source PDF file path
        target_file: Target markdown file path
        img_assets_folder: Image assets folder path
        
    Returns:
        Boolean indicating whether there were issues with image extraction
    """
    # Check if we have results
    if not extraction_results:
        logger.warning(f"No image extraction results for {source_file}")
        return False
    
    # Get counts
    extracted_count = extraction_results.get('extracted_count', 0)
    failed_count = extraction_results.get('failed_count', 0)
    validation_failures = extraction_results.get('validation_failures', 0)
    problematic_count = len(extraction_results.get('problematic_images', []))
    
    # Create placeholder images if needed
    if problematic_count > 0:
        create_placeholder_images(img_assets_folder)
    
    # Determine if there were issues
    has_issues = failed_count > 0 or validation_failures > 0 or problematic_count > 0
    
    # Generate a single diagnostic report if there were issues
    if has_issues:
        # Add source and target file info
        extraction_results['source_file'] = source_file
        extraction_results['target_file'] = target_file
        
        # Generate report directly in the img_assets_folder with a consistent name
        report_path = os.path.join(img_assets_folder, "image_extraction_report.md")
        
        # Generate the report content (don't save to file in the function)
        report = generate_extraction_report(extraction_results, None)  
        
        # Write the report content ourselves to the img-assets folder
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report['report_text'])
        
        logger.warning(f"Generated image extraction report: {report_path}")
    
    return has_issues


def create_placeholder_images(img_assets_folder):
    """
    Create or copy placeholder images for different issue types.
    
    Args:
        img_assets_folder: Folder to place placeholder images
    """
    # Define placeholder types and source files
    placeholders = {
        'placeholder-blank.png': os.path.join(settings.BASE_DIR, 'assets', 'placeholders', 'blank-image.png'),
        'placeholder-corrupt.png': os.path.join(settings.BASE_DIR, 'assets', 'placeholders', 'corrupt-image.png'),
        'placeholder-error.png': os.path.join(settings.BASE_DIR, 'assets', 'placeholders', 'error-image.png')
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
                else:
                    # Create a simple text-based placeholder image
                    from PIL import Image, ImageDraw, ImageFont
                    img = Image.new('RGB', (400, 300), color=(240, 240, 240))
                    d = ImageDraw.Draw(img)
                    
                    # Try to use a system font, fallback to default
                    try:
                        font = ImageFont.truetype("Arial", 20)
                    except:
                        font = ImageFont.load_default()
                    
                    issue_type = placeholder_name.replace('placeholder-', '').replace('.png', '')
                    message = f"Image Extraction Issue: {issue_type.upper()}"
                    
                    # Add text to the image
                    text_width = d.textlength(message, font=font)
                    d.text(
                        ((400 - text_width) / 2, 140),
                        message,
                        fill=(200, 0, 0),
                        font=font
                    )
                    
                    # Save the placeholder
                    img.save(target_path)
                    
                logger.debug(f"Created placeholder image: {target_path}")
            except Exception as e:
                logger.warning(f"Failed to create placeholder image {placeholder_name}: {e}")


def process_single_file(pdf_path):
    """Process a single PDF file."""
    # Normalize path
    pdf_path = os.path.normpath(pdf_path)
    
    # Determine the target path
    rel_path = os.path.relpath(pdf_path, settings.PDF_SOURCE_DIR)
    target_path = os.path.join(settings.MARKDOWN_TARGET_DIR, rel_path)
    
    # Process the file
    success = transform_pdf_to_markdown(pdf_path, target_path)
    
    return {
        'success_count': 1 if success else 0,
        'failure_count': 0 if success else 1,
        'failures': [] if success else [pdf_path]
    }


def process_directory(directory_path):
    """Process all PDF files in a directory and its subdirectories."""
    # Normalize path
    directory_path = os.path.normpath(directory_path)
    
    # Determine the source and target base directories
    if os.path.commonpath([directory_path, settings.PDF_SOURCE_DIR]) == settings.PDF_SOURCE_DIR:
        # Directory is within the source directory
        rel_path = os.path.relpath(directory_path, settings.PDF_SOURCE_DIR)
        source_dir = directory_path
        target_dir = os.path.join(settings.MARKDOWN_TARGET_DIR, rel_path)
    else:
        # Directory is outside the source directory - use it directly
        source_dir = directory_path
        target_dir = settings.MARKDOWN_TARGET_DIR
    
    # Mirror the directory structure and transform files
    logger.info(f"Processing directory: {source_dir}")
    logger.info(f"Target directory: {target_dir}")
    
    results = FileWriter.mirror_directory_structure(
        source_dir, 
        target_dir,
        transform_func=transform_pdf_to_markdown
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
    # For now, just process all files
    logger.info(f"Processing batch: {batch_id or 'ALL'}")
    
    return process_directory(settings.PDF_SOURCE_DIR)


def validate_image_extraction():
    """Validate that image extraction dependencies are properly installed."""
    try:
        import fitz  # PyMuPDF
        from PIL import Image, ImageDraw, ImageFont
        logger.info("Image extraction dependencies are properly installed")
        return True
    except ImportError as e:
        logger.warning(f"Image extraction dependency missing: {e}")
        logger.warning("Please install: pip install PyMuPDF Pillow")
        return False


def main():
    """Main entry point for the extraction script."""
    parser = argparse.ArgumentParser(description='Extract Rise PDF content to markdown with images.')
    parser.add_argument('--file', help='Single PDF file to process')
    parser.add_argument('--dir', help='Directory containing PDF files to process')
    parser.add_argument('--course', help='Course ID to process (e.g., CON0001)')
    parser.add_argument('--module', help='Module ID to process (e.g., MOD0001)')
    parser.add_argument('--batch', help='Batch ID to process')
    parser.add_argument('--all', action='store_true', help='Process all PDF files')
    parser.add_argument('--check-deps', action='store_true', help='Check if all dependencies are installed')
    parser.add_argument('--create-placeholders', action='store_true', help='Create or update placeholder images')
    args = parser.parse_args()
    
    # Check dependencies if requested
    if args.check_deps:
        if validate_image_extraction():
            print("All dependencies are properly installed.")
        else:
            print("Some dependencies are missing. Please check the logs.")
        return
    
    # Create placeholder images if requested
    if args.create_placeholders:
        placeholder_dir = os.path.join(settings.BASE_DIR, 'assets', 'placeholders')
        os.makedirs(placeholder_dir, exist_ok=True)
        create_placeholder_images(placeholder_dir)
        print(f"Created placeholder images in {placeholder_dir}")
        return
    
    # Validate image extraction capabilities
    if not validate_image_extraction():
        logger.warning("Image extraction may not work properly due to missing dependencies")
    
    # Track the time taken
    start_time = datetime.now()
    
    # Initialize results
    results = {
        'success_count': 0,
        'failure_count': 0,
        'failures': []
    }
    
    # Determine which processing method to use
    if args.file:
        # Process a single file
        logger.info(f"Processing single file: {args.file}")
        results = process_single_file(args.file)
    elif args.dir:
        # Process a directory
        logger.info(f"Processing directory: {args.dir}")
        results = process_directory(args.dir)
    elif args.course:
        # Process a course
        course_dir = None
        for item in os.listdir(settings.PDF_SOURCE_DIR):
            if item.startswith(args.course):
                course_dir = os.path.join(settings.PDF_SOURCE_DIR, item)
                break
        
        if course_dir:
            logger.info(f"Processing course: {args.course} ({course_dir})")
            results = process_directory(course_dir)
        else:
            logger.error(f"Course directory not found for: {args.course}")
    elif args.module:
        # Process a module
        module_dir = None
        for root, dirs, files in os.walk(settings.PDF_SOURCE_DIR):
            for d in dirs:
                if d.startswith(args.module):
                    module_dir = os.path.join(root, d)
                    break
            if module_dir:
                break
        
        if module_dir:
            logger.info(f"Processing module: {args.module} ({module_dir})")
            results = process_directory(module_dir)
        else:
            logger.error(f"Module directory not found for: {args.module}")
    elif args.batch:
        # Process a batch
        logger.info(f"Processing batch: {args.batch}")
        results = process_batch(args.batch)
    elif args.all:
        # Process all
        logger.info("Processing all PDF files with image extraction")
        results = process_directory(settings.PDF_SOURCE_DIR)
    else:
        # No option specified
        logger.error("No processing option specified. Use --help for available options.")
        return
    
    # Calculate elapsed time
    elapsed_time = datetime.now() - start_time
    
    # Log the results
    logger.info(f"Processing complete in {elapsed_time}")
    logger.info(f"Successes: {results['success_count']}")
    logger.info(f"Failures: {results['failure_count']}")
    
    if results['failure_count'] > 0:
        logger.info("Failed files:")
        for failure in results['failures']:
            logger.info(f"  - {failure}")
    
    logger.info("Use --check-deps to verify all dependencies are installed correctly.")
    logger.info(f"Extraction log saved to: {log_filename}")


if __name__ == "__main__":
    main()