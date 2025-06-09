# scripts/extraction/image_processing/__init__.py

"""
Image Processing Package.

This package contains modules for extracting, processing, and managing images
from PDF files using a strategy pattern approach.
"""

# Import main classes to make them available at package level
from .image_extractor import ImageExtractor
from .image_processor import ImageProcessor
from .retry_coordinator import RetryCoordinator
from .extraction_reporter import ExtractionReporter

# Import strategy classes from the strategies subpackage
from .extraction_strategies import (
    BaseExtractionStrategy,
    StandardExtractionStrategy,
    AlternateColorspaceExtractionStrategy,
    CompressionRetryStrategy,
    PageBasedExtractionStrategy,
    StrategyTuple
)

__all__ = [
    'ImageExtractor',
    'ImageProcessor', 
    'RetryCoordinator',
    'ExtractionReporter',
    'BaseExtractionStrategy',
    'StandardExtractionStrategy',
    'AlternateColorspaceExtractionStrategy',
    'CompressionRetryStrategy',
    'PageBasedExtractionStrategy',
    'StrategyTuple'
]