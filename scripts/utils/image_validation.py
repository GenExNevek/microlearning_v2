"""Utility module for validating extracted PDF images."""

import os
import logging
import time
from typing import Dict, List, Tuple, Optional, Union
from enum import Enum
import io
from PIL import Image, ImageStat, UnidentifiedImageError
import numpy as np

logger = logging.getLogger(__name__)

class ImageIssueType(Enum):
    """Enumeration of possible image extraction issues."""
    MISSING = "missing"               # Image wasn't extracted at all
    CORRUPT = "corrupt"               # Image data is corrupted
    LOW_QUALITY = "low_quality"       # Image has very low quality (blurry, etc.)
    BLANK = "blank"                   # Image appears to be blank/empty
    TRUNCATED = "truncated"           # Image data is incomplete
    SIZE_ISSUES = "size_issues"       # Image has unusual dimensions
    FORMAT_ISSUES = "format_issues"   # Image format problems
    OTHER = "other"                   # Other unclassified issues


class ImageValidationResult:
    """Container for image validation results."""
    
    def __init__(
        self,
        is_valid: bool,
        image_path: str,
        issue_type: Optional[ImageIssueType] = None,
        details: Optional[str] = None,
        metrics: Optional[Dict] = None
    ):
        """
        Initialize validation result.
        
        Args:
            is_valid: Whether the image is valid
            image_path: Path to the image file
            issue_type: Type of issue if not valid
            details: Description of the issue
            metrics: Additional metrics about the image
        """
        self.is_valid = is_valid
        self.image_path = image_path
        self.issue_type = issue_type
        self.details = details
        self.metrics = metrics or {}
        
    def to_dict(self) -> Dict:
        """Convert result to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "image_path": self.image_path,
            "issue_type": self.issue_type.value if self.issue_type else None,
            "details": self.details,
            "metrics": self.metrics
        }
    
    def __str__(self) -> str:
        """String representation of validation result."""
        if self.is_valid:
            return f"Valid image: {os.path.basename(self.image_path)}"
        else:
            return f"Invalid image: {os.path.basename(self.image_path)} - {self.issue_type.value if self.issue_type else 'unknown'}: {self.details}"


class ImageValidator:
    """Validates extracted images for quality and integrity."""
    
    def __init__(
        self,
        min_width: int = 50,
        min_height: int = 50,
        min_content_variance: float = 0.01,
        min_file_size: int = 1024,  # 1KB
        blank_threshold: float = 0.98,
        supported_formats: List[str] = None
    ):
        """
        Initialize the image validator with configurable thresholds.
        
        Args:
            min_width: Minimum acceptable width in pixels
            min_height: Minimum acceptable height in pixels
            min_content_variance: Minimum pixel variance (0-1) for non-blank images
            min_file_size: Minimum file size in bytes
            blank_threshold: Threshold for determining a blank image (0-1)
            supported_formats: List of supported image formats
        """
        self.min_width = min_width
        self.min_height = min_height
        self.min_content_variance = min_content_variance
        self.min_file_size = min_file_size
        self.blank_threshold = blank_threshold
        self.supported_formats = supported_formats or ["png", "jpg", "jpeg", "gif", "webp"]
    
    def validate_image_file(self, image_path: str) -> ImageValidationResult:
        """
        Validate an image file on disk.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ImageValidationResult object
        """
        # Check if file exists
        if not os.path.exists(image_path):
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.MISSING,
                details="Image file does not exist"
            )
        
        # Check file size
        file_size = os.path.getsize(image_path)
        if file_size < self.min_file_size:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.SIZE_ISSUES,
                details=f"File size too small: {file_size} bytes",
                metrics={"file_size": file_size}
            )
        
        # Check file extension
        ext = os.path.splitext(image_path)[1].lower().replace(".", "")
        if ext not in self.supported_formats:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.FORMAT_ISSUES,
                details=f"Unsupported format: {ext}",
                metrics={"format": ext}
            )
        
        # Try to open and validate the image
        try:
            with Image.open(image_path) as img:
                return self._validate_image(img, image_path)
        except UnidentifiedImageError:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.CORRUPT,
                details="Unidentified image format or corrupt data",
                metrics={"file_size": file_size}
            )
        except (IOError, OSError) as e:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.CORRUPT,
                details=f"IO error: {str(e)}",
                metrics={"file_size": file_size, "error": str(e)}
            )
        except Exception as e:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.OTHER,
                details=f"Validation error: {str(e)}",
                metrics={"file_size": file_size, "error": str(e)}
            )
    
    def validate_image_bytes(self, image_bytes: bytes, image_name: str = "unknown") -> ImageValidationResult:
        """
        Validate image from bytes without saving to disk.
        
        Args:
            image_bytes: Raw image data as bytes
            image_name: Name identifier for the image
            
        Returns:
            ImageValidationResult object
        """
        # Check if bytes are provided
        if not image_bytes:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_name,
                issue_type=ImageIssueType.MISSING,
                details="No image data provided"
            )
        
        # Check size of bytes
        if len(image_bytes) < self.min_file_size:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_name,
                issue_type=ImageIssueType.SIZE_ISSUES,
                details=f"Data size too small: {len(image_bytes)} bytes",
                metrics={"data_size": len(image_bytes)}
            )
        
        # Try to open and validate the image from bytes
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                return self._validate_image(img, image_name)
        except UnidentifiedImageError:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_name,
                issue_type=ImageIssueType.CORRUPT,
                details="Unidentified image format or corrupt data",
                metrics={"data_size": len(image_bytes)}
            )
        except (IOError, OSError) as e:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_name,
                issue_type=ImageIssueType.CORRUPT,
                details=f"IO error: {str(e)}",
                metrics={"data_size": len(image_bytes), "error": str(e)}
            )
        except Exception as e:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_name,
                issue_type=ImageIssueType.OTHER,
                details=f"Validation error: {str(e)}",
                metrics={"data_size": len(image_bytes), "error": str(e)}
            )
    
    def _validate_image(self, img: Image.Image, image_path: str) -> ImageValidationResult:
        """
        Perform validation checks on a PIL Image object.
        
        Args:
            img: PIL Image object
            image_path: Path or identifier for the image
            
        Returns:
            ImageValidationResult object
        """
        width, height = img.size
        metrics = {
            "width": width,
            "height": height,
            "format": img.format,
            "mode": img.mode
        }
        
        # Check dimensions
        if width < self.min_width or height < self.min_height:
            return ImageValidationResult(
                is_valid=False,
                image_path=image_path,
                issue_type=ImageIssueType.SIZE_ISSUES,
                details=f"Image too small: {width}x{height}",
                metrics=metrics
            )
        
        # Check if image is blank/mostly uniform
        try:
            # Convert to grayscale for simpler analysis
            if img.mode != "L":
                gray_img = img.convert("L")
            else:
                gray_img = img
                
            # Get image statistics
            stat = ImageStat.Stat(gray_img)
            metrics["mean"] = stat.mean[0]
            metrics["stddev"] = stat.stddev[0]
            
            # Calculate histogram for advanced blank detection
            hist = gray_img.histogram()
            hist_array = np.array(hist)
            total_pixels = width * height
            
            # Check if most pixels fall into a single bin (highly uniform image)
            max_bin = max(hist)
            max_bin_ratio = max_bin / total_pixels
            metrics["max_bin_ratio"] = max_bin_ratio
            
            # Check for blank or near-blank images
            if max_bin_ratio > self.blank_threshold:
                return ImageValidationResult(
                    is_valid=False,
                    image_path=image_path,
                    issue_type=ImageIssueType.BLANK,
                    details=f"Image appears to be blank or nearly blank (uniformity: {max_bin_ratio:.2%})",
                    metrics=metrics
                )
            
            # Check pixel variance 
            if stat.stddev[0] < self.min_content_variance * 255:
                return ImageValidationResult(
                    is_valid=False,
                    image_path=image_path,
                    issue_type=ImageIssueType.LOW_QUALITY,
                    details=f"Low image variance: {stat.stddev[0]:.2f}",
                    metrics=metrics
                )
                
        except Exception as e:
            # If analysis fails, log but continue with other checks
            logger.warning(f"Error analyzing image content: {str(e)}")
            metrics["analysis_error"] = str(e)
        
        # If we get here, the image passes validation
        return ImageValidationResult(
            is_valid=True,
            image_path=image_path,
            metrics=metrics
        )
    
    def diagnose_extraction_issue(self, source_pdf_path: str, page_num: int, image_index: int) -> Dict:
        """
        Diagnose potential issues with image extraction from PDF.
        This is a placeholder for more advanced diagnostic functions.
        
        Args:
            source_pdf_path: Path to the source PDF
            page_num: Page number in the PDF
            image_index: Index of the image on the page
            
        Returns:
            Dictionary with diagnostic information
        """
        # This would need to be expanded with more detailed PDF analysis
        # Currently returns basic information for tracking
        return {
            "pdf_path": source_pdf_path,
            "page_num": page_num,
            "image_index": image_index,
            "pdf_exists": os.path.exists(source_pdf_path),
            "pdf_size": os.path.getsize(source_pdf_path) if os.path.exists(source_pdf_path) else 0
        }


# Helper function to batch validate multiple images
def batch_validate_images(
    image_paths: List[str],
    validator: Optional[ImageValidator] = None
) -> Tuple[List[ImageValidationResult], Dict]:
    """
    Validate multiple images and return summary statistics.
    
    Args:
        image_paths: List of paths to image files
        validator: ImageValidator instance (optional)
        
    Returns:
        Tuple of (list of validation results, summary dictionary)
    """
    validator = validator or ImageValidator()
    results = []
    
    valid_count = 0
    issue_counts = {issue_type.value: 0 for issue_type in ImageIssueType}
    
    for image_path in image_paths:
        result = validator.validate_image_file(image_path)
        results.append(result)
        
        if result.is_valid:
            valid_count += 1
        else:
            issue_type = result.issue_type.value if result.issue_type else "other"
            issue_counts[issue_type] += 1
    
    # Prepare summary
    summary = {
        "total_images": len(image_paths),
        "valid_images": valid_count,
        "invalid_images": len(image_paths) - valid_count,
        "issue_breakdown": issue_counts
    }
    
    return results, summary


# Function to generate diagnostic report for problematic images
def generate_extraction_report(
    extraction_results: Dict,
    output_dir: Optional[str] = None
) -> Dict:
    """
    Generate a comprehensive diagnostic report for problematic images.
    
    Args:
        extraction_results: Results from ImageExtractor.extract_images_from_pdf
        output_dir: Optional directory to save report to
        
    Returns:
        Dictionary with report summary
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
    
    # Save report to file if output_dir provided
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, f"extraction_report_{int(time.time())}.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(summary["report_text"])
        
        summary["report_path"] = report_path
    
    return summary
