# scripts/extraction/pdf_reader.py

"""Module for handling PDF reading and Gemini API integration."""

import os
# from google import genai # This specific import might be older SDK style
# from google.genai import types # This is good
import google.generativeai as genai # More common modern SDK import for client
from ..config import settings
import logging # Added for logging
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError # Added for robustness

logger = logging.getLogger(__name__) # Added logger

class PDFReader:
    """Handles PDF reading and interaction with Gemini API."""
    
    def __init__(self, api_key=None, model_id=None):
        """Initialize PDFReader with API credentials."""
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_id = model_id or settings.GEMINI_MODEL # Ensure this is the model *name* string
        
        if not self.api_key:
            # This should be a critical error or a very loud warning if Gemini is essential
            logger.critical("GEMINI_API_KEY not found. PDFReader cannot function with Gemini.")
            raise ValueError("GEMINI_API_KEY is not configured.")
        
        # Configure the genai library with the API key
        genai.configure(api_key=self.api_key)
        
        # Initialize the GenerativeModel instance
        # The original code used self.client.models.generate_content,
        # but it's more common to create a GenerativeModel instance.
        # Let's stick to the provided client.models.generate_content for now if that's the intended SDK usage.
        # However, the `genai.Client` is not standard for the `google-generativeai` package.
        # The typical pattern is:
        # genai.configure(api_key=...)
        # self.model = genai.GenerativeModel(self.model_id)
        # And then self.model.generate_content(...)
        #
        # If `genai.Client` is from a different or older Google AI SDK, that's important.
        # Assuming `google-generativeai` (the common Python SDK for Gemini):
        # self.client = genai.Client(api_key=self.api_key) # This line is unusual for google-generativeai
        # Let's adjust to the standard `google-generativeai` pattern.
        try:
            self.model = genai.GenerativeModel(self.model_id)
            logger.info(f"PDFReader initialized with Gemini model: {self.model_id}")
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini GenerativeModel ({self.model_id}): {e}", exc_info=True)
            raise
    
    def read_pdf_from_path(self, file_path: str, use_file_api_threshold_mb: int = 18) -> dict: # Added threshold from previous version
        """
        Read PDF file from local path and return file data.
        Determines whether to use direct content upload or the File API based on size.
        """
        if not os.path.exists(file_path):
            logger.error(f"PDF file not found at {file_path}")
            # Consistent return structure even on error
            return {
                'method': None,
                'data': None,
                'path': file_path,
                'normalized_path': os.path.normpath(file_path),
                'error': f"PDF file not found at {file_path}"
            }
            
        normalized_path = os.path.normpath(file_path)
        pdf_info = {
            'method': None,
            'data': None,
            'path': file_path, # Original path
            'normalized_path': normalized_path, # Normalized path
            'error': None
        }
        
        try:
            file_size_bytes = os.path.getsize(normalized_path)
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Check file size to determine processing method
            if file_size_mb < use_file_api_threshold_mb:
                logger.info(f"PDF size ({file_size_mb:.2f}MB) is below threshold. Preparing for direct processing: {normalized_path}")
                pdf_info.update(self._prepare_direct_processing(normalized_path))
            else:
                logger.info(f"PDF size ({file_size_mb:.2f}MB) exceeds threshold. Preparing for File API processing: {normalized_path}")
                pdf_info.update(self._prepare_file_api_processing(normalized_path))
        except Exception as e:
            logger.error(f"Error preparing PDF {normalized_path}: {e}", exc_info=True)
            pdf_info['error'] = str(e)
            
        return pdf_info
    
    def _prepare_direct_processing(self, file_path: str) -> dict:
        """Prepare PDF data for direct processing."""
        with open(file_path, 'rb') as file:
            pdf_data = file.read()
        return {
            'method': 'direct',
            'data': pdf_data,
            # 'path': file_path, # path and normalized_path are already in the calling dict
            # 'normalized_path': file_path
        }
    
    def _prepare_file_api_processing(self, file_path: str) -> dict:
        """Prepare PDF for processing via File API."""
        # No data to read at this stage, just mark the method.
        # The actual upload happens when _generate_content_file_api is called.
        return {
            'method': 'file_api',
            # 'path': file_path,
            # 'normalized_path': file_path
        }
    
    def test_pdf_reading(self, pdf_info: dict) -> dict: # Added type hint
        """Test if Gemini can read the PDF by requesting a simple summary."""
        if pdf_info.get('error'): # If there was an error reading/preparing the PDF
            logger.warning(f"Skipping Gemini test for {pdf_info.get('path')} due to prior error: {pdf_info['error']}")
            return {
                'success': False,
                'error': f"Skipped due to PDF preparation error: {pdf_info['error']}",
                'pdf_info': pdf_info
            }
        
        test_prompt = "Give me a brief one-sentence description of what this PDF document is about."
        try:
            if pdf_info['method'] == 'direct':
                if not pdf_info.get('data'):
                    raise ValueError("PDF data is missing for direct processing method.")
                response = self._generate_content_direct(
                    pdf_info['data'],
                    test_prompt
                )
            elif pdf_info['method'] == 'file_api':
                if not pdf_info.get('path'):
                     raise ValueError("PDF path is missing for File API processing method.")
                response = self._generate_content_file_api(
                    pdf_info['path'], # Use original path for upload
                    test_prompt
                )
            else:
                raise ValueError(f"Unknown processing method: {pdf_info.get('method')}")
                
            return {
                'success': True,
                'summary': response.text, # Assuming response.text is how to get the content
                'pdf_info': pdf_info
            }
            
        except Exception as e:
            logger.error(f"Gemini PDF reading test failed for {pdf_info.get('path')}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'pdf_info': pdf_info
            }
    
    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _generate_content_direct(self, pdf_data: bytes, prompt: str): # Added type hints
        """Generate content using direct PDF data."""
        logger.info(f"Generating content with Gemini (direct method) for prompt: '{prompt[:50]}...'")
        # Using the standard `google-generativeai` SDK pattern with GenerativeModel instance
        # The `contents` should be a list.
        # The prompt is typically text, and the PDF data is a Part.
        
        # Create a Part for the PDF data
        pdf_part = {"mime_type": "application/pdf", "data": pdf_data}
        
        try:
            # The prompt should also be a part of the list if it's multimodal
            response = self.model.generate_content([prompt, pdf_part])
            logger.debug("Successfully generated content (direct method).")
            return response
        except Exception as e:
            logger.error(f"Error during Gemini direct content generation: {e}", exc_info=True)
            raise # Reraise for tenacity

    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _upload_to_file_api(self, file_path: str):
        """Uploads a file to Gemini File API and waits for it to be active."""
        logger.info(f"Uploading {file_path} to Gemini File API...")
        # The original code used `self.client.files.upload`.
        # With `google-generativeai`, it's `genai.upload_file`.
        uploaded_file = genai.upload_file(path=file_path) # display_name can be added
        
        logger.info(f"File {file_path} uploaded. Name: {uploaded_file.name}, URI: {uploaded_file.uri}. Waiting for processing...")
        
        # Wait for the file to be processed (ACTIVE state)
        while uploaded_file.state.name == "PROCESSING":
            # Exponential backoff for polling can be good here, or simple sleep
            # For simplicity, let's use a short sleep and rely on tenacity for overall call retry.
            import time
            time.sleep(5) # Short sleep, adjust as needed or make it configurable
            try:
                uploaded_file = genai.get_file(name=uploaded_file.name)
                logger.debug(f"File {uploaded_file.name} state: {uploaded_file.state.name}")
            except Exception as e:
                logger.error(f"Error getting file state for {uploaded_file.name}: {e}. Retrying upload if attempts left.")
                raise # Reraise to trigger tenacity for the _upload_to_file_api call

        if uploaded_file.state.name == "ACTIVE":
            logger.info(f"File {uploaded_file.name} is now ACTIVE and ready for use.")
            return uploaded_file
        else:
            # This includes FAILED or other terminal states
            error_message = f"File {uploaded_file.name} processing ended with state {uploaded_file.state.name}."
            logger.error(error_message)
            # Optionally, delete the failed file
            try:
                genai.delete_file(name=uploaded_file.name)
                logger.info(f"Deleted file {uploaded_file.name} due to non-ACTIVE state.")
            except Exception as del_e:
                logger.warning(f"Could not delete file {uploaded_file.name} after processing issue: {del_e}")
            raise Exception(error_message) # Reraise for tenacity

    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _generate_content_file_api(self, file_path: str, prompt: str): # Added type hints
        """Generate content using File API."""
        logger.info(f"Generating content with Gemini (File API method) for {file_path}, prompt: '{prompt[:50]}...'")
        
        try:
            # Upload the file (this method now handles retries and waits for ACTIVE)
            file_object = self._upload_to_file_api(file_path)
        except RetryError as e: # Catch tenacity's RetryError if all upload attempts fail
            logger.critical(f"All attempts to upload {file_path} to File API failed: {e.last_attempt.exception()}")
            raise Exception(f"Failed to upload {file_path} to File API after multiple retries.") from e
        except Exception as e: # Catch other upload exceptions
            logger.critical(f"File upload failed for {file_path}: {e}", exc_info=True)
            raise

        # Create a Part from the uploaded file object
        # The `file_object` from `genai.upload_file` or `genai.get_file` can be used directly.
        
        try:
            response = self.model.generate_content([prompt, file_object]) # Pass the file object directly
            logger.debug(f"Successfully generated content (File API method) for {file_path}.")
            return response
        except Exception as e:
            logger.error(f"Error during Gemini File API content generation for {file_path}: {e}", exc_info=True)
            # Deleting the file on generation failure might be too aggressive if the prompt was the issue.
            # Consider if this is desired. For now, let's not delete here automatically.
            raise # Reraise for tenacity