# scripts/extraction/pdf_processing/pdf_reader.py

"""Module for handling PDF reading and Gemini API integration."""

import os
import time # For waiting for File API processing
import logging
from typing import Dict, Any, Optional

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from ...config import settings

logger = logging.getLogger(__name__)

# Constants from Gemini documentation (or could be settings)
# Max size for inline data (bytes). 20MB.
DIRECT_UPLOAD_MAX_SIZE_BYTES = 20 * 1024 * 1024
# File API storage time (seconds). 48 hours.
# FILE_API_STORAGE_DURATION_SECONDS = 48 * 60 * 60 # Not directly used in logic but good to note

class PDFReader:
    """Handles PDF reading and interaction with Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model_id: Optional[str] = None):
        """Initialize PDFReader with API credentials."""
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_id = model_id or settings.GEMINI_MODEL

        if not self.api_key:
            logger.critical("GEMINI_API_KEY not found. PDFReader cannot function with Gemini.")
            raise ValueError("GEMINI_API_KEY is not configured.")

        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_id)
            logger.info(f"PDFReader initialized with Gemini model: {self.model_id}")
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini GenerativeModel ({self.model_id}): {e}", exc_info=True)
            raise

    def read_pdf_from_path(self, file_path: str, use_file_api_threshold_mb: int = 18) -> Dict[str, Any]:
        """
        Read PDF file from local path and return file data for Gemini processing.
        Determines whether to use direct content upload or the File API based on size.

        Args:
            file_path: Path to the source PDF file.
            use_file_api_threshold_mb: Threshold in MB. Files larger than this will use File API.
                                       Gemini direct limit is 20MB for the *total request*.
                                       A threshold slightly lower (e.g., 18-19MB) for the PDF itself
                                       leaves room for the prompt and other metadata.

        Returns:
            A dictionary containing processing method, data/path, and any errors.
            Keys: 'method' (str), 'data' (bytes|None), 'path' (str|None),
                  'normalized_path' (str), 'error' (str|None).
        """
        if not os.path.exists(file_path):
            logger.error(f"PDF file not found at {file_path}")
            return {
                'method': None,
                'data': None,
                'path': file_path,
                'normalized_path': os.path.normpath(file_path),
                'error': f"PDF file not found at {file_path}"
            }

        normalized_path = os.path.normpath(file_path)
        pdf_info: Dict[str, Any] = {
            'method': None,
            'data': None,
            'path': file_path,
            'normalized_path': normalized_path,
            'error': None
        }

        try:
            file_size_bytes = os.path.getsize(normalized_path)
            file_size_mb = file_size_bytes / (1024 * 1024)

            # Gemini has a 20MB limit for *total request size* for inline data.
            # The File API supports up to 50MB for PDF files.
            # We use `use_file_api_threshold_mb` to decide.
            if file_size_bytes < (use_file_api_threshold_mb * 1024 * 1024) and file_size_bytes < DIRECT_UPLOAD_MAX_SIZE_BYTES:
                logger.info(f"PDF size ({file_size_mb:.2f}MB) is suitable for direct processing: {normalized_path}")
                pdf_info.update(self._prepare_direct_processing(normalized_path))
            else:
                logger.info(f"PDF size ({file_size_mb:.2f}MB) requires File API processing: {normalized_path}")
                pdf_info.update(self._prepare_file_api_processing(normalized_path)) # Path is already in pdf_info

        except Exception as e:
            logger.error(f"Error preparing PDF {normalized_path}: {e}", exc_info=True)
            pdf_info['error'] = str(e)

        return pdf_info

    def _prepare_direct_processing(self, file_path: str) -> Dict[str, Any]:
        """Prepare PDF data for direct processing (inline)."""
        try:
            with open(file_path, 'rb') as file:
                pdf_data = file.read()
            return {
                'method': 'direct',
                'data': pdf_data,
                'error': None
            }
        except Exception as e:
            logger.error(f"Failed to read PDF for direct processing {file_path}: {e}", exc_info=True)
            return {
                'method': 'direct',
                'data': None,
                'error': f"Failed to read PDF for direct processing: {str(e)}"
            }

    def _prepare_file_api_processing(self, file_path: str) -> Dict[str, Any]:
        """Prepare PDF for processing via File API."""
        # Actual upload happens in _generate_content_file_api
        # Just mark the method and confirm path.
        return {
            'method': 'file_api',
            'path': file_path, # Ensure path is explicitly set for this method
            'error': None
        }

    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _generate_content_direct(self, pdf_data: bytes, prompt: str) -> genai.types.GenerateContentResponse:
        """Generate content using direct PDF data (inline)."""
        logger.info(f"Generating content with Gemini (direct method). Prompt: '{prompt[:50]}...'")
        if not pdf_data:
            logger.error("Cannot generate content: PDF data is empty for direct method.")
            raise ValueError("PDF data is empty for direct method.")

        pdf_part = {"mime_type": "application/pdf", "data": pdf_data}
        try:
            response = self.model.generate_content([prompt, pdf_part])
            logger.debug("Successfully generated content (direct method).")
            return response
        except Exception as e:
            logger.error(f"Error during Gemini direct content generation: {e}", exc_info=True)
            raise # Reraise for tenacity

    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3), reraise=True) # Longer max wait for upload
    def _upload_to_file_api(self, file_path: str) -> genai.types.File:
        """Uploads a file to Gemini File API and waits for it to be active."""
        logger.info(f"Uploading {file_path} to Gemini File API...")
        # display_name is optional, can be file_path or os.path.basename(file_path)
        uploaded_file = genai.upload_file(path=file_path, display_name=os.path.basename(file_path))
        logger.info(f"File {file_path} uploaded. Name: {uploaded_file.name}, URI: {uploaded_file.uri}. Waiting for processing...")

        # Wait for the file to be processed (ACTIVE state)
        # Polling with backoff/timeout
        poll_interval = 5  # seconds
        max_wait_time = 300  # 5 minutes
        elapsed_time = 0

        while uploaded_file.state.name == "PROCESSING" and elapsed_time < max_wait_time:
            time.sleep(poll_interval)
            elapsed_time += poll_interval
            try:
                uploaded_file = genai.get_file(name=uploaded_file.name)
                logger.debug(f"File {uploaded_file.name} state: {uploaded_file.state.name} (waited {elapsed_time}s)")
            except Exception as e:
                logger.warning(f"Error getting file state for {uploaded_file.name} during polling: {e}. Will retry if upload attempts left.")
                raise # Reraise to trigger tenacity for the _upload_to_file_api call

        if uploaded_file.state.name == "ACTIVE":
            logger.info(f"File {uploaded_file.name} is now ACTIVE and ready for use.")
            return uploaded_file
        else:
            error_message = f"File {uploaded_file.name} processing ended with state {uploaded_file.state.name} (or timed out)."
            logger.error(error_message)
            # Optionally, delete the failed file if not ACTIVE
            if uploaded_file.state.name != "ACTIVE": # e.g. FAILED
                try:
                    genai.delete_file(name=uploaded_file.name)
                    logger.info(f"Deleted file {uploaded_file.name} due to non-ACTIVE state: {uploaded_file.state.name}.")
                except Exception as del_e: # pragma: no cover
                    logger.warning(f"Could not delete file {uploaded_file.name} after processing issue: {del_e}")
            raise Exception(error_message) # Reraise for tenacity

    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
    def _generate_content_file_api(self, file_path: str, prompt: str) -> genai.types.GenerateContentResponse:
        """Generate content using File API."""
        logger.info(f"Generating content with Gemini (File API method) for {file_path}. Prompt: '{prompt[:50]}...'")
        if not file_path:
            logger.error("Cannot generate content: file_path is empty for File API method.")
            raise ValueError("file_path is empty for File API method.")

        file_object = None
        try:
            file_object = self._upload_to_file_api(file_path) # This method handles retries and waits for ACTIVE
            response = self.model.generate_content([prompt, file_object]) # Pass the file object directly
            logger.debug(f"Successfully generated content (File API method) for {file_path}.")
            return response
        except RetryError as e: # Catch tenacity's RetryError if all upload attempts fail
            logger.critical(f"All attempts to upload/process {file_path} with File API failed: {e.last_attempt.exception() if e.last_attempt else e}") # type: ignore
            raise Exception(f"Failed to upload/process {file_path} with File API after multiple retries.") from e
        except Exception as e: # Catch other exceptions during generation
            logger.error(f"Error during Gemini File API content generation for {file_path}: {e}", exc_info=True)
            raise # Reraise for tenacity
        finally:
            # Clean up the file from File API after use, if desired and successful.
            # Gemini files are auto-deleted after 48 hours.
            # For this application, explicit deletion might be good practice if the file is processed.
            # However, if generation fails, keeping it for debugging might be useful.
            # Let's not delete automatically here to allow for retries or inspection.
            # If deletion is needed, it should be handled by the caller or a cleanup process.
            # if file_object:
            #     try:
            #         genai.delete_file(name=file_object.name)
            #         logger.info(f"Deleted file {file_object.name} from File API after processing.")
            #     except Exception as del_e:
            #         logger.warning(f"Could not delete file {file_object.name} from File API: {del_e}")
            pass

    def test_pdf_reading(self, pdf_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test if Gemini can read the PDF by requesting a simple summary.
        This method calls the actual Gemini generation.

        Args:
            pdf_info: The dictionary returned by `read_pdf_from_path`.

        Returns:
            A dictionary with 'success' (bool), 'summary' (str, if successful),
            'error' (str, if failed), and the original 'pdf_info'.
        """
        if pdf_info.get('error'):
            logger.warning(f"Skipping Gemini test for {pdf_info.get('path', 'unknown PDF')} due to prior error: {pdf_info['error']}")
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
                response = self._generate_content_direct(pdf_info['data'], test_prompt)
            elif pdf_info['method'] == 'file_api':
                if not pdf_info.get('path'):
                     raise ValueError("PDF path is missing for File API processing method.")
                response = self._generate_content_file_api(pdf_info['path'], test_prompt)
            else:
                raise ValueError(f"Unknown processing method: {pdf_info.get('method')}")

            return {
                'success': True,
                'summary': response.text,
                'pdf_info': pdf_info
            }

        except Exception as e:
            logger.error(f"Gemini PDF reading test failed for {pdf_info.get('path', 'unknown PDF')}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'pdf_info': pdf_info
            }