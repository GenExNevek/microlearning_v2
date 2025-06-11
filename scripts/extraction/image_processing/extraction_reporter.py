# scripts/extraction/extraction_reporter.py

"""Handles reporting and tracking of image extraction results."""

import logging
import time
import os
from typing import Dict, List, Any, Optional

from ...utils.image_validation import ImageIssueType
# --- NEW IMPORT ---
from .image_analyser import AnalysisResult

logger = logging.getLogger(__name__)

class ExtractionReporter:
    """Collects metrics, tracks problematic images, and generates reports."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the reporter with configuration."""
        self.config = config
        self.metrics = self._reset_metrics()
        self.problematic_images: List[Dict[str, Any]] = []
        # --- NEW ---
        self.kept_image_data: List[Dict[str, Any]] = [] # To store analysis of kept images
        self.errors: List[str] = []
        self.pdf_path: Optional[str] = None
        self.start_time: Optional[float] = None
        self.extracted_count: int = 0
        self.failed_count: int = 0

    def _reset_metrics(self) -> Dict[str, Any]:
        """Resets metrics for a new document."""
        return {
            "total_images_in_doc": 0,
            "attempted_extractions": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "validation_failures": 0,
            "retry_successes": 0,
            "issue_types": {issue_type.value: 0 for issue_type in ImageIssueType},
            "total_extraction_duration": 0.0,
            # --- NEW ---
            "filter_stats": {
                'total_filtered': 0,
                'filtered_as_blank': 0,
                'filtered_as_icon': 0,
                'filtered_by_size': 0,
                'kept_diagrams': 0,
                'kept_photos': 0,
                'kept_unknown': 0,
            },
            # --- NEW (for Phase 4) ---
            "correlation_stats": {
                'semantic_matches': 0,
                'context_matches': 0,
                'position_matches': 0,
                'fallback_matches': 0,
                'unresolved_references': 0
            }
        }

    def start_document_report(self, pdf_path: str):
        """Starts tracking for a new document."""
        self.pdf_path = pdf_path
        self.start_time = time.time()
        self.metrics = self._reset_metrics()
        self.problematic_images = []
        # --- NEW ---
        self.kept_image_data = []
        self.errors = []
        self.extracted_count = 0
        self.failed_count = 0
        logger.info(f"Starting extraction report for {pdf_path}")

    def track_image_attempt(self, img_info: tuple):
        """Tracks that an attempt will be made for an image."""
        self.metrics["total_images_in_doc"] += 1

    # --- ENTIRELY NEW METHOD ---
    def track_filtered_image(self, reason: str, analysis: AnalysisResult):
        """Tracks an image that was filtered out after analysis."""
        self.metrics["filter_stats"]['total_filtered'] += 1
        
        if "icon" in reason.lower():
            self.metrics["filter_stats"]['filtered_as_icon'] += 1
        elif "blank" in reason.lower():
            self.metrics["filter_stats"]['filtered_as_blank'] += 1
        elif "dimensions" in reason.lower():
            self.metrics["filter_stats"]['filtered_by_size'] += 1
        
        logger.debug(f"Image filtered. Reason: {reason}. Details: {analysis.dimensions}, {analysis.content_type}")

    def track_extraction_result(self, extraction_info: Dict, processing_result: Dict, analysis_result: Optional[AnalysisResult] = None):
        """
        Tracks the result of a single image extraction and processing pipeline.

        Args:
            extraction_info: The info dict returned by RetryCoordinator.
            processing_result: The info dict returned by ImageProcessor (save/validate).
            analysis_result: The result from ImageAnalyser for kept images.
        """
        self.metrics["attempted_extractions"] += 1
        self.metrics["total_extraction_duration"] += extraction_info.get('duration', 0.0)

        is_extracted = extraction_info.get('success', False)
        is_saved_and_valid = processing_result.get('success', False)
        
        current_issue_type_str: Optional[str] = None 

        if is_extracted:
            self.metrics["successful_extractions"] += 1

            if is_saved_and_valid:
                self.extracted_count += 1
                # --- NEW: Track content type and store analysis data ---
                if analysis_result:
                    content_type = analysis_result.content_type
                    if content_type == 'diagram':
                        self.metrics['filter_stats']['kept_diagrams'] += 1
                    elif content_type == 'photograph':
                        self.metrics['filter_stats']['kept_photos'] += 1
                    else:
                        self.metrics['filter_stats']['kept_unknown'] += 1
                    
                    self.kept_image_data.append({
                        'image_path': processing_result.get('path'),
                        'analysis': analysis_result,
                        'page_num': extraction_info.get('page'),
                        'xref': extraction_info.get('xref')
                    })
                # --- END NEW ---
            else: 
                self.failed_count += 1
                
                current_issue_type_str = processing_result.get('issue_type')
                is_actual_image_issue_type_failure = False
                if current_issue_type_str:
                    try:
                        ImageIssueType(current_issue_type_str)
                        is_actual_image_issue_type_failure = True
                    except ValueError:
                        pass 

                if is_actual_image_issue_type_failure:
                    self.metrics["validation_failures"] += 1
                
                if current_issue_type_str:
                    if current_issue_type_str not in self.metrics['issue_types']:
                        self.metrics['issue_types'][current_issue_type_str] = 0
                    self.metrics['issue_types'][current_issue_type_str] += 1
                else:
                    current_issue_type_str = 'processing_failed'
                    if current_issue_type_str not in self.metrics['issue_types']:
                        self.metrics['issue_types'][current_issue_type_str] = 0
                    self.metrics['issue_types'][current_issue_type_str] += 1

                if not processing_result.get('filtered', False):
                    self.problematic_images.append({
                        'page': extraction_info.get('page', 'unknown'),
                        'index_on_page': extraction_info.get('index_on_page', 'unknown'),
                        'xref': extraction_info.get('xref', 'unknown'),
                        'issue': processing_result.get('issue', 'Processing or Validation failed'),
                        'issue_type': current_issue_type_str,
                        'extraction_info': extraction_info,
                        'validation_info': processing_result.get('validation_info', {})
                    })
                    self.errors.append(
                        f"Processing/Validation failed for image on page {extraction_info.get('page')}, "
                        f"index {extraction_info.get('index_on_page')}: {processing_result.get('issue')}"
                    )

            if len(extraction_info.get('attempts', [])) > 1 and extraction_info['success']:
                 self.metrics['retry_successes'] += 1
        
        else:
            self.metrics["failed_extractions"] += 1
            self.failed_count += 1
            
            current_issue_type_str = extraction_info.get('issue_type', 'extraction_failed')
            if current_issue_type_str not in self.metrics['issue_types']:
                self.metrics['issue_types'][current_issue_type_str] = 0
            self.metrics['issue_types'][current_issue_type_str] += 1

            self.problematic_images.append({
                'page': extraction_info.get('page', 'unknown'),
                'index_on_page': extraction_info.get('index_on_page', 'unknown'),
                'xref': extraction_info.get('xref', 'unknown'),
                'issue': extraction_info.get('final_error', 'Extraction failed'),
                'issue_type': current_issue_type_str,
                'extraction_info': extraction_info,
            })
            self.errors.append(
                f"Extraction failed for image on page {extraction_info.get('page')}, "
                f"index {extraction_info.get('index_on_page')}: {extraction_info.get('final_error', 'Unknown error.')}"
            )

    def finalize_report(self, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """Finalizes the report and generates summary and problematic image details."""
        end_time = time.time()
        total_elapsed_time = end_time - self.start_time if self.start_time is not None else 0.0

        summary = {
            "pdf_path": self.pdf_path,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "total_elapsed_time": total_elapsed_time,
            "extracted_count": self.extracted_count,
            "failed_count": self.failed_count,
            "problematic_count": len(self.problematic_images),
            "errors_count": len(self.errors),
            "metrics": self.metrics,
            # --- NEW ---
            "kept_image_data": self.kept_image_data,
            "problematic_images": self.problematic_images,
            "errors": self.errors,
            "success": self.failed_count == 0 
        }

        total_processed = self.metrics.get("attempted_extractions", 0)
        failure_ratio = self.failed_count / total_processed if total_processed > 0 else 0

        if self.failed_count > 0 and failure_ratio > 0.25:
             summary['success'] = False
        
        if self.failed_count > 0 :
            summary['failure_ratio'] = failure_ratio

        report_text = self._generate_report_text(summary)
        summary['report_text'] = report_text

        report_path = None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
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

        success_status = "SUCCESSFUL" if summary['success'] else "PROBLEMATIC"
        logger.info(f"Image extraction {success_status} summary for {summary.get('pdf_path', 'N/A')}: "
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
            # --- NEW ---
            f"- Filtered out (icons, blanks, etc.): {summary['metrics'].get('filter_stats', {}).get('total_filtered', 0)}",
            f"- Successfully extracted & processed: {summary['extracted_count']}",
            f"- Failed extraction or processing/validation: {summary['failed_count']}",
            f"- Validation failures (extracted but invalid ImageIssueType): {summary['metrics'].get('validation_failures', 0)}",
            f"- Total problematic images reported: {summary['problematic_count']}",
            f"",
        ]

        # --- NEW SECTION ---
        filter_stats = summary['metrics'].get('filter_stats', {})
        if filter_stats:
            report.append("### Filter & Content Type Breakdown")
            report.append(f"- Images Filtered Out: {filter_stats.get('total_filtered', 0)}")
            report.append(f"  - As icon/UI element: {filter_stats.get('filtered_as_icon', 0)}")
            report.append(f"  - As blank: {filter_stats.get('filtered_as_blank', 0)}")
            report.append(f"  - By size: {filter_stats.get('filtered_by_size', 0)}")
            report.append(f"- Images Kept: {summary['extracted_count']}")
            report.append(f"  - Kept Diagrams: {filter_stats.get('kept_diagrams', 0)}")
            report.append(f"  - Kept Photographs: {filter_stats.get('kept_photos', 0)}")
            report.append(f"  - Kept Unknown Type: {filter_stats.get('kept_unknown', 0)}")
            report.append("")

        report.append(f"## Detailed Metrics")
        report.append(f"- Successful extractions (PIL image produced): {summary['metrics'].get('successful_extractions', 0)}")
        report.append(f"- Failed extractions (no PIL image produced): {summary['metrics'].get('failed_extractions', 0)}")
        report.append(f"- Retry successes (extracted after initial failure): {summary['metrics'].get('retry_successes', 0)}")
        report.append(f"- Total extraction time (strategy attempts): {summary['metrics'].get('total_extraction_duration', 0.0):.2f} seconds")
        report.append("")
        report.append(f"### Issue Type Breakdown (for problematic images)")

        issue_types_counts = summary['metrics'].get('issue_types', {})
        if issue_types_counts:
            present_issue_types = {k: v for k, v in issue_types_counts.items() if v > 0}
            if present_issue_types:
                for issue_type, count in sorted(present_issue_types.items()):
                    report.append(f"- {issue_type}: {count}")
            else:
                report.append("- No specific issue types recorded with counts > 0.")
        else:
             report.append("- No issue type data available.")

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

                ext_info = img.get('extraction_info', {})
                report.append(f"- **Extraction Attempts**: {ext_info.get('attempt_count', 0)}")
                if ext_info.get('attempts'):
                     report.append("  - **Attempt History**:")
                     for attempt_idx, attempt in enumerate(ext_info['attempts']):
                         status = 'SUCCESS' if attempt.get('success') else 'FAILED'
                         duration = attempt.get('duration', 0.0)
                         attempt_num_str = attempt.get('attempt_num', attempt_idx + 1)
                         report.append(f"    - Attempt {attempt_num_str}: Strategy='{attempt.get('strategy', 'unknown')}', Status={status}, Duration={duration:.4f}s")
                         if attempt.get('error'):
                             report.append(f"      - Error: {attempt['error']}")

                val_info = img.get('validation_info', {})
                if val_info:
                    report.append(f"- **Validation Details**: {val_info}")
                report.append("") 

        report.append("## Errors Log")
        if summary.get('errors'):
            for error_msg in summary['errors']:
                report.append(f"- {error_msg}")
        else:
            report.append("No specific errors were logged.")

        return "\n".join(report)