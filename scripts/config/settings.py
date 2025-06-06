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
    
    # Configuration for specific strategies (can be added as needed)
    # e.g., "alternate_colorspace_options": ["RGB", "GRAY"],
    # e.g., "compression_retry_threshold": 0.5,

    # Configuration for ImageProcessor validation
    "validate_images": True,       # Enable image validation after saving

    # Configuration for ExtractionReporter
    "report_path": "reports",      # Default sub-directory for reports within output_dir (can be overridden)
    "save_report_to_file": True    # Whether the reporter should save the .md report
}

# Ensure .env loading messages are useful
# print(f"Attempting to load .env from: {ENV_PATH}")
# print(f".env file exists: {os.path.exists(ENV_PATH)}")
# if GEMINI_API_KEY:
#     print("GEMINI_API_KEY loaded successfully.")
# else:
#     print("GEMINI_API_KEY not found. Please check your .env file and path.")