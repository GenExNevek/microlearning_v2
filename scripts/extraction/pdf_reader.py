"""Module for handling PDF reading and Gemini API integration."""

import os
import io
from google import genai
from google.genai import types
from ..config import settings

class PDFReader:
    """Handles PDF reading and interaction with Gemini API."""
    
    def __init__(self, api_key=None, model_id=None):
        """Initialize PDFReader with API credentials."""
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_id = model_id or settings.GEMINI_MODEL
        self.client = genai.Client(api_key=self.api_key)
        
    def read_pdf_from_path(self, file_path):
        """Read PDF file from local path and return file data."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at {file_path}")
            
        # Normalize the path for consistent handling
        normalized_path = os.path.normpath(file_path)
        
        # Check file size to determine processing method
        if os.path.getsize(file_path) < 20 * 1024 * 1024:  # Less than 20MB
            return self._prepare_direct_processing(normalized_path)
        else:
            return self._prepare_file_api_processing(normalized_path)
    
    def _prepare_direct_processing(self, file_path):
        """Prepare PDF data for direct processing."""
        with open(file_path, 'rb') as file:
            pdf_data = file.read()
        return {
            'method': 'direct',
            'data': pdf_data,
            'path': file_path,
            'normalized_path': file_path  # Keep normalized path for image extraction
        }
        
    def _prepare_file_api_processing(self, file_path):
        """Prepare PDF for processing via File API."""
        return {
            'method': 'file_api',
            'path': file_path,
            'normalized_path': file_path  # Keep normalized path for image extraction
        }
        
    def test_pdf_reading(self, pdf_info):
        """Test if Gemini can read the PDF by requesting a simple summary."""
        try:
            if pdf_info['method'] == 'direct':
                # For direct method (files under 20MB)
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=[
                        types.Part.from_bytes(
                            data=pdf_info['data'],
                            mime_type='application/pdf',
                        ),
                        "Give me a brief description of what this PDF contains."
                    ]
                )
            else:
                # For File API method (files over 20MB)
                file_obj = self.client.files.upload(
                    file=pdf_info['path'],
                    config=dict(mime_type='application/pdf')
                )
                
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=[
                        file_obj,
                        "Give me a brief description of what this PDF contains."
                    ]
                )
                
            return {
                'success': True,
                'summary': response.text,
                'pdf_info': pdf_info
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'pdf_info': pdf_info
            }