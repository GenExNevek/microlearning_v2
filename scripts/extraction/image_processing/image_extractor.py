# scripts/extraction/image_extractor.py

"""Module for extracting images from PDF files."""

import os
import logging
import fitz  # PyMuPDF
import time
from typing import Dict, List, Optional, Tuple, Any

# Import refactored components
from ...config import settings
from ...utils.image_validation import ImageValidator, ImageIssueType # Keep for config check/init
from .extraction_strategies import (
    StandardExtractionStrategy,
    AlternateColorspaceExtractionStrategy,
    CompressionRetryStrategy,
    PageBasedExtractionStrategy,
    StrategyTuple
)
from .retry_coordinator import RetryCoordinator
from .image_processor import ImageProcessor
from .extraction_reporter import ExtractionReporter


logger = logging.getLogger(__name__)

class ImageExtractor:
    """
    Handles image extraction from PDF files using a strategy pattern,
    retry coordination, and dedicated image processing/reporting.
    """

    def __init__(self):
        """Initialize the ImageExtractor with configuration settings and components."""
        self.config = settings.IMAGE_EXTRACTION_CONFIG

        # Initialize sub-components with relevant parts of config
        # Strategies need min_width/height from config
        self.strategies: List[StrategyTuple] = [
            (StandardExtractionStrategy, 'standard'),
            (AlternateColorspaceExtractionStrategy, 'alternate_colorspace'),
            (CompressionRetryStrategy, 'compression_retry'),
            (PageBasedExtractionStrategy, 'page_based'), # This is a fallback, should be last
        ]
        self.retry_coordinator = RetryCoordinator(self.strategies, self.config)

        # ImageProcessor needs various save/process/validation settings
        self.image_processor = ImageProcessor(self.config)

        # Reporter needs validation issue types and report path config
        self.reporter = ExtractionReporter(self.config)

    def extract_images_from_pdf(self, pdf_path: str, output_dir: str) -> Dict[str, Any]:
        """
        Extract all images from a PDF file and save them to the specified directory.

        Orchestrates the extraction, processing, and reporting pipeline.

        Args:
            pdf_path: Path to the PDF file.
            output_dir: Directory where images will be saved.

        Returns:
            Dictionary containing extraction results summary.
        """
        # Start tracking for this document
        self.reporter.start_document_report(pdf_path)

        # Ensure output directory exists
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            error_msg = f"Failed to create output directory {output_dir}: {str(e)}"
            logger.error(error_msg)
            # Finalize report with this initial error and return
            self.reporter.errors.append(error_msg)
            return self.reporter.finalize_report(output_dir)


        pdf_document = None
        try:
            # Open the PDF
            pdf_document = fitz.open(pdf_path)
            image_counter = 0 # Global image counter for naming

            # Iterate through all pages
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]

                # Get images list for this page
                # full=True provides more details but can be slower
                # We rely on extract_image for some strategies which doesn't need full=True initially
                # Let's stick to full=True for consistent image listing
                image_list = page.get_images(full=True)

                for img_index, img_info in enumerate(image_list):
                    self.reporter.track_image_attempt(img_info) # Record an image was found

                    # Delegate extraction attempts and retries
                    extracted_image, extraction_info = self.retry_coordinator.coordinate_extraction(
                        pdf_document,
                        img_info,
                        page_num + 1, # Pass 1-indexed page num
                        img_index,    # Pass 0-indexed image index
                        {'global_image_counter': image_counter + 1} # Include global counter hint
                    )

                    # Prepare output path based on counter, page, and index
                    image_counter += 1
                    image_filename = f"fig{image_counter}-page{page_num + 1}-img{img_index + 1}.{self.image_processor.image_format}"
                    image_path = os.path.join(output_dir, image_filename)

                    processing_result = {
                        'success': False,
                        'issue': 'Extraction failed, skipping processing.',
                        'issue_type': 'processing_skipped_extraction_failed'
                    }

                    if extracted_image is not None and extraction_info.get('success', False):
                        # Delegate processing (resize, save, validate)
                        processing_result = self.image_processor.process_and_save_image(
                            extracted_image,
                            image_path
                        )
                        # Free image memory after processing/saving
                        extracted_image.close()
                        del extracted_image

                    # Track the final outcome in the report
                    self.reporter.track_extraction_result(extraction_info, processing_result)

            if pdf_document:
                pdf_document.close()

        except fitz.FileNotFoundError:
            error_msg = f"PDF file not found: {pdf_path}"
            logger.error(error_msg)
            self.reporter.errors.append(error_msg)
            self.reporter.failed_count += self.reporter.metrics["total_images_in_doc"] # Assume all failed if PDF open fails

        except Exception as e:
            error_msg = f"An unexpected error occurred while processing {pdf_path}: {str(e)}"
            logger.error(error_msg, exc_info=True) # Log traceback for unexpected errors
            self.reporter.errors.append(error_msg)
            # Attempt to finalize report even after exception
            if pdf_document and not pdf_document.is_closed:
                 try:
                     pdf_document.close()
                 except Exception:
                     pass # Ignore close errors during exception handling

        finally:
            # Finalize and return the report
            # Pass output_dir to reporter so it can save the report file
            return self.reporter.finalize_report(output_dir)


# Note: The generate_extraction_report function from the original file
# is effectively replaced by the functionality within ExtractionReporter.
# If it's needed as a public utility *outside* the class flow, it would
# need to be recreated or adjusted to work with the new report structure
# from ExtractionReporter.finalize_report().
# For now, let's assume the reporter handles report generation internally
# as part of the ImageExtractor flow. If markdown_formatter needs it,
# it will need to be updated to accept the reporter's output dict directly.