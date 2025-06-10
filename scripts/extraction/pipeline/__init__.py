# scripts/extraction/pipeline/__init__.py

"""
Package for orchestrating the PDF to Markdown extraction pipeline.

This package includes:
- ExtractionOrchestrator: Handles the core transformation logic for a single PDF.
- BatchProcessor: Manages processing of multiple PDFs (single, directory, batch).
- PipelineCoordinator: High-level coordinator for the entire pipeline execution,
                       CLI interactions, and global configurations.
"""

from .extraction_orchestrator import ExtractionOrchestrator
from .batch_processor import BatchProcessor
from .pipeline_coordinator import PipelineCoordinator

__all__ = [
    'ExtractionOrchestrator',
    'BatchProcessor',
    'PipelineCoordinator'
]