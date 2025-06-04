# scripts/extraction/tests/test_image_extractor_refactored.py

"""Unit tests for the refactored ImageExtractor (coordinator)."""

import unittest
from unittest.mock import MagicMock, patch, call
import os
import tempfile
import shutil
import time
# Import fitz - Added to fix Pylance "fitz" is not defined error
import fitz
from typing import Dict, Any # Added Any for type hints in Mock classes

# Import the refactored ImageExtractor and its components
from ..image_extractor import ImageExtractor
# from ..extraction_strategies.base_strategy import BaseExtractionStrategy # Keep if StrategyTuple needed
from ..retry_coordinator import RetryCoordinator
from ..image_processor import ImageProcessor
from ..extraction_reporter import ExtractionReporter
# Assuming utils is two levels up
# from ...utils.image_validation import ImageValidator, ImageIssueType # Original
from ...utils.image_validation import ImageValidator, ImageIssueType # Adjusted import based on test location

# Mock settings for configuration
class MockSettings:
    IMAGE_EXTRACTION_CONFIG = {
        "dpi": 150,
        "image_format": "png",
        "quality": 95,
        "max_width": 1920,
        "max_height": 1080,
        "min_width": 50,
        "min_height": 50,
        "supported_formats": ["png", "jpg", "jpeg"],
        "validate_images": True,
        "retry_failed_extractions": True,
        "max_extraction_retries": 3,
    }

# Mock dependent components
# Mock ImageValidator (used by ImageProcessor)
class MockImageValidator:
    def __init__(self, *args: Any, **kwargs: Any) -> None: # Added type hints
        self.is_valid = True
        self.details = None
        self.issue_type = None
        self.metrics = {"size": "100x100", "format": "png", 'is_valid': True} # Default valid metrics and include is_valid

    def validate_image_file(self, path: str) -> MagicMock: # Added type hints
        # Return a mock ValidationResult object
        mock_result = MagicMock()
        mock_result.is_valid = self.is_valid
        mock_result.details = self.details
        mock_result.issue_type = self.issue_type
        mock_result.metrics = self.metrics.copy() # Return a copy to avoid modification issues
        mock_result.metrics['is_valid'] = self.is_valid # Ensure is_valid is in metrics too for reporter
        return mock_result

class MockImageProcessor:
    def __init__(self, config: Dict[str, Any]) -> None: # Added type hints
        self.config = config
        self.image_format = config.get("image_format", "png").lower()
        self.process_and_save_result = {
            'success': True,
            'path': '/fake/path/image.png', # Placeholder
            'issue': None,
            'issue_type': None,
            'validation_info': {'size': '100x100', 'format': 'png', 'is_valid': True},
            'processing_details': {}
        }
        # Store calls for assertion
        self.process_and_save_calls: list[Any] = [] # Added type hints

    def process_and_save_image(self, image: MagicMock, output_path: str) -> Dict[str, Any]: # Added type hints
        self.process_and_save_calls.append((image, output_path))
        # Simulate saving by creating a dummy file
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                 f.write("dummy image content")
            process_result = self.process_and_save_result.copy() # Return a copy
            process_result['path'] = output_path # Update path in result copy
            process_result['processing_details']['saved'] = True
        except Exception as e:
             process_result = {'success': False, 'path': output_path, 'issue': f"Mock save failed: {e}", 'issue_type': "mock_save_error", 'validation_info': {}, 'processing_details': {}}

        return process_result

class MockRetryCoordinator:
    def __init__(self, strategies: list[Any], config: Dict[str, Any]) -> None: # Added type hints
        self.strategies = strategies # Store for inspection if needed
        self.config = config
        # Default success scenario: return a mock PIL Image and success info
        self.coord_result: tuple[MagicMock | None, Dict[str, Any]] = (MagicMock(), {'success': True, 'attempt_count': 1, 'attempts': [{'strategy': 'standard', 'success': True, 'details': {'dimensions': '100x100', 'mode': 'RGB'}}], 'duration': 0.01}) # Added type hints
        self._call_count = 0 # Track how many times coordinate_extraction is called
        self._side_effect: list[tuple[MagicMock | None, Dict[str, Any]]] | None = None # Added type hints # For configuring different results per call

    def set_side_effect(self, side_effect_list: list[tuple[MagicMock | None, Dict[str, Any]]]) -> None: # Added type hints
         self._side_effect = side_effect_list
         self._call_count = 0 # Reset call count when side effect is set

    def coordinate_extraction(self, pdf_document: MagicMock, img_info: tuple, page_num: int, img_index: int, initial_extraction_info: Dict[str, Any]) -> tuple[MagicMock | None, Dict[str, Any]]: # Added type hints
        if self._side_effect:
            result = self._side_effect[self._call_count]
            self._call_count += 1
            return result
        else:
            self._call_count += 1
            return self.coord_result

class MockExtractionReporter:
    def __init__(self, config: Dict[str, Any]) -> None: # Added type hints
        self.config = config
        self.metrics: Dict[str, Any] = {} # Simplified for mock # Added type hints
        self.problematic_images: list[Dict[str, Any]] = [] # Simplified for mock # Added type hints
        self.errors: list[str] = [] # Simplified for mock # Added type hints
        self.start_time: float | None = None # Added type hints
        self.extracted_count = 0
        self.failed_count = 0
        self.final_report_summary: Dict[str, Any] = {'success': True, 'extracted_count': 0, 'failed_count': 0, 'problematic_count': 0, 'metrics': {}, 'problematic_images': [], 'errors': [], 'report_text': 'Mock Report'} # Added type hints

        # Store calls for assertion
        self.start_doc_calls: list[Any] = [] # Added type hints
        self.track_attempt_calls: list[Any] = [] # Added type hints
        self.track_result_calls: list[Any] = [] # Added type hints
        self.finalize_calls: list[Any] = [] # Added type hints


    def start_document_report(self, pdf_path: str) -> None: # Added type hints
        self.start_doc_calls.append(pdf_path)
        self.start_time = time.time() # Simulate start
        self.metrics = {} # Reset
        self.problematic_images = [] # Reset
        self.errors = [] # Reset
        self.extracted_count = 0
        self.failed_count = 0

    def track_image_attempt(self, img_info: tuple) -> None: # Added type hints
        self.track_attempt_calls.append(img_info)

    def track_extraction_result(self, extraction_info: Dict[str, Any], processing_result: Dict[str, Any]) -> None: # Added type hints
        self.track_result_calls.append((extraction_info, processing_result))
        # Simulate basic counting for the final summary
        if extraction_info.get('success') and processing_result.get('success'):
            self.extracted_count += 1
        else:
            self.failed_count += 1
            # Add minimal problematic image info for problematic_count check
            prob_img_info = {'page': extraction_info.get('page', '?'), 'index_on_page': extraction_info.get('index_on_page', '?'), 'issue': extraction_info.get('final_error', processing_result.get('issue', 'Unknown'))}
            self.problematic_images.append(prob_img_info)
            if extraction_info.get('final_error'):
                 self.errors.append(extraction_info['final_error'])
            elif processing_result.get('issue'):
                 self.errors.append(processing_result['issue'])


    def finalize_report(self, output_dir: str | None = None) -> Dict[str, Any]: # Added type hints
        self.finalize_calls.append(output_dir)
        # Simulate finalizing report with counts
        final_summary = self.final_report_summary.copy()
        final_summary['extracted_count'] = self.extracted_count
        final_summary['failed_count'] = self.failed_count
        final_summary['problematic_count'] = len(self.problematic_images)
        final_summary['errors'] = self.errors
        final_summary['problematic_images'] = self.problematic_images
        # Basic success check (can be refined based on actual reporter logic)
        final_summary['success'] = (self.failed_count == 0) if (self.extracted_count + self.failed_count) > 0 else True
        if (self.extracted_count + self.failed_count) > 0:
             final_summary['failure_ratio'] = self.failed_count / (self.extracted_count + self.failed_count)

        # Simulate saving report if output_dir is provided
        if output_dir:
            final_summary['report_path'] = os.path.join(output_dir, 'mock_report.md')
            os.makedirs(output_dir, exist_ok=True)
            with open(final_summary['report_path'], 'w') as f:
                f.write(final_summary['report_text'])

        return final_summary


# Patch the dependencies at the module level
@patch('scripts.extraction.image_extractor.ExtractionReporter', new=MockExtractionReporter)
@patch('scripts.extraction.image_extractor.ImageProcessor', new=MockImageProcessor)
@patch('scripts.extraction.image_extractor.RetryCoordinator', new=MockRetryCoordinator)
@patch('scripts.extraction.image_extractor.settings', new=MockSettings)
@patch('scripts.extraction.image_processor.ImageValidator', new=MockImageValidator) # Also patch validator used by ImageProcessor
class TestImageExtractorRefactored(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None: # Added type hint
        # Create a dummy PDF file path (content not needed for these mocks)
        cls.temp_dir = tempfile.mkdtemp()
        cls.dummy_pdf_path = os.path.join(cls.temp_dir, "dummy.pdf")
        with open(cls.dummy_pdf_path, 'w') as f:
            f.write("%PDF-1.0\n...\n%%EOF") # Minimal PDF structure indicator

    @classmethod
    def tearDownClass(cls) -> None: # Added type hint
        shutil.rmtree(cls.temp_dir)

    def setUp(self) -> None: # Added type hint
        # Get the mock instances created by the patched __init__ calls
        # These instances persist across test methods unless explicitly reset
        # We need to reset their call trackers and behaviors for each test
        self.mock_reporter: MockExtractionReporter = MockExtractionReporter.return_value # Use the mocked class's return_value attribute # Added type hint
        self.mock_processor: MockImageProcessor = MockImageProcessor.return_value # Added type hint
        self.mock_coordinator: MockRetryCoordinator = MockRetryCoordinator.return_value # Added type hint

        # Reset mock states before each test
        self.mock_reporter.start_doc_calls = []
        self.mock_reporter.track_attempt_calls = []
        self.mock_reporter.track_result_calls = []
        self.mock_reporter.finalize_calls = []
        self.mock_reporter.extracted_count = 0
        self.mock_reporter.failed_count = 0
        self.mock_reporter.problematic_images = []
        self.mock_reporter.errors = []

        self.mock_processor.process_and_save_calls = []
        self.mock_processor.process_and_save_result = {'success': True, 'path': '/fake/path', 'issue': None, 'issue_type': None, 'validation_info': {'is_valid': True}, 'processing_details': {}}


        self.mock_coordinator._call_count = 0
        self.mock_coordinator._side_effect = None # Clear side effect
        # Reset default result to a success
        self.mock_coordinator.coord_result = (MagicMock(), {'success': True, 'attempt_count': 1, 'attempts': [{'strategy': 'standard', 'success': True, 'details': {'dimensions': '100x100', 'mode': 'RGB'}}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10})


    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs')
    def test_extraction_pipeline_success(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None: # Added type hints
        """Test end-to-end pipeline with all images successfully extracted and processed."""
        # Configure mock fitz document
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1 # 1 page
        mock_page = MagicMock()
        # Simulate 2 images found
        mock_img_list = [(10, ...), (20, ...)]
        mock_page.get_images.return_value = mock_img_list
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.close.return_value = None
        mock_fitz_open.return_value = mock_doc

        # Configure mocks for success
        self.mock_coordinator.set_side_effect([
            (MagicMock(), {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10}),
            (MagicMock(), {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.02, 'page': 1, 'index_on_page': 1, 'xref': 20})
        ])
        self.mock_processor.process_and_save_result = {'success': True, 'path': '/fake/path', 'issue': None, 'issue_type': None, 'validation_info': {'is_valid': True}, 'processing_details': {}}


        extractor = ImageExtractor()
        output_dir = os.path.join(self.temp_dir, "output_success")
        results = extractor.extract_images_from_pdf(self.dummy_pdf_path, output_dir)

        # Assertions for component interactions
        self.mock_reporter.start_document_report.assert_called_once_with(self.dummy_pdf_path)
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_fitz_open.assert_called_once_with(self.dummy_pdf_path)
        mock_doc.__getitem__.assert_called_once_with(0) # Page 0
        mock_page.get_images.assert_called_once_with(full=True)

        self.assertEqual(len(self.mock_reporter.track_attempt_calls), 2) # Called for each image found

        # Coordinator should be called for each image
        self.assertEqual(self.mock_coordinator._call_count, 2)
        self.mock_coordinator.coordinate_extraction.assert_has_calls([
             call(mock_doc, mock_img_list[0], 1, 0, {'global_image_counter': 1}),
             call(mock_doc, mock_img_list[1], 1, 1, {'global_image_counter': 2}),
        ])

        # Processor should be called for each image (since extraction succeeded)
        self.assertEqual(len(self.mock_processor.process_and_save_calls), 2)
        self.assertIn(os.path.join(output_dir, 'fig1-page1-img1.png'), self.mock_processor.process_and_save_calls[0][1])
        self.assertIn(os.path.join(output_dir, 'fig2-page1-img2.png'), self.mock_processor.process_and_save_calls[1][1])


        # Reporter should track results for each image
        self.assertEqual(len(self.mock_reporter.track_result_calls), 2)
        # Reporter should finalize
        self.mock_reporter.finalize_calls.assert_called_once_with(output_dir)
        mock_doc.close.assert_called_once() # Document should be closed

        # Check final results returned by reporter
        self.assertTrue(results['success'])
        self.assertEqual(results['extracted_count'], 2)
        self.assertEqual(results['failed_count'], 0)
        self.assertEqual(results['problematic_count'], 0)


    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs')
    def test_extraction_pipeline_with_failures(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None: # Added type hints
        """Test pipeline with a mix of extraction/processing failures."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1 # 1 page
        # Simulate 3 images found
        mock_img_list = [(10, ...), (20, ...), (30, ...)]
        mock_page = MagicMock()
        mock_page.get_images.return_value = mock_img_list
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.close.return_value = None
        mock_fitz_open.return_value = mock_doc

        # Configure mocks:
        # Image 1: Success
        # Image 2: Extraction Failure
        # Image 3: Extraction Success, Processing Failure (Validation)

        coord_side_effect: list[tuple[MagicMock | None, Dict[str, Any]]] = [ # Added type hint
            (MagicMock(), {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10}), # Image 1 Success
            (None, {'success': False, 'attempt_count': 2, 'attempts': [{}, {}], 'duration': 0.05, 'page': 1, 'index_on_page': 1, 'xref': 20, 'final_error': 'Coord Fail', 'issue_type': 'extraction_failed'}), # Image 2 Fail
            (MagicMock(), {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.02, 'page': 1, 'index_on_page': 2, 'xref': 30}) # Image 3 Success (from coord)
        ]
        self.mock_coordinator.set_side_effect(coord_side_effect)


        # Processor calls for Image 1 and Image 3
        process_save_side_effect: list[Dict[str, Any]] = [ # Added type hint
            {'success': True, 'path': '/fake/path/1.png', 'issue': None, 'issue_type': None, 'validation_info': {'is_valid': True}, 'processing_details': {}}, # Image 1 Process Success
            {'success': False, 'path': '/fake/path/3.png', 'issue': 'Proc Fail', 'issue_type': 'size_issues', 'validation_info': {'is_valid': False}, 'processing_details': {}} # Image 3 Process Fail
        ]
        self.mock_processor.process_and_save_image = MagicMock(side_effect=process_save_side_effect)


        extractor = ImageExtractor()
        output_dir = os.path.join(self.temp_dir, "output_failures")
        results = extractor.extract_images_from_pdf(self.dummy_pdf_path, output_dir)

        # Assertions
        self.assertEqual(self.mock_coordinator._call_count, 3) # Called for all 3 images
        # Processor should only be called for images where extraction succeeded (Image 1, Image 3)
        self.assertEqual(self.mock_processor.process_and_save_image.call_count, 2)

        # Reporter should track results for all 3 images
        self.assertEqual(len(self.mock_reporter.track_result_calls), 3)
        # Check how the mock reporter counted them:
        # Image 1: Success (Coord Success, Proc Success) -> extracted_count += 1
        # Image 2: Failure (Coord Fail) -> failed_count += 1, problematic_images += 1, errors += 1
        # Image 3: Failure (Coord Success, Proc Fail) -> extracted_count += 1, failed_count += 1, problematic_images += 1, errors += 1
        # Total: extracted_count = 2, failed_count = 2, problematic_count = 2, errors = 2
        self.assertEqual(self.mock_reporter.extracted_count, 2)
        self.assertEqual(self.mock_reporter.failed_count, 2)
        self.assertEqual(len(self.mock_reporter.problematic_images), 2)
        self.assertEqual(len(self.mock_reporter.errors), 2)

        # Final results should reflect failures
        # 2 failures out of 3 attempts = 0.66 failure ratio > 0.25
        self.assertFalse(results['success'])
        self.assertEqual(results['extracted_count'], 2) # Matches mock reporter's successful_extractions count logic
        self.assertEqual(results['failed_count'], 2) # Matches mock reporter's failed_count logic
        self.assertEqual(results['problematic_count'], 2) # Matches mock reporter's problematic_images count

        self.mock_reporter.finalize_calls.assert_called_once_with(output_dir)
        mock_doc.close.assert_called_once()


    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs')
    def test_pdf_error_handling(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None: # Added type hints
        """Test graceful handling when opening PDF fails."""
        mock_fitz_open.side_effect = fitz.FileNotFoundError("Mock PDF not found")

        extractor = ImageExtractor()
        output_dir = os.path.join(self.temp_dir, "output_pdf_error")
        results = extractor.extract_images_from_pdf("/non/existent/pdf", output_dir)

        # Assertions
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_fitz_open.assert_called_once_with("/non/existent/pdf")

        # No further calls should be made to coordinator or processor
        self.assertEqual(self.mock_coordinator._call_count, 0)
        self.assertEqual(len(self.mock_processor.process_and_save_calls), 0)

        # Reporter should have captured the error and finalized
        self.assertEqual(len(self.mock_reporter.errors), 1)
        self.assertIn("PDF file not found", self.mock_reporter.errors[0])
        self.mock_reporter.finalize_calls.assert_called_once_with(output_dir)

        # Final results should indicate failure
        self.assertFalse(results['success'])
        self.assertEqual(results['extracted_count'], 0)
        self.assertEqual(results['failed_count'], 0) # Based on how mock reporter handles this case
        self.assertEqual(results['problematic_count'], 0) # No images were processed to be problematic


    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs', side_effect=OSError("Mock mkdir failed"))
    def test_makedirs_error_handling(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None: # Added type hints
        """Test graceful handling when output directory creation fails."""
        extractor = ImageExtractor()
        output_dir = "/invalid/output/dir"
        results = extractor.extract_images_from_pdf(self.dummy_pdf_path, output_dir)

        # Assertions
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        # fitz.open should NOT be called
        mock_fitz_open.assert_not_called()

        # No further calls
        self.assertEqual(self.mock_coordinator._call_count, 0)
        self.assertEqual(len(self.mock_processor.process_and_save_calls), 0)

        # Reporter should have captured the error and finalized
        self.assertEqual(len(self.mock_reporter.errors), 1)
        self.assertIn("Failed to create output directory", self.mock_reporter.errors[0])
        self.mock_reporter.finalize_calls.assert_called_once_with(output_dir)

        # Final results should indicate failure
        self.assertFalse(results['success'])
        self.assertEqual(results['extracted_count'], 0)
        self.assertEqual(results['failed_count'], 0)
        self.assertEqual(results['problematic_count'], 0)

if __name__ == '__main__':
    unittest.main()