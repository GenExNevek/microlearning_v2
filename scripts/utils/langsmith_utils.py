"""Utility functions and decorators for LangSmith tracing."""

import functools
import logging
import time
from typing import Any, Callable, Dict, Optional
from langsmith import traceable
from langchain_core.tracers.context import tracing_v2_enabled
from ..config.tracing import is_tracing_enabled, create_run_metadata

logger = logging.getLogger(__name__)


def traced_operation(
    operation_type: str,
    name: Optional[str] = None,
    metadata_extractor: Optional[Callable] = None,
    run_type: str = "chain",
    visibility: str = "visible"
):
    """
    Decorator to trace operations with LangSmith.
    
    Args:
        operation_type: Type of operation (e.g., "pdf_reading", "image_extraction")
        name: Custom name for the trace (defaults to function name)
        metadata_extractor: Function to extract metadata from arguments
        run_type: LangSmith run type (chain, llm, tool, etc.)
        visibility: Controls trace visibility: "visible" (default) or "hidden"
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
                return result
            except Exception as e:
                metadata["duration_seconds"] = time.time() - start_time
                metadata["status"] = "error"
                metadata["error"] = str(e)
                raise
            
        return wrapper
    return decorator


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
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if is_tracing_enabled() and self.start_time:
                self.metadata["duration_seconds"] = time.time() - self.start_time
                self.metadata["status"] = "error" if exc_type else "success"
                
                # Log batch results
                logger.info(f"Batch operation '{self.name}' completed: "
                          f"{self.metadata['items_processed']} processed, "
                          f"{self.metadata['items_failed']} failed")
                
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