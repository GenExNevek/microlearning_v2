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
        Enhanced image extraction with consistent numbering and better metadata tracking.
        
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
        image_counter = 0
        extraction_metadata = {}

        try:
            pdf_document = fitz.open(pdf_path)
            
            # Track extraction metadata for better correlation
            extraction_metadata = {
                'total_pages': len(pdf_document),
                'images_per_page': {},
                'extraction_order': [],
            }

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                image_list = page.get_images(full=True)
                
                # Track images per page for metadata
                extraction_metadata['images_per_page'][page_num + 1] = len(image_list)
                logger.debug(f"Processing page {page_num + 1}: found {len(image_list)} images")

                # Enhanced extraction loop with consistent numbering
                for img_index, img_info in enumerate(image_list):
                    self.reporter.track_image_attempt(img_info)
                    
                    # Enhanced extraction metadata
                    extraction_context = {
                        'global_image_counter': image_counter + 1,  # Prospective counter
                        'page_number': page_num + 1,  # 1-indexed page number
                        'index_on_page': img_index,   # 0-indexed position on page
                        'total_images_on_page': len(image_list),
                    }

                    extracted_image, extraction_info = self.retry_coordinator.coordinate_extraction(
                        pdf_document,
                        img_info,
                        page_num + 1,  # Pass 1-indexed page number
                        img_index,     # Pass 0-indexed image position
                        extraction_context
                    )

                    if extracted_image is not None and extraction_info.get('success', False):
                        analysis_result = self.image_analyser.analyse_image(extracted_image)
                        should_keep, filter_reason = self.image_filter.should_keep_image(analysis_result)
                        
                        if should_keep or current_diagnostic_mode:
                            if current_diagnostic_mode and not should_keep:
                                logger.info(f"DIAGNOSTIC - Image on page {page_num + 1}, index {img_index + 1} would be filtered: {filter_reason}")
                            elif should_keep:
                                logger.debug(f"Image kept: {filter_reason}")

                            # Increment counter ONLY for kept/saved images
                            image_counter += 1
                            
                            # Consistent filename format: fig{counter}-page{page}-img{img_index+1}
                            image_filename = f"fig{image_counter}-page{page_num + 1}-img{img_index + 1}.{self.image_processor.image_format.lower()}"
                            output_path = os.path.join(output_dir, image_filename)
                            
                            # Enhanced metadata for correlation
                            enhanced_extraction_info = extraction_info.copy()
                            enhanced_extraction_info.update({
                                'figure_number': image_counter,
                                'display_page': page_num + 1,
                                'display_index': img_index + 1,
                                'filename': image_filename,
                                'relative_position': img_index / max(1, len(image_list) - 1) if len(image_list) > 1 else 0.5,
                            })
                            
                            processing_result = self.image_processor.process_and_save_image(
                                extracted_image, 
                                output_path
                            )
                            
                            # Track extraction order for sequential fallback
                            extraction_metadata['extraction_order'].append({
                                'figure_number': image_counter,
                                'page': page_num + 1,
                                'index': img_index + 1,
                                'filename': image_filename,
                                'success': processing_result.get('success', False),
                            })
                            
                            self.reporter.track_extraction_result(
                                enhanced_extraction_info, 
                                processing_result,
                                analysis_result,
                                diagnostic_reason=filter_reason if current_diagnostic_mode and not should_keep else None
                            )
                            
                            logger.info(f"Successfully extracted and saved: {image_filename}")
                            
                        else:
                            # Normal mode: track filtered images
                            logger.debug(f"Filtered image on page {page_num + 1}, index {img_index + 1}: {filter_reason}")
                            self.reporter.track_filtered_image(filter_reason, analysis_result)
                        
                        # Clean up image resource
                        if hasattr(extracted_image, 'close'):
                            extracted_image.close()
                        del extracted_image
                    else:
                        # Track failed extractions
                        error_detail = extraction_info.get('final_error', extraction_info.get('error', 'Unknown error'))
                        logger.warning(f"Failed to extract image on page {page_num + 1}, index {img_index + 1}: {error_detail}")
                        
                        failed_info = extraction_info.copy()
                        failed_info.update({
                            'page_display': page_num + 1,
                            'index_display': img_index + 1,
                        })
                        
                        processing_result = {
                            'success': False, 
                            'issue': f"Extraction failed: {error_detail}",
                            'issue_type': 'processing_skipped_extraction_failed'
                        }
                        self.reporter.track_extraction_result(
                            failed_info,
                            processing_result,
                            None, # No analysis result
                            diagnostic_reason=f"[EXTRACTION FAILED] {error_detail}" if current_diagnostic_mode else None
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
            
            # Add extraction and diagnostic metadata to the final report
            final_report['extraction_metadata'] = extraction_metadata
            final_report['diagnostic_mode_enabled'] = current_diagnostic_mode
            
            if not self.reporter.errors:
                logger.info(f"Image extraction complete: {image_counter} images successfully extracted from {len(pdf_document) if pdf_document else 'N/A'} pages")

            if current_diagnostic_mode:
                logger.info("🔍 DIAGNOSTIC MODE COMPLETE - Check the extraction report for detailed analysis")
            
            return final_report

    def _create_image_metadata(self, page_num: int, img_index: int, image_counter: int, 
                              extraction_info: Dict, analysis_result) -> Dict[str, Any]:
        """Create comprehensive metadata for extracted images to aid correlation."""
        
        return {
            'image_path': extraction_info.get('output_path'),
            'figure_number': image_counter,
            'page_number': page_num,  # 1-indexed
            'index_on_page': img_index + 1,  # 1-indexed for display
            'internal_index': img_index,  # 0-indexed for correlation
            'filename': os.path.basename(extraction_info.get('output_path', '')),
            'extraction_success': extraction_info.get('success', False),
            'analysis_score': getattr(analysis_result, 'complexity_score', 0) if hasattr(analysis_result, 'complexity_score') else 0,
            'content_type': getattr(analysis_result, 'detected_content_type', 'unknown') if hasattr(analysis_result, 'detected_content_type') else 'unknown',
            'dimensions': {
                'width': getattr(analysis_result, 'width', 0) if hasattr(analysis_result, 'width') else 0,
                'height': getattr(analysis_result, 'height', 0) if hasattr(analysis_result, 'height') else 0,
            },
            'processing_timestamp': extraction_info.get('timestamp'),
        }

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