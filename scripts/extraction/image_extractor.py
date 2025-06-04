"""Module for extracting images from PDF files."""

import os
import logging
import fitz  # PyMuPDF
from PIL import Image
import io
import time
from typing import Dict, List, Optional, Tuple, Any
from ..config import settings
from ..utils.image_validation import ImageValidator, ImageValidationResult, ImageIssueType

logger = logging.getLogger(__name__)

class ImageExtractor:
    """Handles image extraction from PDF files."""
    
    def __init__(self):
        """Initialize the ImageExtractor with configuration settings."""
        self.config = settings.IMAGE_EXTRACTION_CONFIG
        self.dpi = self.config.get("dpi", 150)
        self.image_format = self.config.get("image_format", "png")
        self.quality = self.config.get("quality", 95)
        self.max_width = self.config.get("max_width", 1920)
        self.max_height = self.config.get("max_height", 1080)
        self.min_width = self.config.get("min_width", 50)
        self.min_height = self.config.get("min_height", 50)
        self.supported_formats = self.config.get("supported_formats", ["png", "jpg", "jpeg"])
        
        # Configure validator with same thresholds
        self.validator = ImageValidator(
            min_width=self.min_width,
            min_height=self.min_height,
            supported_formats=self.supported_formats
        )
        
        # Enable more detailed error tracking
        self.track_extraction_attempts = True
        self.validation_enabled = self.config.get("validate_images", True)
        self.retry_extraction = self.config.get("retry_failed_extractions", True)
        self.max_retries = self.config.get("max_extraction_retries", 3)
        
        # Tracking for detailed reporting
        self.extraction_metrics = {
            "total_attempts": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "validation_failures": 0,
            "retry_successes": 0,
            "issue_types": {issue_type.value: 0 for issue_type in ImageIssueType}
        }
    
    def extract_images_from_pdf(self, pdf_path: str, output_dir: str) -> Dict[str, Any]:
        """
        Extract all images from a PDF file and save them to the specified directory.
        
        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory where images will be saved
            
        Returns:
            Dictionary containing extraction results
        """
        # Reset extraction metrics for this document
        self._reset_extraction_metrics()
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Track results
        results = {
            'success': True,
            'extracted_count': 0,
            'failed_count': 0,
            'validation_failures': 0,
            'images': [],
            'errors': [],
            'problematic_images': [],
            'extraction_metrics': {},
            'start_time': time.time(),
            'pdf_path': pdf_path
        }
        
        try:
            # Open the PDF
            pdf_document = fitz.open(pdf_path)
            image_counter = 0
            
            # Iterate through all pages
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                
                # Get images list for this page
                image_list = page.get_images(full=True)
                
                for img_index, img in enumerate(image_list):
                    extraction_attempt = {
                        'pdf_path': pdf_path,
                        'page_num': page_num + 1,
                        'img_index': img_index,
                        'xref': img[0],
                        'retries': 0,
                        'status': 'pending'
                    }
                    
                    self.extraction_metrics['total_attempts'] += 1
                    
                    try:
                        # Extract image with retry logic
                        image_counter += 1
                        extracted_image, extraction_info = self._extract_single_image_with_retry(
                            pdf_document, 
                            img, 
                            page_num + 1,
                            image_counter,
                            extraction_attempt
                        )
                        
                        if extracted_image:
                            # Save the image
                            image_filename = f"fig{image_counter}-page{page_num + 1}-img{img_index + 1}.{self.image_format}"
                            image_path = os.path.join(output_dir, image_filename)
                            
                            save_result = self._save_and_validate_image(extracted_image, image_path)
                            
                            if save_result['success']:
                                # Successfully saved and validated
                                results['extracted_count'] += 1
                                self.extraction_metrics['successful_extractions'] += 1
                                
                                results['images'].append({
                                    'filename': image_filename,
                                    'path': image_path,
                                    'page': page_num + 1,
                                    'index': img_index + 1,
                                    'extraction_info': extraction_info,
                                    'validation_info': save_result.get('validation_info', {})
                                })
                                
                                logger.info(f"Extracted image: {image_filename}")
                                extraction_attempt['status'] = 'success'
                            else:
                                # Image saved but failed validation
                                results['validation_failures'] += 1
                                self.extraction_metrics['validation_failures'] += 1
                                
                                # Track the issue type
                                issue_type = save_result.get('issue_type')
                                if issue_type:
                                    self.extraction_metrics['issue_types'][issue_type] += 1
                                
                                results['problematic_images'].append({
                                    'filename': image_filename,
                                    'path': image_path,
                                    'page': page_num + 1,
                                    'index': img_index + 1,
                                    'issue': save_result.get('issue', 'Unknown validation issue'),
                                    'issue_type': issue_type,
                                    'extraction_info': extraction_info,
                                    'validation_info': save_result.get('validation_info', {})
                                })
                                
                                error_msg = f"Image validation failed for {image_filename}: {save_result.get('issue')}"
                                logger.warning(error_msg)
                                results['errors'].append(error_msg)
                                extraction_attempt['status'] = 'validation_failed'
                        else:
                            # Failed to extract image
                            results['failed_count'] += 1
                            self.extraction_metrics['failed_extractions'] += 1
                            
                            # Track problematic image
                            results['problematic_images'].append({
                                'page': page_num + 1,
                                'index': img_index + 1,
                                'issue': extraction_info.get('error', 'Unknown extraction issue'),
                                'issue_type': extraction_info.get('issue_type', 'extraction_failed'),
                                'extraction_info': extraction_info
                            })
                            
                            error_msg = f"Failed to extract image {img_index + 1} from page {page_num + 1}: {extraction_info.get('error', 'Unknown issue')}"
                            logger.error(error_msg)
                            results['errors'].append(error_msg)
                            extraction_attempt['status'] = 'extraction_failed'
                    
                    except Exception as e:
                        error_msg = f"Exception extracting image {img_index + 1} from page {page_num + 1}: {str(e)}"
                        logger.error(error_msg)
                        results['failed_count'] += 1
                        self.extraction_metrics['failed_extractions'] += 1
                        results['errors'].append(error_msg)
                        extraction_attempt['status'] = 'error'
                        extraction_attempt['error'] = str(e)
            
            pdf_document.close()
            
        except Exception as e:
            error_msg = f"Failed to process PDF {pdf_path}: {str(e)}"
            logger.error(error_msg)
            results['success'] = False
            results['errors'].append(error_msg)
        
        # Calculate elapsed time
        results['elapsed_time'] = time.time() - results['start_time']
        
        # Include detailed extraction metrics
        results['extraction_metrics'] = self.extraction_metrics.copy()
        
        # Determine overall success based on failure ratio
        if results['failed_count'] > 0:
            total_images = results['extracted_count'] + results['failed_count']
            failure_ratio = results['failed_count'] / total_images if total_images > 0 else 0
            
            # If more than 25% of images failed, mark as problematic
            if failure_ratio > 0.25:
                results['success'] = False
                results['failure_ratio'] = failure_ratio
        
        # Log summary
        success_status = "SUCCESSFUL" if results['success'] else "PROBLEMATIC"
        logger.info(f"Image extraction {success_status} for {pdf_path}: "
                   f"{results['extracted_count']} extracted, "
                   f"{results['failed_count']} failed, "
                   f"{results['validation_failures']} validation issues")
        
        return results
    
    def _reset_extraction_metrics(self):
        """Reset extraction metrics for a new document."""
        self.extraction_metrics = {
            "total_attempts": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "validation_failures": 0,
            "retry_successes": 0,
            "issue_types": {issue_type.value: 0 for issue_type in ImageIssueType}
        }
    
    def _extract_single_image_with_retry(
        self, 
        pdf_document, 
        img_info: Tuple, 
        page_num: int, 
        image_counter: int,
        extraction_attempt: Dict
    ) -> Tuple[Optional[Image.Image], Dict]:
        """
        Extract a single image from PDF with retry logic.
        
        Args:
            pdf_document: PyMuPDF document object
            img_info: Image information tuple
            page_num: Page number (1-indexed)
            image_counter: Global image counter
            extraction_attempt: Dictionary tracking extraction attempt details
            
        Returns:
            Tuple of (PIL Image object or None if extraction failed, extraction info dict)
        """
        extraction_info = {
            'xref': img_info[0],
            'page': page_num,
            'attempt_count': 0,
            'extraction_method': 'standard'
        }
        
        # Initial standard extraction attempt
        extracted_image = self._try_standard_extraction(pdf_document, img_info, extraction_info)
        extraction_attempt['retries'] += 1
        extraction_info['attempt_count'] += 1
        
        # If standard extraction failed and retries are enabled, try alternative methods
        if extracted_image is None and self.retry_extraction:
            # Try alternative extraction methods with multiple retries
            for retry in range(self.max_retries):
                if retry == 0:
                    # Try pixmap extraction with different colorspace
                    extraction_info['extraction_method'] = 'pixmap_alternate_colorspace'
                    extracted_image = self._try_pixmap_alternate_colorspace(pdf_document, img_info, extraction_info)
                elif retry == 1:
                    # Try extracting with different compression parameters
                    extraction_info['extraction_method'] = 'alternate_compression'
                    extracted_image = self._try_alternate_compression(pdf_document, img_info, extraction_info)
                else:
                    # Try page-based extraction as last resort
                    extraction_info['extraction_method'] = 'page_based'
                    extracted_image = self._try_page_based_extraction(pdf_document, page_num-1, img_info, extraction_info)
                
                extraction_attempt['retries'] += 1
                extraction_info['attempt_count'] += 1
                
                # If successful, update metrics and break
                if extracted_image is not None:
                    self.extraction_metrics['retry_successes'] += 1
                    extraction_info['success'] = True
                    break
        
        # Set final extraction status
        if extracted_image is not None:
            extraction_info['success'] = True
            extraction_info['dimensions'] = f"{extracted_image.width}x{extracted_image.height}"
            extraction_info['mode'] = extracted_image.mode
        else:
            extraction_info['success'] = False
            extraction_info['error'] = "All extraction methods failed"
            extraction_info['issue_type'] = "extraction_failed"
        
        return extracted_image, extraction_info
    
    def _try_standard_extraction(self, pdf_document, img_info: Tuple, extraction_info: Dict) -> Optional[Image.Image]:
        """Standard extraction method using PyMuPDF's Pixmap."""
        try:
            # Get the XREF of the image
            xref = img_info[0]
            
            # Extract the image
            pix = fitz.Pixmap(pdf_document, xref)
            
            if pix.n - pix.alpha < 4:  # GRAY or RGB
                pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            else:  # CMYK
                pil_image = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
                pil_image = pil_image.convert("RGB")
            
            pix = None  # free memory
            
            # Check minimum size requirements
            if pil_image.width < self.min_width or pil_image.height < self.min_height:
                extraction_info['error'] = f"Image too small: {pil_image.width}x{pil_image.height}"
                extraction_info['issue_type'] = "size_issues"
                return None
            
            return pil_image
            
        except Exception as e:
            extraction_info['error'] = f"Standard extraction failed: {str(e)}"
            return None
    
    def _try_pixmap_alternate_colorspace(self, pdf_document, img_info: Tuple, extraction_info: Dict) -> Optional[Image.Image]:
        """Try extraction with different colorspace settings."""
        try:
            xref = img_info[0]
            
            # Try with explicit colorspace conversion
            pix = fitz.Pixmap(pdf_document, xref)
            
            # Force conversion to RGB
            if pix.colorspace:  # If there's a colorspace, convert to RGB
                pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                pil_image = Image.frombytes("RGB", [pix_rgb.width, pix_rgb.height], pix_rgb.samples)
                pix_rgb = None  # free memory
            else:
                # Grayscale or another format
                pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            pix = None  # free memory
            
            # Check minimum size requirements
            if pil_image.width < self.min_width or pil_image.height < self.min_height:
                extraction_info['error'] = f"Image too small: {pil_image.width}x{pil_image.height}"
                extraction_info['issue_type'] = "size_issues"
                return None
            
            return pil_image
            
        except Exception as e:
            extraction_info['error'] = f"Alternate colorspace extraction failed: {str(e)}"
            return None
    
    def _try_alternate_compression(self, pdf_document, img_info: Tuple, extraction_info: Dict) -> Optional[Image.Image]:
        """Try extraction with different compression parameters."""
        try:
            xref = img_info[0]
            
            # Try extracting raw image data then reconstructing
            img_dict = pdf_document.extract_image(xref)
            
            if img_dict:
                img_bytes = img_dict["image"]
                img_ext = img_dict["ext"]
                
                # Try to create PIL image from raw bytes
                pil_image = Image.open(io.BytesIO(img_bytes))
                pil_image.load()  # Load image data
                
                # Convert to RGB if needed
                if pil_image.mode not in ["RGB", "RGBA"]:
                    pil_image = pil_image.convert("RGB")
                
                # Check minimum size requirements
                if pil_image.width < self.min_width or pil_image.height < self.min_height:
                    extraction_info['error'] = f"Image too small: {pil_image.width}x{pil_image.height}"
                    extraction_info['issue_type'] = "size_issues"
                    return None
                
                return pil_image
            else:
                extraction_info['error'] = "No image data in extract_image result"
                return None
                
        except Exception as e:
            extraction_info['error'] = f"Alternate compression extraction failed: {str(e)}"
            return None
    
    def _try_page_based_extraction(
        self, 
        pdf_document, 
        page_idx: int, 
        img_info: Tuple, 
        extraction_info: Dict
    ) -> Optional[Image.Image]:
        """
        Last resort: render page as image and attempt to extract relevant portion.
        This is much less precise but can sometimes recover otherwise lost images.
        """
        try:
            # Get the page
            page = pdf_document[page_idx]
            
            # Render page to pixmap at high resolution
            zoom_factor = 2.0  # Higher resolution for better quality
            matrix = fitz.Matrix(zoom_factor, zoom_factor)
            pix = page.get_pixmap(matrix=matrix)
            
            # Convert to PIL Image
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Here we would ideally extract just the portion containing our image
            # But without positional data, we'll just use the whole page
            # This is imprecise but better than nothing as a last resort
            
            extraction_info['warning'] = "Used whole page rendering as fallback; image may contain surrounding content"
            
            return pil_image
            
        except Exception as e:
            extraction_info['error'] = f"Page-based extraction failed: {str(e)}"
            return None
    
    def _save_and_validate_image(self, image: Image.Image, path: str) -> Dict:
        """
        Save image to disk and validate it.
        
        Args:
            image: PIL Image object
            path: Path to save the image
            
        Returns:
            Dictionary with save and validation results
        """
        result = {
            'success': False,
            'path': path
        }
        
        try:
            # Resize if needed while maintaining aspect ratio
            if self.config.get("maintain_aspect_ratio", True):
                image = self._resize_image(image)
            
            # Save the image
            self._save_image(image, path)
            
            # Validate the saved image if validation is enabled
            if self.validation_enabled:
                validation_result = self.validator.validate_image_file(path)
                
                if validation_result.is_valid:
                    result['success'] = True
                    result['validation_info'] = validation_result.metrics
                else:
                    result['success'] = False
                    result['issue'] = validation_result.details
                    result['issue_type'] = validation_result.issue_type.value if validation_result.issue_type else "unknown"
                    result['validation_info'] = validation_result.metrics
            else:
                # Skip validation
                result['success'] = True
        
        except Exception as e:
            result['success'] = False
            result['issue'] = f"Failed to save or validate image: {str(e)}"
            result['issue_type'] = "save_error"
        
        return result
    
    def _resize_image(self, image: Image.Image) -> Image.Image:
        """
        Resize image if it exceeds maximum dimensions while maintaining aspect ratio.
        
        Args:
            image: PIL Image object
            
        Returns:
            Resized PIL Image object
        """
        width, height = image.size
        
        # Calculate scaling factor
        scale_factor = min(
            self.max_width / width if width > self.max_width else 1,
            self.max_height / height if height > self.max_height else 1
        )
        
        if scale_factor < 1:
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height), Image.LANCZOS)
            logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")
        
        return image
    
    def _save_image(self, image: Image.Image, path: str):
        """
        Save PIL Image to file.
        
        Args:
            image: PIL Image object
            path: Output file path
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Save with appropriate quality
        save_kwargs = {}
        if self.image_format.lower() in ['jpg', 'jpeg']:
            save_kwargs['quality'] = self.quality
            save_kwargs['optimize'] = True
        elif self.image_format.lower() == 'png':
            save_kwargs['compress_level'] = 9
        
        image.save(path, format=self.image_format.upper(), **save_kwargs)
        logger.debug(f"Saved image to: {path}")


# Function to generate diagnostic report for problematic images
def generate_extraction_report(
    extraction_results: Dict,
    output_dir: Optional[str] = None
) -> Dict:
    """
    Generate a comprehensive diagnostic report for problematic images.
    
    Args:
        extraction_results: Results from ImageExtractor.extract_images_from_pdf
        output_dir: Optional directory to save report to (None to skip saving to file)
        
    Returns:
        Dictionary with report summary including report text
    """
    summary = {
        "total_images": extraction_results.get("extracted_count", 0) + extraction_results.get("failed_count", 0),
        "extracted_count": extraction_results.get("extracted_count", 0),
        "failed_count": extraction_results.get("failed_count", 0),
        "validation_failures": extraction_results.get("validation_failures", 0),
        "problematic_count": len(extraction_results.get("problematic_images", [])),
        "metrics": extraction_results.get("extraction_metrics", {}),
        "pdf_path": extraction_results.get("pdf_path", "unknown"),
        "timestamp": time.time()
    }
    
    # Get most common issue types
    issue_types = {}
    for img in extraction_results.get("problematic_images", []):
        issue_type = img.get("issue_type", "unknown")
        issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    
    summary["issue_types"] = issue_types
    
    # Generate report string
    report = [
        f"# Image Extraction Diagnostic Report",
        f"PDF: {summary['pdf_path']}",
        f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## Summary",
        f"- Total images: {summary['total_images']}",
        f"- Successfully extracted: {summary['extracted_count']}",
        f"- Failed to extract: {summary['failed_count']}",
        f"- Validation failures: {summary['validation_failures']}",
        f"- Total problematic images: {summary['problematic_count']}",
        f"",
        f"## Issue Breakdown"
    ]
    
    for issue_type, count in issue_types.items():
        report.append(f"- {issue_type}: {count}")
    
    report.append("")
    report.append("## Problematic Images")
    
    # Add details for each problematic image
    for i, img in enumerate(extraction_results.get("problematic_images", [])):
        report.append(f"### Image {i+1}")
        report.append(f"- **Page**: {img.get('page', 'unknown')}")
        report.append(f"- **Index**: {img.get('index', 'unknown')}")
        report.append(f"- **Issue**: {img.get('issue', 'unknown')}")
        report.append(f"- **Issue Type**: {img.get('issue_type', 'unknown')}")
        
        if "extraction_info" in img:
            report.append(f"- **Extraction Method**: {img['extraction_info'].get('extraction_method', 'unknown')}")
            report.append(f"- **Attempts**: {img['extraction_info'].get('attempt_count', 0)}")
        
        if "validation_info" in img:
            report.append(f"- **Validation Details**: {img['validation_info']}")
        
        report.append("")
    
    summary["report_text"] = "\n".join(report)
    
    # Save report to file ONLY if output_dir is provided
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, f"extraction_report_{int(time.time())}.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(summary["report_text"])
        
        summary["report_path"] = report_path
    
    return summary