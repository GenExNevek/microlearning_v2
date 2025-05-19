"""Utility functions and decorators for LangSmith tracing."""

import functools
import logging
import time
import os
from typing import Any, Callable, Dict, List, Optional, Union
from langsmith import traceable
from langchain_core.tracers.context import tracing_v2_enabled
from ..config.tracing import is_tracing_enabled, create_run_metadata

logger = logging.getLogger(__name__)


class ImageExtractionTracker:
    """Helper class for tracking image extraction metrics across multiple documents."""
    
    def __init__(self):
        """Initialize the extraction tracker."""
        self.reset()
    
    def reset(self):
        """Reset all tracking metrics."""
        self.document_count = 0
        self.successful_documents = 0
        self.problematic_documents = 0
        self.total_images = 0
        self.extracted_images = 0
        self.failed_images = 0
        self.validation_failures = 0
        self.problematic_documents_list = []
        self.issue_types = {}
        self.start_time = time.time()
    
    def add_document_result(self, doc_path: str, extraction_results: Dict):
        """
        Add results from a single document extraction.
        
        Args:
            doc_path: Path to the document
            extraction_results: Extraction results dictionary
        """
        self.document_count += 1
        
        # Track document success/failure
        if extraction_results.get('success', False):
            self.successful_documents += 1
        else:
            self.problematic_documents += 1
            self.problematic_documents_list.append({
                'path': doc_path,
                'errors': extraction_results.get('errors', []),
                'problematic_count': len(extraction_results.get('problematic_images', [])),
                'failure_ratio': extraction_results.get('failure_ratio', 0)
            })
        
        # Track image counts
        self.total_images += (extraction_results.get('extracted_count', 0) + 
                              extraction_results.get('failed_count', 0))
        self.extracted_images += extraction_results.get('extracted_count', 0)
        self.failed_images += extraction_results.get('failed_count', 0)
        self.validation_failures += extraction_results.get('validation_failures', 0)
        
        # Track issue types
        metrics = extraction_results.get('extraction_metrics', {})
        issue_types = metrics.get('issue_types', {})
        
        for issue_type, count in issue_types.items():
            if count > 0:
                self.issue_types[issue_type] = self.issue_types.get(issue_type, 0) + count
    
    def get_summary(self) -> Dict:
        """Get summary of all tracked extractions."""
        elapsed_time = time.time() - self.start_time
        success_rate = (self.extracted_images / self.total_images * 100) if self.total_images > 0 else 0
        
        return {
            'document_count': self.document_count,
            'successful_documents': self.successful_documents,
            'problematic_documents': self.problematic_documents,
            'total_images': self.total_images,
            'extracted_images': self.extracted_images,
            'failed_images': self.failed_images,
            'validation_failures': self.validation_failures,
            'success_rate': f"{success_rate:.1f}%",
            'issue_types': self.issue_types,
            'elapsed_time': elapsed_time,
            'problematic_documents_list': self.problematic_documents_list,
        }


# Global tracker instance
image_extraction_tracker = ImageExtractionTracker()


def traced_operation(
    operation_type: str,
    name: Optional[str] = None,
    metadata_extractor: Optional[Callable] = None,
    run_type: str = "chain",
    visibility: str = "visible",
    track_image_extraction: bool = False
):
    """
    Decorator to trace operations with LangSmith.
    
    Args:
        operation_type: Type of operation (e.g., "pdf_reading", "image_extraction")
        name: Custom name for the trace (defaults to function name)
        metadata_extractor: Function to extract metadata from arguments
        run_type: LangSmith run type (chain, llm, tool, etc.)
        visibility: Controls trace visibility: "visible" (default) or "hidden"
        track_image_extraction: Whether to track image extraction metrics
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **original_kwargs):
            # Skip tracing if not enabled
            if not is_tracing_enabled():
                return func(*args, **original_kwargs)
            
            # Make a clean copy of kwargs for function execution
            kwargs = original_kwargs.copy()
            
            # Handle parent visibility context (but remove from kwargs passed to the actual function)
            parent_visibility = "visible"
            if "__parent_visibility" in kwargs:
                parent_visibility = kwargs.pop("__parent_visibility")
            
            # Skip trace recording for hidden operations based on context
            if visibility == "hidden" and parent_visibility == "visible":
                # Execute function without creating a trace
                return func(*args, **kwargs)
            
            # Prepare metadata
            metadata = create_run_metadata(operation_type)
            metadata["visibility"] = visibility
            
            # Extract additional metadata if extractor provided
            if metadata_extractor:
                try:
                    additional_metadata = metadata_extractor(*args, **kwargs)
                    if additional_metadata:
                        metadata.update(additional_metadata)
                except Exception as e:
                    logger.warning(f"Failed to extract metadata: {e}")
            
            # Use custom name or function name
            trace_name = name or func.__name__
            
            # Create traced function
            traced_func = traceable(
                name=trace_name,
                run_type=run_type,
                metadata=metadata,
                tags=[operation_type, "microlearning"]
            )(func)
            
            # Add visibility context for child operations via a new kwargs dict
            traced_kwargs = kwargs.copy()
            traced_kwargs["__parent_visibility"] = visibility
            
            # Execute with timing
            start_time = time.time()
            try:
                # Pass the original kwargs to the actual function
                result = traced_func(*args, **kwargs)
                metadata["duration_seconds"] = time.time() - start_time
                metadata["status"] = "success"
                
                # Special handling for image extraction results
                if track_image_extraction and isinstance(result, dict):
                    # This is an image extraction result
                    update_extraction_trace_metadata(metadata, result)
                    
                    # Add to global tracker if provided
                    if len(args) > 1 and isinstance(args[1], str):
                        # Assuming first arg is self, second is pdf_path
                        image_extraction_tracker.add_document_result(args[1], result)
                
                return result
            except Exception as e:
                metadata["duration_seconds"] = time.time() - start_time
                metadata["status"] = "error"
                metadata["error"] = str(e)
                raise
            
        return wrapper
    return decorator


def update_extraction_trace_metadata(metadata: Dict, extraction_results: Dict):
    """
    Update trace metadata with image extraction results.
    
    Args:
        metadata: Trace metadata dictionary
        extraction_results: Image extraction results dictionary
    """
    # Add image extraction metrics
    metadata["image_extraction_success"] = extraction_results.get("success", False)
    metadata["images_extracted"] = extraction_results.get("extracted_count", 0)
    metadata["images_failed"] = extraction_results.get("failed_count", 0)
    metadata["validation_failures"] = extraction_results.get("validation_failures", 0)
    
    # Add tag for problematic extractions
    if extraction_results.get("problematic_images", []):
        if "tags" not in metadata:
            metadata["tags"] = []
        metadata["tags"].append("problematic_extraction")
        
        # Only add detailed issue data if there are problems
        metadata["problematic_images_count"] = len(extraction_results.get("problematic_images", []))
        
        # Add summary of issue types
        issue_counts = {}
        for img in extraction_results.get("problematic_images", []):
            issue_type = img.get("issue_type", "unknown")
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        
        metadata["issue_types"] = issue_counts


def trace_api_call(model_id: str, operation: str = "generate"):
    """
    Decorator specifically for tracing API calls.
    
    Args:
        model_id: ID of the model being called
        operation: Type of API operation
    """
    def metadata_extractor(*args, **kwargs):
        metadata = {
            "model_id": model_id,
            "api_operation": operation
        }
        
        # Extract prompt if available
        if args and len(args) > 1:
            if hasattr(args[1], "__len__"):
                metadata["prompt_length"] = len(str(args[1]))
        
        return metadata
    
    return traced_operation(
        operation_type="api_call",
        metadata_extractor=metadata_extractor,
        run_type="llm"
    )


def trace_batch_operation(operation_name: str):
    """
    Context manager for tracing batch operations.
    
    Args:
        operation_name: Name of the batch operation
    """
    class BatchTracer:
        def __init__(self, name: str):
            self.name = name
            self.metadata = {
                "operation": "batch",
                "batch_name": name,
                "items_processed": 0,
                "items_failed": 0
            }
            self.start_time = None
            
        def __enter__(self):
            if is_tracing_enabled():
                self.start_time = time.time()
                # Reset image extraction tracker at start of batch
                image_extraction_tracker.reset()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if is_tracing_enabled() and self.start_time:
                self.metadata["duration_seconds"] = time.time() - self.start_time
                self.metadata["status"] = "error" if exc_type else "success"
                
                # Add image extraction metrics to batch metadata
                extraction_summary = image_extraction_tracker.get_summary()
                self.metadata.update({
                    "documents_processed": extraction_summary["document_count"],
                    "documents_problematic": extraction_summary["problematic_documents"],
                    "total_images": extraction_summary["total_images"],
                    "extracted_images": extraction_summary["extracted_images"],
                    "failed_images": extraction_summary["failed_images"],
                    "image_extraction_success_rate": extraction_summary["success_rate"]
                })
                
                # Log batch results with image extraction info
                logger.info(f"Batch operation '{self.name}' completed: "
                          f"{self.metadata['items_processed']} processed, "
                          f"{self.metadata['items_failed']} failed")
                
                if extraction_summary["problematic_documents"] > 0:
                    logger.warning(f"Image extraction issues detected in {extraction_summary['problematic_documents']} documents")
                    for doc in extraction_summary["problematic_documents_list"]:
                        logger.warning(f"Problematic document: {doc['path']} - {doc['problematic_count']} issue(s)")
                
        def update_progress(self, processed: int = 0, failed: int = 0):
            """Update batch progress counters."""
            self.metadata["items_processed"] += processed
            self.metadata["items_failed"] += failed
    
    return BatchTracer(operation_name)


def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """Extract metadata from a file path for tracing."""
    import os
    
    metadata = {
        "file_name": os.path.basename(file_path),
        "file_extension": os.path.splitext(file_path)[1]
    }
    
    # Extract course/module/unit information if available
    path_parts = file_path.replace('\\', '/').split('/')
    for part in path_parts:
        if part.startswith('CON'):
            metadata["course_id"] = part.split('-')[0]
        elif part.startswith('MOD'):
            metadata["module_id"] = part.split('-')[0]
        elif part.startswith('UNI'):
            metadata["unit_id"] = part.split('-')[0] if '-' in part else part.split('_')[0]
    
    return metadata


def get_image_extraction_summary() -> Dict:
    """Get the current image extraction summary from the global tracker."""
    return image_extraction_tracker.get_summary()


def generate_batch_report(output_dir: Optional[str] = None) -> Dict:
    """
    Generate a comprehensive report of image extraction issues across the batch.
    
    Args:
        output_dir: Optional directory to save report to
        
    Returns:
        Dictionary with summary information
    """
    summary = image_extraction_tracker.get_summary()
    
    # Generate markdown report
    report = [
        f"# Image Extraction Batch Report",
        f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## Summary",
        f"- Documents processed: {summary['document_count']}",
        f"- Documents with issues: {summary['problematic_documents']}",
        f"- Total images: {summary['total_images']}",
        f"- Successfully extracted: {summary['extracted_images']}",
        f"- Failed to extract: {summary['failed_images']}",
        f"- Validation failures: {summary['validation_failures']}",
        f"- Overall success rate: {summary['success_rate']}",
        f"- Processing time: {summary['elapsed_time']:.1f} seconds",
        f"",
        f"## Issue Breakdown"
    ]
    
    for issue_type, count in summary['issue_types'].items():
        report.append(f"- {issue_type}: {count}")
    
    report.append("")
    report.append("## Problematic Documents")
    
    # Add details for each problematic document
    for i, doc in enumerate(summary['problematic_documents_list']):
        report.append(f"### Document {i+1}: {doc['path']}")
        report.append(f"- **Problematic Images**: {doc['problematic_count']}")
        report.append(f"- **Failure Ratio**: {doc['failure_ratio']:.2f}")
        
        if doc['errors']:
            report.append(f"- **Errors**:")
            for error in doc['errors']:
                report.append(f"  - {error}")
        
        report.append("")
    
    summary["report_text"] = "\n".join(report)
    
    # Save report to file if output_dir provided
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, f"batch_extraction_report_{int(time.time())}.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(summary["report_text"])
        
        summary["report_path"] = report_path
    
    return summary