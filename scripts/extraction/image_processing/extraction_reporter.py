# scripts/extraction/image_processing/extraction_reporter.py

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
    """Collects metrics, tracks problematic images, and generates reports.
    
    Enhanced with diagnostic mode support for detailed filtering analysis.
    """

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
                'filtered_as_decorative': 0,  # Added for diagnostic mode
                'kept_diagrams': 0,
                'kept_photos': 0,
                'kept_unknown': 0,
            },
            # --- NEW (for diagnostic mode) ---
            "diagnostic_stats": {
                'would_be_filtered_count': 0,
                'would_be_filtered_blank': 0,
                'would_be_filtered_icon': 0,
                'would_be_filtered_size': 0,
                'would_be_filtered_decorative': 0,
                'extraction_failures': 0,
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
        elif "decorative" in reason.lower() or "banner" in reason.lower():
            self.metrics["filter_stats"]['filtered_as_decorative'] += 1
        
        logger.debug(f"Image filtered. Reason: {reason}. Details: {analysis.dimensions}, {analysis.content_type}")

    def track_extraction_result(self, extraction_info: Dict, processing_result: Dict, analysis_result: Optional[AnalysisResult] = None, diagnostic_reason: Optional[str] = None):
        """
        Tracks the result of a single image extraction and processing pipeline.
        
        Enhanced with diagnostic mode support.

        Args:
            extraction_info: The info dict returned by RetryCoordinator.
            processing_result: The info dict returned by ImageProcessor (save/validate).
            analysis_result: The result from ImageAnalyser for kept images.
            diagnostic_reason: Optional diagnostic reason from filter analysis.
        """
        self.metrics["attempted_extractions"] += 1
        self.metrics["total_extraction_duration"] += extraction_info.get('duration', 0.0)

        is_extracted = extraction_info.get('success', False)
        is_saved_and_valid = processing_result.get('success', False)
        
        current_issue_type_str: Optional[str] = None 

        if is_extracted:
            self.metrics["successful_extractions"] += 1
            problem_details = {
                'page': extraction_info.get('page', 'unknown'),
                'index_on_page': extraction_info.get('index_on_page', 'unknown'),
                'xref': extraction_info.get('xref', 'unknown'),
                'extraction_info': extraction_info,
                'validation_info': processing_result.get('validation_info', {}),
                'diagnostic_reason': diagnostic_reason
            }

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
                        'xref': extraction_info.get('xref'),
                        'diagnostic_reason': diagnostic_reason
                    })
                
                # --- NEW: Track diagnostic information even for saved images ---
                if diagnostic_reason and "[WOULD BE FILTERED]" in diagnostic_reason:
                    self.metrics["diagnostic_stats"]['would_be_filtered_count'] += 1
                    
                    # Track specific filter types that would have been applied
                    if "blank" in diagnostic_reason.lower():
                        self.metrics["diagnostic_stats"]['would_be_filtered_blank'] += 1
                    elif "icon" in diagnostic_reason.lower():
                        self.metrics["diagnostic_stats"]['would_be_filtered_icon'] += 1
                    elif "dimensions" in diagnostic_reason.lower():
                        self.metrics["diagnostic_stats"]['would_be_filtered_size'] += 1
                    elif "decorative" in diagnostic_reason.lower() or "banner" in diagnostic_reason.lower():
                        self.metrics["diagnostic_stats"]['would_be_filtered_decorative'] += 1
                    
                    # In diagnostic mode, track as problematic for analysis purposes
                    problem_details.update({
                        'issue': f"Diagnostic: {diagnostic_reason}",
                        'issue_type': 'diagnostic_would_filter'
                    })
                    self.problematic_images.append(problem_details)
                # --- END NEW ---

            else: 
                self.failed_count += 1
                current_issue_type_str = processing_result.get('issue_type')
                
                if current_issue_type_str and current_issue_type_str not in self.metrics['issue_types']:
                    self.metrics['issue_types'][current_issue_type_str] = 0
                if current_issue_type_str:
                    self.metrics['issue_types'][current_issue_type_str] += 1
                
                if 'filtered' not in processing_result or not processing_result['filtered']:
                    problem_details.update({
                        'issue': processing_result.get('issue', 'Processing or Validation failed'),
                        'issue_type': current_issue_type_str
                    })
                    self.problematic_images.append(problem_details)
                    self.errors.append(
                        f"Processing/Validation failed for image on page {extraction_info.get('page')}, "
                        f"index {extraction_info.get('index_on_page')}: {processing_result.get('issue')}"
                    )

            if len(extraction_info.get('attempts', [])) > 1 and extraction_info['success']:
                 self.metrics['retry_successes'] += 1
        
        else: # Extraction itself failed
            self.metrics["failed_extractions"] += 1
            self.failed_count += 1
            
            # Track diagnostic information for extraction failures
            if diagnostic_reason:
                self.metrics["diagnostic_stats"]['extraction_failures'] += 1
            
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
                'diagnostic_reason': diagnostic_reason
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

        # Save report to file if configured
        if self.config.get('save_report_to_file', True) and output_dir:
            report_path = self._save_report_to_file(report_text, output_dir)
            if report_path:
                summary["report_path"] = report_path

        success_status = "SUCCESSFUL" if summary['success'] else "PROBLEMATIC"
        logger.info(f"Image extraction {success_status} summary for {summary.get('pdf_path', 'N/A')}: "
                   f"{summary['extracted_count']} extracted, "
                   f"{summary['failed_count']} failed/problematic, "
                   f"{summary['metrics'].get('validation_failures', 0)} validation issues. "
                   f"Total time: {summary['total_elapsed_time']:.2f}s")

        return summary

    def _save_report_to_file(self, report_text: str, output_dir: str) -> Optional[str]:
        """Save the report text to a markdown file."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            pdf_basename = os.path.splitext(os.path.basename(self.pdf_path or "report"))[0]
            report_filename = f"image_extraction_report_{pdf_basename}_{int(time.time())}.md"
            report_path = os.path.join(output_dir, report_filename)

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            
            logger.info(f"Image extraction report saved to {report_path}")
            return report_path
        except Exception as e:
            logger.error(f"Failed to save extraction report: {str(e)}")
            return None

    def _generate_report_text(self, summary: Dict[str, Any]) -> str:
        """Generates the markdown report text with diagnostic information."""
        is_diagnostic_mode = summary['metrics'].get('diagnostic_stats', {}).get('would_be_filtered_count', 0) > 0
        
        report = [
            f"# Image Extraction {'Diagnostic ' if is_diagnostic_mode else ''}Report",
            f"**PDF:** {summary['pdf_path']}",
            f"**Date:** {summary['timestamp']}",
            f"**Total time:** {summary['total_elapsed_time']:.2f} seconds",
            f"",
            f"## Summary",
            f"- Total identified images in PDF: {summary['metrics'].get('total_images_in_doc', 0)}",
            f"- Attempted extractions: {summary['metrics'].get('attempted_extractions', 0)}",
            f"- Successfully extracted & processed (saved to disk): {summary['extracted_count']}",
            f"- Extraction or Processing Failures: {summary.get('failed_count', 0)}",
        ]
        
        # Add diagnostic mode specific summary
        if is_diagnostic_mode:
            diagnostic_stats = summary['metrics'].get('diagnostic_stats', {})
            report.extend([
                f"",
                f"### 🔍 Diagnostic Mode Results",
                f"- **Images that would normally be filtered:** {diagnostic_stats.get('would_be_filtered_count', 0)}",
                f"  - Would be filtered as blank: {diagnostic_stats.get('would_be_filtered_blank', 0)}",
                f"  - Would be filtered as icons: {diagnostic_stats.get('would_be_filtered_icon', 0)}",
                f"  - Would be filtered by size: {diagnostic_stats.get('would_be_filtered_size', 0)}",
                f"  - Would be filtered as decorative: {diagnostic_stats.get('would_be_filtered_decorative', 0)}",
                f"- **Extraction failures:** {diagnostic_stats.get('extraction_failures', 0)}",
            ])
        
        report.extend([
            f"- Total problematic images reported: {summary['problematic_count']}",
            f"",
            "## Filter Statistics",
            f"- Images kept as diagrams: {summary['metrics']['filter_stats'].get('kept_diagrams', 0)}",
            f"- Images kept as photographs: {summary['metrics']['filter_stats'].get('kept_photos', 0)}",
            f"- Images kept (unknown type): {summary['metrics']['filter_stats'].get('kept_unknown', 0)}",
        ])

        # Add normal mode filter stats
        if not is_diagnostic_mode:
            report.extend([
                f"- Total filtered out: {summary['metrics']['filter_stats'].get('total_filtered', 0)}",
                f"  - Filtered as blank: {summary['metrics']['filter_stats'].get('filtered_as_blank', 0)}",
                f"  - Filtered as icons: {summary['metrics']['filter_stats'].get('filtered_as_icon', 0)}",
                f"  - Filtered by size: {summary['metrics']['filter_stats'].get('filtered_by_size', 0)}",
                f"  - Filtered as decorative: {summary['metrics']['filter_stats'].get('filtered_as_decorative', 0)}",
            ])
        
        report.extend([
            f"",
            f"## {'Diagnostic Analysis' if is_diagnostic_mode else 'Problematic Images'}",
        ])

        if not summary['problematic_images']:
            report.append("No problematic images were identified.")
        else:
            for i, img in enumerate(summary['problematic_images']):
                report.append(f"### Problem {i+1} (Page {img.get('page', '?')}, Index {img.get('index_on_page', '?')})")
                report.append(f"- **Issue**: {img.get('issue', 'Unknown issue')}")
                
                # Add diagnostic information if available
                if img.get('diagnostic_reason'):
                    report.append(f"- **Diagnostic Info**: {img['diagnostic_reason']}")
                
                # Add technical details
                if img.get('xref'):
                    report.append(f"- **Reference ID**: {img['xref']}")
                
                report.append("") 

        # Add extraction performance details
        if summary['metrics'].get('retry_successes', 0) > 0:
            report.extend([
                f"",
                f"## Extraction Performance",
                f"- Successful retries: {summary['metrics']['retry_successes']}",
                f"- Average extraction time: {summary['metrics']['total_extraction_duration'] / max(1, summary['metrics']['attempted_extractions']):.3f}s per image",
            ])

        return "\n".join(report)