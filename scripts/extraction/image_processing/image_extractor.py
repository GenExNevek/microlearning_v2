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
    
    Enhanced with diagnostic mode capability to analyse all images and provide
    detailed filtering diagnostics.
    """

    def __init__(self, diagnostic_mode: bool = None):
        """
        Initialize the ImageExtractor with configuration settings and components.
        
        Args:
            diagnostic_mode: Override for diagnostic mode. If None, uses config setting.
        """
        self.config = settings.IMAGE_EXTRACTION_CONFIG
        self.filter_config = settings.IMAGE_FILTER_CONFIG
        
        # Determine diagnostic mode from parameter or configuration
        if diagnostic_mode is not None:
            self.diagnostic_mode = diagnostic_mode
        else:
            self.diagnostic_mode = (
                self.config.get('diagnostic_mode_enabled', False) or 
                self.filter_config.get('DIAGNOSTIC_MODE_ENABLED', False)
            )

        self.strategies: List[StrategyTuple] = [
            (StandardExtractionStrategy, 'standard'),
            (AlternateColorspaceExtractionStrategy, 'alternate_colorspace'),
            (CompressionRetryStrategy, 'compression_retry'),
            (PageBasedExtractionStrategy, 'page_based'),
        ]
        self.retry_coordinator = RetryCoordinator(self.strategies, self.config)
        self.image_processor = ImageProcessor(self.config)
        self.reporter = ExtractionReporter(self.config)
        
        # Initialize image analysis and filtering components
        self.image_analyser = ImageAnalyser()
        self.image_filter = ImageFilter(self.filter_config, diagnostic_mode=self.diagnostic_mode)

    def extract_images_from_pdf(self, pdf_path: str, output_dir: str, diagnostic_mode: bool = None) -> Dict[str, Any]:
        """
        Extract all images from a PDF file and save them to the specified directory.
        
        Args:
            pdf_path: Path to the PDF file to process
            output_dir: Directory where extracted images should be saved
            diagnostic_mode: Override diagnostic mode for this extraction
            
        Returns:
            Dictionary containing extraction results and diagnostic information
        """
        # Override diagnostic mode if specified for this extraction
        if diagnostic_mode is not None:
            current_diagnostic_mode = diagnostic_mode
            if diagnostic_mode != self.diagnostic_mode:
                self.image_filter.diagnostic_mode = diagnostic_mode
        else:
            current_diagnostic_mode = self.diagnostic_mode
        
        self.reporter.start_document_report(pdf_path)
        
        # Log diagnostic mode status
        if current_diagnostic_mode:
            logger.info("=" * 80)
            logger.info("🔍 RUNNING IN DIAGNOSTIC MODE: ALL IMAGES WILL BE EXTRACTED")
            logger.info("🔍 Filter analysis will be performed but images won't be discarded")
            logger.info("🔍 Check the extraction report for detailed filtering diagnostics")
            logger.info("=" * 80)

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

                for img_index, img_info in enumerate(image_list):
                    self.reporter.track_image_attempt(img_info)

                    # Attempt extraction using retry coordinator
                    extracted_image, extraction_info = self.retry_coordinator.coordinate_extraction(
                        pdf_document,
                        img_info,
                        page_num + 1,
                        img_index,
                        {'global_image_counter': image_counter + 1}
                    )
                    
                    image_counter += 1
                    image_filename = f"fig{image_counter}-page{page_num + 1}-img{img_index + 1}.{self.image_processor.image_format}"
                    image_path = os.path.join(output_dir, image_filename)

                    if extracted_image is not None and extraction_info.get('success', False):
                        # Analyse the extracted image
                        analysis_result = self.image_analyser.analyse_image(extracted_image)
                        
                        # Apply filter logic (in diagnostic mode, this provides reasons but doesn't filter)
                        should_keep, filter_reason = self.image_filter.should_keep_image(analysis_result)
                        
                        # Log diagnostic information
                        if current_diagnostic_mode:
                            diagnostic_log_level = self.config.get('diagnostic_log_level', 'INFO').upper()
                            log_message = f"DIAGNOSTIC - Image '{image_filename}': {filter_reason}"
                            
                            if diagnostic_log_level == 'DEBUG':
                                logger.debug(log_message)
                            elif diagnostic_log_level == 'WARNING':
                                logger.warning(log_message)
                            else:  # INFO or default
                                logger.info(log_message)
                        else:
                            # Normal mode: respect filter decision
                            if not should_keep:
                                logger.debug(f"Image filtered: {filter_reason}")
                                # Track the filtered image and continue to next image
                                self.reporter.track_filtered_image(filter_reason, analysis_result)
                                extracted_image.close()
                                del extracted_image
                                continue
                            else:
                                logger.debug(f"Image kept: {filter_reason}")
                        
                        # Process and save the image (in diagnostic mode, all images are saved)
                        processing_result = self.image_processor.process_and_save_image(
                            extracted_image,
                            image_path
                        )
                        
                        # Track the extraction result with diagnostic information
                        self.reporter.track_extraction_result(
                            extraction_info, 
                            processing_result, 
                            analysis_result, 
                            diagnostic_reason=filter_reason if current_diagnostic_mode else None
                        )

                        extracted_image.close()
                        del extracted_image
                        
                    else:
                        # Extraction failed
                        error_msg = f"DIAGNOSTIC - Failed to extract image: page {page_num+1}, index {img_index}. Info: {extraction_info.get('final_error', 'Unknown error')}"
                        if current_diagnostic_mode:
                            logger.info(error_msg)
                        else:
                            logger.error(error_msg)
                            
                        processing_result = {
                            'success': False,
                            'issue': 'Extraction failed, skipping processing.',
                            'issue_type': 'processing_skipped_extraction_failed'
                        }
                        self.reporter.track_extraction_result(
                            extraction_info, 
                            processing_result,
                            diagnostic_reason=f"[EXTRACTION FAILED] {extraction_info.get('final_error', 'Unknown error')}" if current_diagnostic_mode else None
                        )

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
            # Reset diagnostic mode if it was overridden for this extraction
            if diagnostic_mode is not None and diagnostic_mode != self.diagnostic_mode:
                self.image_filter.diagnostic_mode = self.diagnostic_mode
                
            final_report = self.reporter.finalize_report(output_dir)
            
            # Add diagnostic mode information to the final report
            final_report['diagnostic_mode_enabled'] = current_diagnostic_mode
            if current_diagnostic_mode:
                logger.info("🔍 DIAGNOSTIC MODE COMPLETE - Check the extraction report for detailed analysis")
            
            return final_report

    def enable_diagnostic_mode(self):
        """Enable diagnostic mode for this extractor instance."""
        self.diagnostic_mode = True
        self.image_filter.enable_diagnostic_mode()
    
    def disable_diagnostic_mode(self):
        """Disable diagnostic mode for this extractor instance."""
        self.diagnostic_mode = False
        self.image_filter.disable_diagnostic_mode()
    
    def is_diagnostic_mode_enabled(self) -> bool:
        """Check if diagnostic mode is currently enabled."""
        return self.diagnostic_mode