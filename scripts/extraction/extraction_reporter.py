# scripts/extraction/extraction_reporter.py

"""Handles reporting and tracking of image extraction results."""

import logging
import time
import os
from typing import Dict, List, Any, Optional
from ..utils.image_validation import ImageIssueType # Assuming utils is a sibling or parent directory

logger = logging.getLogger(__name__)

class ExtractionReporter:
    """Collects metrics, tracks problematic images, and generates reports."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the reporter with configuration."""
        self.config = config
        self.metrics = self._reset_metrics()
        self.problematic_images: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.pdf_path: Optional[str] = None
        self.start_time: Optional[float] = None
        self.extracted_count: int = 0 # Track successful extractions for summary
        self.failed_count: int = 0 # Track total failed attempts to get an image

    def _reset_metrics(self) -> Dict[str, Any]:
        """Resets metrics for a new document."""
        return {
            "total_images_in_doc": 0, # Total images identified in PDF
            "attempted_extractions": 0, # Total images extraction was attempted for
            "successful_extractions": 0, # Successfully extracted (produced PIL image)
            "failed_extractions": 0, # Failed to extract (did not produce PIL image)
            "validation_failures": 0, # Extracted but failed validation
            "retry_successes": 0, # Successful extraction after initial standard failure
            "issue_types": {issue_type.value: 0 for issue_type in ImageIssueType},
            "total_extraction_duration": 0.0, # Sum of time spent in coordinate_extraction
        }

    def start_document_report(self, pdf_path: str):
        """Starts tracking for a new document."""
        self.pdf_path = pdf_path
        self.start_time = time.time()
        self.metrics = self._reset_metrics()
        self.problematic_images = []
        self.errors = []
        self.extracted_count = 0
        self.failed_count = 0
        logger.info(f"Starting extraction report for {pdf_path}")

    def track_image_attempt(self, img_info: tuple):
        """Tracks that an attempt will be made for an image."""
        self.metrics["total_images_in_doc"] += 1
        # Attempted extractions are counted when coordinate_extraction is called

    def track_extraction_result(self, extraction_info: Dict, processing_result: Dict):
        """
        Tracks the result of a single image extraction and processing pipeline.

        Args:
            extraction_info: The info dict returned by RetryCoordinator.
            processing_result: The info dict returned by ImageProcessor (save/validate).
        """
        self.metrics["attempted_extractions"] += 1
        self.metrics["total_extraction_duration"] += extraction_info.get('duration', 0.0)

        is_extracted = extraction_info.get('success', False)
        is_saved_and_valid = processing_result.get('success', False)
        is_validation_failed = processing_result.get('issue_type') is not None

        if is_extracted:
            self.metrics["successful_extractions"] += 1
            self.extracted_count += 1

            if is_saved_and_valid:
                # Fully successful pipeline
                pass # No problematic image added
            elif is_validation_failed:
                # Extracted but failed validation
                self.metrics["validation_failures"] += 1
                self.failed_count += 1 # Count validation failures as problematic failures for summary
                issue_type = processing_result.get('issue_type')
                if issue_type:
                    self.metrics['issue_types'][issue_type] = self.metrics['issue_types'].get(issue_type, 0) + 1

                self.problematic_images.append({
                    'page': extraction_info.get('page', 'unknown'),
                    'index_on_page': extraction_info.get('index_on_page', 'unknown'),
                    'xref': extraction_info.get('xref', 'unknown'),
                    'issue': processing_result.get('issue', 'Validation failed'),
                    'issue_type': issue_type,
                    'extraction_info': extraction_info,
                    'validation_info': processing_result.get('validation_info', {})
                })
                self.errors.append(f"Validation failed for image on page {extraction_info.get('page')}, index {extraction_info.get('index_on_page')}: {processing_result.get('issue')}")

            else: # Extracted but something went wrong during save/post-processing
                 self.failed_count += 1
                 self.problematic_images.append({
                    'page': extraction_info.get('page', 'unknown'),
                    'index_on_page': extraction_info.get('index_on_page', 'unknown'),
                    'xref': extraction_info.get('xref', 'unknown'),
                    'issue': processing_result.get('issue', 'Saving/Processing failed'),
                    'issue_type': processing_result.get('issue_type', 'processing_failed'),
                    'extraction_info': extraction_info,
                    'validation_info': processing_result.get('validation_info', {})
                })
                 self.errors.append(f"Saving/Processing failed for image on page {extraction_info.get('page')}, index {extraction_info.get('index_on_page')}: {processing_result.get('issue')}")


            # Check if extraction succeeded on a retry method (not the first attempt's strategy)
            if len(extraction_info.get('attempts', [])) > 1 and extraction_info['success']:
                 self.metrics['retry_successes'] += 1


        else:
            # Failed to extract (no PIL image produced)
            self.metrics["failed_extractions"] += 1
            self.failed_count += 1
            issue_type = extraction_info.get('issue_type', 'extraction_failed')
            self.metrics['issue_types'][issue_type] = self.metrics['issue_types'].get(issue_type, 0) + 1


            self.problematic_images.append({
                'page': extraction_info.get('page', 'unknown'),
                'index_on_page': extraction_info.get('index_on_page', 'unknown'),
                'xref': extraction_info.get('xref', 'unknown'),
                'issue': extraction_info.get('final_error', 'Extraction failed'),
                'issue_type': issue_type,
                'extraction_info': extraction_info,
                # No validation info as extraction failed
            })
            self.errors.append(f"Extraction failed for image on page {extraction_info.get('page')}, index {extraction_info.get('index_on_page')}: {extraction_info.get('final_error', 'Unknown error.')}")


    def finalize_report(self, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Finalizes the report and generates summary and problematic image details.

        Args:
            output_dir: Optional directory to save the report file.

        Returns:
            A dictionary containing the report summary and details.
        """
        end_time = time.time()
        total_elapsed_time = end_time - self.start_time if self.start_time else 0.0

        summary = {
            "pdf_path": self.pdf_path,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "total_elapsed_time": total_elapsed_time,
            "extracted_count": self.extracted_count,
            "failed_count": self.failed_count,
            "problematic_count": len(self.problematic_images),
            "errors_count": len(self.errors),
            "metrics": self.metrics,
            "problematic_images": self.problematic_images,
            "errors": self.errors,
            "success": self.failed_count == 0 # Simple success check
        }

        # Determine overall success based on failure ratio
        total_processed = self.extracted_count + self.failed_count
        failure_ratio = self.failed_count / total_processed if total_processed > 0 else 0

        # If more than 25% of images failed or had validation issues, mark as problematic
        if failure_ratio > 0.25:
             summary['success'] = False
             summary['failure_ratio'] = failure_ratio


        # Generate report text
        report_text = self._generate_report_text(summary)
        summary['report_text'] = report_text

        # Save report to file
        report_path = None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            # Use PDF filename base for report filename
            pdf_basename = os.path.splitext(os.path.basename(self.pdf_path or "report"))[0]
            report_filename = f"image_extraction_report_{pdf_basename}_{int(time.time())}.md"
            report_path = os.path.join(output_dir, report_filename)

            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
                summary["report_path"] = report_path
                logger.info(f"Image extraction report saved to {report_path}")
            except Exception as e:
                logger.error(f"Failed to save extraction report to {report_path}: {str(e)}")
                summary["report_save_error"] = str(e)


        # Log summary
        success_status = "SUCCESSFUL" if summary['success'] else "PROBLEMATIC"
        logger.info(f"Image extraction {success_status} summary for {summary['pdf_path']}: "
                   f"{summary['extracted_count']} extracted, "
                   f"{summary['failed_count']} failed/problematic, "
                   f"{summary['metrics'].get('validation_failures', 0)} validation issues. "
                   f"Total time: {summary['total_elapsed_time']:.2f}s")


        return summary

    def _generate_report_text(self, summary: Dict[str, Any]) -> str:
        """Generates the markdown report text."""
        report = [
            f"# Image Extraction Diagnostic Report",
            f"PDF: {summary['pdf_path']}",
            f"Date: {summary['timestamp']}",
            f"Total time: {summary['total_elapsed_time']:.2f} seconds",
            f"",
            f"## Summary",
            f"- Total identified images in PDF: {summary['metrics'].get('total_images_in_doc', 0)}",
            f"- Attempted extractions: {summary['metrics'].get('attempted_extractions', 0)}",
            f"- Successfully extracted & processed: {summary['extracted_count']}",
            f"- Failed extraction or processing/validation: {summary['failed_count']}",
            f"- Validation failures (extracted but invalid): {summary['metrics'].get('validation_failures', 0)}",
            f"- Total problematic images reported: {summary['problematic_count']}",
            f"",
            f"## Detailed Metrics",
            f"- Retry successes (extracted after initial failure): {summary['metrics'].get('retry_successes', 0)}",
            f"- Total extraction time (strategy attempts): {summary['metrics'].get('total_extraction_duration', 0.0):.2f} seconds",
            f"",
            f"### Issue Type Breakdown (for problematic images)"
        ]

        issue_types_counts = summary['metrics'].get('issue_types', {})
        if issue_types_counts:
             # Filter out issue types with zero count for report readability
            present_issue_types = {k: v for k, v in issue_types_counts.items() if v > 0}
            if present_issue_types:
                for issue_type, count in present_issue_types.items():
                    report.append(f"- {issue_type}: {count}")
            else:
                report.append("- No specific issue types recorded (might be general errors)")
        else:
             report.append("- No issue type data available")


        report.append("")
        report.append("## Problematic Images Details")

        if not summary['problematic_images']:
            report.append("No problematic images were identified.")
        else:
            for i, img in enumerate(summary['problematic_images']):
                report.append(f"### Problematic Image {i+1} (Page {img.get('page', '?')}, Index {img.get('index_on_page', '?')})")
                report.append(f"- **XREF**: {img.get('xref', 'unknown')}")
                report.append(f"- **Issue**: {img.get('issue', 'Unknown issue')}")
                report.append(f"- **Issue Type**: {img.get('issue_type', 'unknown')}")

                # Extraction Info
                ext_info = img.get('extraction_info', {})
                report.append(f"- **Extraction Attempts**: {ext_info.get('attempt_count', 0)}")
                # Detailed attempts history
                report.append("  - **Attempt History**:")
                if ext_info.get('attempts'):
                     for attempt in ext_info['attempts']:
                         status = 'SUCCESS' if attempt.get('success') else 'FAILED'
                         duration = attempt.get('duration', 0.0)
                         report.append(f"    - Attempt {attempt.get('attempt_num')}: Strategy='{attempt.get('strategy', 'unknown')}', Status={status}, Duration={duration:.4f}s")
                         if attempt.get('error'):
                             report.append(f"      - Error: {attempt['error']}")
                         if attempt.get('details', {}).get('warning'):
                             report.append(f"      - Warning: {attempt['details']['warning']}")
                         if attempt.get('details', {}).get('dimensions'):
                             report.append(f"      - Dimensions: {attempt['details']['dimensions']}")
                         if attempt.get('details', {}).get('mode'):
                             report.append(f"      - Mode: {attempt['details']['mode']}")

                # Validation Info
                val_info = img.get('validation_info', {})
                if val_info:
                    report.append(f"- **Validation Details**: {val_info}")

                report.append("") # Newline after each image block

        report.append("## Errors Log")
        if self.errors:
            for error_msg in self.errors:
                report.append(f"- {error_msg}")
        else:
            report.append("No specific errors were logged.")

        return "\n".join(report)
