# scripts/config/settings.py

"""Configuration settings for the extraction pipeline."""

import os
from dotenv import load_dotenv

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env"))

# Load environment variables from .env file
load_dotenv(ENV_PATH) # Corrected to use ENV_PATH

# API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-preview-04-17" # Example, adjust if needed

# LangSmith Tracing Configuration
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "microlearning-extraction")
LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
LANGSMITH_TRACING_ENABLED = os.getenv("LANGSMITH_TRACING_V2", "true").lower() == "true"
LANGSMITH_DEBUG = os.getenv("LANGSMITH_DEBUG", "false").lower() == "true"

# Base directory is the microlearning folder
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# File paths - make them relative to the BASE_DIR
PDF_SOURCE_DIR = os.path.join(BASE_DIR, "original_content_pdf")
MARKDOWN_TARGET_DIR = os.path.join(BASE_DIR, "original_content_markdown")
IMAGE_ASSETS_SUFFIX = "-img-assets" # This seems to be a suffix for directory names

# Image extraction settings
IMAGE_EXTRACTION_CONFIG = {
    "dpi": 150,                    # Resolution for image extraction (used by some strategies if applicable)
    "image_format": "png",         # Default output format
    "quality": 95,                 # JPG/PNG quality (1-100)
    "max_width": 1920,             # Maximum width for extracted images (used by ImageProcessor)
    "max_height": 1080,            # Maximum height for extracted images (used by ImageProcessor)
    "maintain_aspect_ratio": True, # Preserve original aspect ratio (used by ImageProcessor)
    "supported_formats": ["png", "jpg", "jpeg"],  # Formats to validate (used by ImageValidator via ImageProcessor)
    "min_width": 50,               # Minimum width to consider valid image (used by ImageValidator & strategies)
    "min_height": 50,              # Minimum height to consider valid image (used by ImageValidator & strategies)
    
    # Configuration for RetryCoordinator and strategies
    "retry_failed_extractions": True, # Enable retries across different strategies
    "max_extraction_retries": 3,      # Max total retries for a single image (Note: current RetryCoordinator tries each strategy once; this might be for future use or a higher-level retry mechanism)
    
    # === DIAGNOSTIC MODE CONFIGURATION ===
    "diagnostic_mode_enabled": False,  # Enable diagnostic mode globally
    "diagnostic_log_level": "INFO",    # Log level for diagnostic messages: DEBUG, INFO, WARNING
    "diagnostic_save_all_images": True, # Save all images in diagnostic mode regardless of filters
    
    # Configuration for specific strategies (can be added as needed)
    # e.g., "alternate_colorspace_options": ["RGB", "GRAY"],
    # e.g., "compression_retry_threshold": 0.5,

    # Configuration for ImageProcessor validation
    "validate_images": True,       # Enable image validation after saving
    "min_file_size": 256,          # Minimum file size in bytes (lowered from 1024 for simple graphics)

    # Configuration for ExtractionReporter
    "report_path": "reports",      # Default sub-directory for reports within output_dir (can be overridden)
    "save_report_to_file": True    # Whether the reporter should save the .md report
}

# === ENHANCED IMAGE PROCESSING CONFIGURATION ===
IMAGE_FILTER_CONFIG = {
    'FILTER_BLANK_IMAGES': True,
    'FILTER_UI_ELEMENTS': True,
    'MIN_MEANINGFUL_IMAGE_WIDTH': 50,
    'MIN_MEANINGFUL_IMAGE_HEIGHT': 50,
    'MAX_ICON_AREA_PX': 4096,  # Area of a 64x64 image
    
    # Enhanced filtering options
    'FILTER_DUPLICATE_IMAGES': True,    # Remove likely duplicates
    'MIN_CONTENT_COMPLEXITY': 0.1,      # Minimum image complexity score
    'ENABLE_CONTENT_DETECTION': True,    # Detect image content types
}

# === ENHANCED CORRELATION ENGINE CONFIGURATION ===
CORRELATION_CONFIG = {
    # Minimum confidence threshold for accepting matches
    'REQUIRE_MINIMUM_CONFIDENCE': 0.2,  # Lowered from 0.4 for more permissive matching
    
    # Enable sequential fallback when other strategies fail
    'ENABLE_FALLBACK_SEQUENTIAL': True,
    
    # Enable filename-based rescue matching
    'ENABLE_FILENAME_RESCUE': True,
    
    # Enable content-type based matching
    'ENABLE_CONTENT_TYPE_MATCHING': True,
    
    # Weights for different matching strategies (should sum to 1.0)
    'SEMANTIC_MATCH_WEIGHT': 0.4,
    'CONTEXT_MATCH_WEIGHT': 0.3,
    'POSITION_PROXIMITY_WEIGHT': 0.2,
    'VISUAL_SIMILARITY_WEIGHT': 0.1,
    
    # Scoring thresholds for different match types
    'EXPLICIT_MATCH_SCORE': 1.0,
    'SEMANTIC_MATCH_THRESHOLD': 0.6,
    'FILENAME_MATCH_THRESHOLD': 0.4,
    'SEQUENTIAL_FALLBACK_SCORE': 0.3,
    
    # Content analysis settings
    'CONTEXT_WINDOW_SIZE': 500,  # Characters to analyze around image refs
    'ENABLE_QUESTION_CONTEXT': True,  # Use question/activity context for matching
    'ENABLE_PAGE_ESTIMATION': True,   # Use heuristics to estimate page numbers
    
    # Debug and logging settings
    'DEBUG_CORRELATION': False,  # Enable detailed correlation logging
    'LOG_UNMATCHED_REFERENCES': True,  # Log details about failed matches
    'SAVE_CORRELATION_REPORT': False,  # Save detailed correlation analysis
}

# === ENHANCED PLACEHOLDER CONFIGURATION ===
PLACEHOLDER_CONFIG = {
    # Types of placeholders to generate
    'PLACEHOLDER_TYPES': {
        'thermometer': 'placeholder-thermometer.png',
        'graph': 'placeholder-graph.png', 
        'target': 'placeholder-target.png',
        'diagram': 'placeholder-diagram.png',
        'table': 'placeholder-table.png',
        'equation': 'placeholder-equation.png',
        'missing': 'placeholder-missing.png',
        'error': 'placeholder-error.png',
    },
    
    # Enhanced alt text for placeholders
    'ENHANCED_ALT_TEXT': True,
    'INCLUDE_DIAGNOSTIC_COMMENTS': True,
    
    # Fallback behavior
    'DEFAULT_PLACEHOLDER': 'placeholder-missing.png',
    'USE_DESCRIPTIVE_PLACEHOLDERS': True,
}

# === MARKDOWN PROCESSING ENHANCEMENTS ===
MARKDOWN_PROCESSING_CONFIG = {
    # Image link processing
    'ENABLE_MULTI_STRATEGY_MATCHING': True,
    'ENABLE_CONTENT_AWARE_ANALYSIS': True,
    'PRESERVE_EXTERNAL_LINKS': True,
    
    # Content analysis
    'EXTRACT_FIGURE_NUMBERS': True,
    'EXTRACT_PAGE_REFERENCES': True,
    'ANALYZE_SURROUNDING_CONTEXT': True,
    
    # Error handling
    'GRACEFUL_FAILURE_MODE': True,
    'DETAILED_ERROR_REPORTING': True,
    'INCLUDE_DIAGNOSTIC_METADATA': True,
}

# === DEBUGGING AND DEVELOPMENT ===
DEBUG_CONFIG = {
    # Enable various debug modes
    'DEBUG_IMAGE_CORRELATION': False,
    'DEBUG_CONTENT_ANALYSIS': False,
    'DEBUG_FILENAME_PARSING': False,
    
    # Output debug information
    'SAVE_DEBUG_REPORTS': False,
    'LOG_CORRELATION_DETAILS': True,
    'LOG_MATCHING_ATTEMPTS': False,
    
    # Performance monitoring
    'TRACK_PROCESSING_TIME': True,
    'LOG_MEMORY_USAGE': False,
}

# === VALIDATION AND QUALITY ASSURANCE ===
VALIDATION_CONFIG = {
    # Post-processing validation
    'VALIDATE_IMAGE_LINKS': True,
    'CHECK_FILE_EXISTENCE': True,
    'VERIFY_IMAGE_ACCESSIBILITY': True,
    
    # Quality thresholds
    'MIN_SUCCESSFUL_MATCH_RATE': 0.7,  # 70% of images should match
    'WARN_ON_EXCESSIVE_PLACEHOLDERS': True,
    'MAX_PLACEHOLDER_RATIO': 0.3,  # Warn if >30% are placeholders
    
    # Reporting
    'GENERATE_QUALITY_REPORT': True,
    'INCLUDE_MATCH_STATISTICS': True,
}

# === BACKWARD COMPATIBILITY ===
# Ensure existing configurations still work
if not hasattr(globals(), 'IMAGE_EXTRACTION_CONFIG'):
    IMAGE_EXTRACTION_CONFIG = {
        "output_format": "PNG",
        "quality": 95,
        "dpi": 150,
        "color_modes": ["RGBA", "RGB", "GRAY"],
        "validate_images": True,
        "report_path": "reports",
        "save_report_to_file": True
    }