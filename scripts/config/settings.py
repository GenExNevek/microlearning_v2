"""Configuration settings for the extraction pipeline."""

import os
from dotenv import load_dotenv

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env"))

# Load environment variables from .env file
load_dotenv()

# API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"

# Base directory is the microlearning folder
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# File paths - make them relative to the BASE_DIR
PDF_SOURCE_DIR = os.path.join(BASE_DIR, "original_content_pdf")
MARKDOWN_TARGET_DIR = os.path.join(BASE_DIR, "original_content_markdown")
IMAGE_ASSETS_SUFFIX = "-img-assets"

# Image extraction settings
IMAGE_EXTRACTION_CONFIG = {
    "dpi": 150,                    # Resolution for image extraction
    "image_format": "png",         # Default output format
    "quality": 95,                 # JPG/PNG quality (1-100)
    "max_width": 1920,            # Maximum width for extracted images
    "max_height": 1080,           # Maximum height for extracted images
    "maintain_aspect_ratio": True, # Preserve original aspect ratio
    "supported_formats": ["png", "jpg", "jpeg"],  # Formats to extract
    "min_width": 50,              # Minimum width to consider valid image
    "min_height": 50,             # Minimum height to consider valid image
}

print(f"ENV file path: {ENV_PATH}")
print(f"ENV file exists: {os.path.exists(ENV_PATH)}")