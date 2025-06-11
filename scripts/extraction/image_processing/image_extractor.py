# scripts/extraction/image_extractor.py

"""Module for extracting images from PDF files."""

import os
import logging
import fitz  # PyMuPDF
from typing import Dict, List, Any

# Import refactored components
from ...config import settings
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
# --- NEW IMPORTS ---
from .image_analyser import ImageAnalyser
from .image_filter import ImageFilter

logger = logging.getLogger(__name__)

class ImageExtractor:
    """
    Handles image extraction from PDF files using a strategy pattern,
    retry coordination, and dedicated image processing/reporting.
    """

    def __init__(self):
        """Initialize the ImageExtractor with configuration settings and components."""
        self.config = settings.IMAGE_EXTRACTION_CONFIG

        self.strategies: List[StrategyTuple] = [
            (StandardExtractionStrategy, 'standard'),
            (AlternateColorspaceExtractionStrategy, 'alternate_colorspace'),
            (CompressionRetryStrategy, 'compression_retry'),
            (PageBasedExtractionStrategy, 'page_based'),
        ]
        self.retry_coordinator = RetryCoordinator(self.strategies, self.config)
        self.image_processor = ImageProcessor(self.config)
        self.reporter = ExtractionReporter(self.config)
        
        # --- NEW ---
        self.image_analyser = ImageAnalyser()
        self.image_filter = ImageFilter(settings.IMAGE_FILTER_CONFIG)

    def extract_images_from_pdf(self, pdf_path: str, output_dir: str) -> Dict[str, Any]:
        """
        Extract all images from a PDF file and save them to the specified directory.
        """
        self.reporter.start_document_report(pdf_path)

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            error_msg = f"Failed to create output directory {output_dir}: {str(e)}"
            logger.error(error_msg)
            self.reporter.errors.append(error_msg)
            return self.reporter.finalize_report(output_dir)

        pdf_document = None
        try:
            pdf_document = fitz.open(pdf_path)
            image_counter = 0

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                image_list = page.get_images(full=True)

                # --- MODIFIED EXTRACTION LOOP ---
                for img_index, img_info in enumerate(image_list):
                    self.reporter.track_image_attempt(img_info)

                    extracted_image, extraction_info = self.retry_coordinator.coordinate_extraction(
                        pdf_document,
                        img_info,
                        page_num + 1,
                        img_index,
                        {'global_image_counter': image_counter + 1}
                    )

                    if extracted_image is not None and extraction_info.get('success', False):
                        analysis_result = self.image_analyser.analyse_image(extracted_image)
                        should_keep, filter_reason = self.image_filter.should_keep_image(analysis_result)
                        
                        if should_keep:
                            image_counter += 1
                            image_filename = f"fig{image_counter}-page{page_num + 1}-img{img_index + 1}.{self.image_processor.image_format}"
                            image_path = os.path.join(output_dir, image_filename)
                            
                            processing_result = self.image_processor.process_and_save_image(
                                extracted_image,
                                image_path
                            )
                            self.reporter.track_extraction_result(extraction_info, processing_result, analysis_result)
                        else:
                            self.reporter.track_filtered_image(filter_reason, analysis_result)
                            processing_result = {
                                'success': False, 
                                'issue': filter_reason, 
                                'issue_type': 'filtered_by_analyser',
                                'filtered': True
                            }
                            self.reporter.track_extraction_result(extraction_info, processing_result)

                        extracted_image.close()
                        del extracted_image
                        
                    else:
                        processing_result = {
                            'success': False,
                            'issue': 'Extraction failed, skipping processing.',
                            'issue_type': 'processing_skipped_extraction_failed'
                        }
                        self.reporter.track_extraction_result(extraction_info, processing_result)

            if pdf_document:
                pdf_document.close()

        except fitz.FileNotFoundError:
            error_msg = f"PDF file not found: {pdf_path}"
            logger.error(error_msg)
            self.reporter.errors.append(error_msg)
            self.reporter.failed_count += self.reporter.metrics.get("total_images_in_doc", 0)

        except Exception as e:
            error_msg = f"An unexpected error occurred while processing {pdf_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.reporter.errors.append(error_msg)
            if pdf_document and not pdf_document.is_closed:
                 try:
                     pdf_document.close()
                 except Exception:
                     pass

        finally:
            return self.reporter.finalize_report(output_dir)