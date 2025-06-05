# scripts/extraction/tests/test_image_extractor_refactored.py

"""Unit tests for the refactored ImageExtractor (coordinator)."""

import unittest
from unittest.mock import MagicMock, patch, call
import os
import tempfile
import shutil
import time
import fitz # PyMuPDF
from typing import Dict, Any, List, Tuple

# DO NOT import ImageExtractor at the top level of the test file.
# from scripts.extraction.image_extractor import ImageExtractor 

# Import the original classes for type hinting or reference if needed.
# These are NOT the patch targets for ImageExtractor's direct dependencies anymore.
from scripts.extraction.extraction_reporter import ExtractionReporter as OriginalExtractionReporter
from scripts.extraction.image_processor import ImageProcessor as OriginalImageProcessor
from scripts.extraction.retry_coordinator import RetryCoordinator as OriginalRetryCoordinator
from scripts.config import settings as original_settings
from scripts.utils.image_validation import ImageValidator as OriginalImageValidator


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
        "report_path": "extraction_reports"
    }

# Mock dependent components
class MockImageValidator:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.is_valid = True
        self.details = None
        self.issue_type = None
        self.metrics = {"size": "100x100", "format": "png", 'is_valid': True}

    def validate_image_file(self, path: str) -> MagicMock:
        mock_result = MagicMock()
        mock_result.is_valid = self.is_valid
        mock_result.details = self.details
        mock_result.issue_type = self.issue_type
        mock_result.metrics = self.metrics.copy()
        mock_result.metrics['is_valid'] = self.is_valid
        return mock_result

class MockImageProcessor:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.image_format = config.get("image_format", "png").lower()
        self.process_and_save_result_template: Dict[str, Any] = {
            'success': True,
            'issue': None,
            'issue_type': None,
            'validation_info': {'size': '100x100', 'format': self.image_format, 'is_valid': True},
            'processing_details': {}
        }
        self.process_and_save_calls: List[Tuple[MagicMock, str]] = []

    def process_and_save_image(self, image: MagicMock, output_path: str) -> Dict[str, Any]:
        self.process_and_save_calls.append((image, output_path))
        process_result = self.process_and_save_result_template.copy()
        process_result['path'] = output_path

        if self.process_and_save_result_template.get('success', True):
            try:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write("dummy image content")
                process_result['processing_details']['saved'] = True
            except Exception as e:
                process_result = {'success': False, 'path': output_path, 'issue': f"Mock save failed: {e}", 'issue_type': "mock_save_error", 'validation_info': {}, 'processing_details': {}}
        else: 
            process_result['success'] = False
        return process_result

class MockRetryCoordinator:
    def __init__(self, strategies: List[Any], config: Dict[str, Any]) -> None:
        self.strategies = strategies
        self.config = config
        
        default_mock_image = MagicMock()
        default_mock_image.close = MagicMock()

        self.coord_result: Tuple[MagicMock | None, Dict[str, Any]] = (
            default_mock_image,
            {'success': True, 'attempt_count': 1, 'attempts': [{'strategy': 'standard', 'success': True, 'details': {'dimensions': '100x100', 'mode': 'RGB'}}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10, 'final_error': None}
        )
        self._call_count = 0
        self._side_effect: List[Tuple[MagicMock | None, Dict[str, Any]]] | None = None
        self.coordinate_extraction_calls: List[Any] = []


    def set_side_effect(self, side_effect_list: List[Tuple[MagicMock | None, Dict[str, Any]]]) -> None:
         processed_side_effect = []
         for img_mock, info in side_effect_list:
             if img_mock is not None and isinstance(img_mock, MagicMock):
                 if not hasattr(img_mock, 'close') or not callable(getattr(img_mock, 'close', None)):
                     img_mock.close = MagicMock()
             processed_side_effect.append((img_mock, info))
         self._side_effect = processed_side_effect
         self._call_count = 0 

    def coordinate_extraction(self, pdf_document: MagicMock, img_info: tuple, page_num: int, img_index: int, initial_extraction_info: Dict[str, Any]) -> Tuple[MagicMock | None, Dict[str, Any]]:
        self.coordinate_extraction_calls.append( (pdf_document, img_info, page_num, img_index, initial_extraction_info) )
        result_img_mock, result_info_template = None, {}
        
        current_call_idx = self._call_count
        # CORRECTED: len(self._side_effect) instead of len(self.side_effect)
        if self._side_effect and current_call_idx < len(self._side_effect):
            result_img_mock, result_info_template = self._side_effect[current_call_idx]
        else: 
            result_img_mock, result_info_template = self.coord_result
        
        self._call_count += 1
        result_info = result_info_template.copy() 

        if result_img_mock is not None and isinstance(result_img_mock, MagicMock):
            if not hasattr(result_img_mock, 'close') or not callable(getattr(result_img_mock, 'close', None)):
                result_img_mock.close = MagicMock() 
        
        result_info.setdefault('success', False)
        result_info.setdefault('page', page_num)
        result_info.setdefault('index_on_page', img_index)
        result_info.setdefault('xref', img_info[0] if isinstance(img_info, tuple) and len(img_info) > 0 else 'unknown_xref')

        return result_img_mock, result_info

class MockExtractionReporter:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.metrics: Dict[str, Any] = {"total_images_in_doc": 0}
        self.problematic_images: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.start_time: float | None = None
        self.extracted_count = 0
        self.failed_count = 0
        self.final_report_summary_template: Dict[str, Any] = {'success': True, 'extracted_count': 0, 'failed_count': 0, 'problematic_count': 0, 'metrics': {}, 'problematic_images': [], 'errors': [], 'report_text': 'Mock Report'}

        self.start_doc_calls: List[str] = []
        self.track_attempt_calls: List[tuple] = []
        self.track_result_calls: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        self.finalize_calls: List[str | None] = []

    def start_document_report(self, pdf_path: str) -> None:
        self.start_doc_calls.append(pdf_path)
        self.start_time = time.time()
        self.metrics = {"total_images_in_doc": 0} 
        self.problematic_images = []
        self.errors = []
        self.extracted_count = 0
        self.failed_count = 0

    def track_image_attempt(self, img_info: tuple) -> None:
        self.track_attempt_calls.append(img_info)
        self.metrics["total_images_in_doc"] = self.metrics.get("total_images_in_doc", 0) + 1

    def track_extraction_result(self, extraction_info: Dict[str, Any], processing_result: Dict[str, Any]) -> None:
        self.track_result_calls.append((extraction_info, processing_result))
        
        is_successful_extraction = extraction_info.get('success', False)
        is_successful_processing = processing_result.get('success', False)

        if is_successful_extraction and is_successful_processing:
            self.extracted_count += 1
        else:
            self.failed_count += 1
            prob_img_info = {
                'page': extraction_info.get('page', '?'),
                'index_on_page': extraction_info.get('index_on_page', '?'),
                'issue': extraction_info.get('final_error') or processing_result.get('issue', 'Unknown error'),
                'xref': extraction_info.get('xref', '?')
            }
            self.problematic_images.append(prob_img_info)
            
            current_error = None
            if not is_successful_extraction and extraction_info.get('final_error'):
                current_error = extraction_info['final_error']
            elif not is_successful_processing and processing_result.get('issue'):
                # Avoid double-reporting if extraction failed and processing was skipped due to that failure
                if not (not is_successful_extraction and processing_result.get('issue_type') == 'processing_skipped_extraction_failed'):
                    current_error = processing_result['issue']
            
            if current_error and str(current_error) not in self.errors: # Ensure current_error is string for list check
                self.errors.append(str(current_error))


    def finalize_report(self, output_dir: str | None = None) -> Dict[str, Any]:
        self.finalize_calls.append(output_dir)
        final_summary = self.final_report_summary_template.copy()
        final_summary['extracted_count'] = self.extracted_count
        final_summary['failed_count'] = self.failed_count
        final_summary['problematic_count'] = len(self.problematic_images)
        final_summary['errors'] = list(self.errors) 
        final_summary['problematic_images'] = list(self.problematic_images) 
        final_summary['metrics'] = self.metrics.copy()

        if any(e for e in self.errors if "PDF file not found" in str(e) or "Failed to create output directory" in str(e)): # Ensure str(e) for safety
             final_summary['success'] = False
        elif self.metrics.get("total_images_in_doc", 0) > 0 : 
            final_summary['success'] = (self.failed_count == 0 and not self.errors)
        elif self.errors: 
            final_summary['success'] = False
        else: 
            final_summary['success'] = True

        total_attempted = self.metrics.get("total_images_in_doc", 0)
        if total_attempted > 0:
             final_summary['failure_ratio'] = self.failed_count / total_attempted
        else: 
            final_summary['failure_ratio'] = 0.0 if not self.errors else 1.0 

        if output_dir: 
            report_file_name = self.config.get("report_file_name", "extraction_report.md")
            final_summary['report_path'] = os.path.join(output_dir, report_file_name)
        return final_summary

# Patch dependencies at their source location, so ImageExtractor imports the mocks.
@patch('scripts.config.settings', new=MockSettings)
@patch('scripts.extraction.retry_coordinator.RetryCoordinator', new=MockRetryCoordinator)
@patch('scripts.extraction.image_processor.ImageProcessor', new=MockImageProcessor)
@patch('scripts.extraction.extraction_reporter.ExtractionReporter', new=MockExtractionReporter) 
# This patch is for ImageProcessor's dependency, if ImageProcessor itself wasn't mocked.
@patch('scripts.extraction.image_processor.ImageValidator', new=MockImageValidator)
class TestImageExtractorRefactored(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.mkdtemp()
        cls.dummy_pdf_path = os.path.join(cls.temp_dir, "dummy.pdf")
        try:
            doc = fitz.open() 
            doc.new_page()
            doc.save(cls.dummy_pdf_path)
            doc.close()
        except Exception as e:
            print(f"Warning: Could not create dummy PDF with fitz: {e}. Using basic text PDF.")
            with open(cls.dummy_pdf_path, 'w') as f:
                 f.write("%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\nxref\n0 3\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n92\n%%EOF")


    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_dir)

    def setUp(self) -> None:
        # Import ImageExtractor HERE, after patches are active due to class decorators
        from scripts.extraction.image_extractor import ImageExtractor 
        
        # Instantiate ImageExtractor. It will now use the mocked dependencies.
        self.extractor = ImageExtractor()
        
        try:
            self.mock_reporter: MockExtractionReporter = self.extractor.reporter # type: ignore
            self.mock_processor: MockImageProcessor = self.extractor.image_processor # type: ignore
            self.mock_coordinator: MockRetryCoordinator = self.extractor.retry_coordinator # type: ignore
        except AttributeError as e:
            raise AttributeError(f"Error accessing component on self.extractor: {e}. Check ImageExtractor structure.") from e

        # These checks should now pass
        if not isinstance(self.mock_reporter, MockExtractionReporter):
            raise TypeError(f"self.extractor.reporter is type {type(self.mock_reporter)}, expected MockExtractionReporter. Patching failed for ExtractionReporter.")
        if not isinstance(self.mock_processor, MockImageProcessor):
            raise TypeError(f"self.extractor.image_processor is type {type(self.mock_processor)}, expected MockImageProcessor. Patching failed for ImageProcessor.")
        if not isinstance(self.mock_coordinator, MockRetryCoordinator):
            raise TypeError(f"self.extractor.retry_coordinator is type {type(self.mock_coordinator)}, expected MockRetryCoordinator. Patching failed for RetryCoordinator.")

        # Reset states of mock instances for each test
        self.mock_reporter.start_doc_calls.clear()
        self.mock_reporter.track_attempt_calls.clear()
        self.mock_reporter.track_result_calls.clear()
        self.mock_reporter.finalize_calls.clear()
        self.mock_reporter.extracted_count = 0
        self.mock_reporter.failed_count = 0
        self.mock_reporter.problematic_images.clear()
        self.mock_reporter.errors.clear()
        self.mock_reporter.metrics = {"total_images_in_doc": 0}


        self.mock_processor.process_and_save_calls.clear()
        self.mock_processor.process_and_save_result_template = {
            'success': True, 'path': '', 'issue': None, 'issue_type': None,
            'validation_info': {'size': '100x100', 'format': self.mock_processor.image_format, 'is_valid': True},
            'processing_details': {}
        }

        self.mock_coordinator._call_count = 0
        self.mock_coordinator._side_effect = None
        self.mock_coordinator.coordinate_extraction_calls.clear()
        default_mock_image_for_coord = MagicMock()
        default_mock_image_for_coord.close = MagicMock() 
        self.mock_coordinator.coord_result = (
            default_mock_image_for_coord,
            {'success': True, 'attempt_count': 1, 'attempts': [{'strategy': 'standard', 'success': True, 'details': {'dimensions': '100x100', 'mode': 'RGB'}}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10, 'final_error': None}
        )

    # Patches for fitz.open and os.makedirs are still targeted at where ImageExtractor looks them up.
    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs')
    def test_extraction_pipeline_success(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None:
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_img_list = [
            (10, 0, 100, 100, 8, "DeviceRGB", "", "Im0", "DCTDecode", 0), 
            (20, 0, 150, 150, 8, "DeviceGray", "", "Im1", "FlateDecode", 0)
        ]
        mock_page.get_images.return_value = mock_img_list
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.close = MagicMock()
        mock_fitz_open.return_value = mock_doc

        img1_mock = MagicMock(); img1_mock.close = MagicMock()
        img2_mock = MagicMock(); img2_mock.close = MagicMock()
        self.mock_coordinator.set_side_effect([
            (img1_mock, {'success': True, 'page': 1, 'index_on_page': 0, 'xref': 10}),
            (img2_mock, {'success': True, 'page': 1, 'index_on_page': 1, 'xref': 20})
        ])

        output_dir = os.path.join(self.temp_dir, "output_success")
        results = self.extractor.extract_images_from_pdf(self.dummy_pdf_path, output_dir)

        self.assertEqual(self.mock_reporter.start_doc_calls, [self.dummy_pdf_path])
        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_fitz_open.assert_called_once_with(self.dummy_pdf_path)
        mock_doc.__getitem__.assert_called_once_with(0)
        mock_page.get_images.assert_called_once_with(full=True)

        self.assertEqual(len(self.mock_reporter.track_attempt_calls), 2)
        self.assertEqual(self.mock_coordinator._call_count, 2)
        self.assertEqual(len(self.mock_coordinator.coordinate_extraction_calls), 2)
        self.assertEqual(self.mock_coordinator.coordinate_extraction_calls[0][1], mock_img_list[0])
        self.assertEqual(self.mock_coordinator.coordinate_extraction_calls[1][1], mock_img_list[1])


        self.assertEqual(len(self.mock_processor.process_and_save_calls), 2)
        self.assertEqual(self.mock_processor.process_and_save_calls[0][1], os.path.join(output_dir, f'fig1-page1-img1.{self.mock_processor.image_format}'))
        self.assertEqual(self.mock_processor.process_and_save_calls[1][1], os.path.join(output_dir, f'fig2-page1-img2.{self.mock_processor.image_format}'))

        self.assertEqual(len(self.mock_reporter.track_result_calls), 2)
        self.assertEqual(self.mock_reporter.finalize_calls, [output_dir])
        mock_doc.close.assert_called_once()

        self.assertTrue(results['success'], f"Report errors: {results.get('errors')}")
        self.assertEqual(results['extracted_count'], 2)
        self.assertEqual(results['failed_count'], 0)
        self.assertEqual(results['problematic_count'], 0)
        self.assertEqual(results['metrics']['total_images_in_doc'], 2)

    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs')
    def test_extraction_pipeline_with_failures(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None:
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_img_list = [(10,0,0,0,0,'','','Im0','',0), (20,0,0,0,0,'','','Im1','',0), (30,0,0,0,0,'','','Im2','',0)] 
        mock_page = MagicMock()
        mock_page.get_images.return_value = mock_img_list
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.close = MagicMock()
        mock_fitz_open.return_value = mock_doc

        img1_mock = MagicMock(); img1_mock.close = MagicMock()
        img3_mock_coord_success = MagicMock(); img3_mock_coord_success.close = MagicMock()

        self.mock_coordinator.set_side_effect([
            (img1_mock, {'success': True, 'page': 1, 'index_on_page': 0, 'xref': 10}),
            (None, {'success': False, 'page': 1, 'index_on_page': 1, 'xref': 20, 'final_error': 'Coord Fail', 'issue_type': 'extraction_failed'}),
            (img3_mock_coord_success, {'success': True, 'page': 1, 'index_on_page': 2, 'xref': 30})
        ])
        
        def process_side_effect(image: MagicMock, output_path: str) -> Dict[str, Any]:
            if 'fig1' in output_path: 
                return {'success': True, 'path': output_path, 'issue': None, 'validation_info': {'is_valid': True}, 'processing_details': {'saved': True}}
            elif 'fig3' in output_path: 
                return {'success': False, 'path': output_path, 'issue': 'Proc Fail', 'issue_type': 'size_issues', 'validation_info': {'is_valid': False}, 'processing_details': {}}
            return {'success': False, 'path': output_path, 'issue': 'Unexpected image call in mock_processor', 'issue_type': 'test_setup_error'} # Should not happen in this test
        self.mock_processor.process_and_save_image = MagicMock(side_effect=process_side_effect)


        output_dir = os.path.join(self.temp_dir, "output_failures")
        results = self.extractor.extract_images_from_pdf(self.dummy_pdf_path, output_dir)

        self.assertEqual(self.mock_coordinator._call_count, 3)
        self.assertEqual(self.mock_processor.process_and_save_image.call_count, 2) 

        self.assertEqual(len(self.mock_reporter.track_result_calls), 3)
        self.assertEqual(self.mock_reporter.extracted_count, 1) 
        self.assertEqual(self.mock_reporter.failed_count, 2)    
        self.assertEqual(len(self.mock_reporter.problematic_images), 2)
        
        # Check specific errors are present. Using a set for order-agnostic check.
        self.assertEqual(set(self.mock_reporter.errors), {'Coord Fail', 'Proc Fail'})

        self.assertFalse(results['success'])
        self.assertEqual(results['extracted_count'], 1)
        self.assertEqual(results['failed_count'], 2)
        self.assertEqual(results['problematic_count'], 2)
        self.assertEqual(results['metrics']['total_images_in_doc'], 3)

        self.assertEqual(self.mock_reporter.finalize_calls, [output_dir])
        mock_doc.close.assert_called_once()

    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs')
    def test_pdf_error_handling(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None:
        mock_fitz_open.side_effect = fitz.FileNotFoundError("Mock PDF not found")

        output_dir = os.path.join(self.temp_dir, "output_pdf_error")
        non_existent_pdf_path = os.path.join(self.temp_dir,"non_existent.pdf") # Path for consistency
        results = self.extractor.extract_images_from_pdf(non_existent_pdf_path, output_dir)

        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_fitz_open.assert_called_once_with(non_existent_pdf_path)

        self.assertEqual(self.mock_coordinator._call_count, 0)
        self.assertEqual(len(self.mock_processor.process_and_save_calls), 0)

        self.assertEqual(len(self.mock_reporter.errors), 1)
        self.assertIn(f"PDF file not found: {non_existent_pdf_path}", self.mock_reporter.errors[0])
        self.assertEqual(self.mock_reporter.finalize_calls, [output_dir])

        self.assertFalse(results['success'])
        self.assertEqual(results['extracted_count'], 0)
        self.assertEqual(results['failed_count'], 0) 
        self.assertEqual(results['problematic_count'], 0)
        self.assertEqual(results['metrics']['total_images_in_doc'], 0) 
        self.assertIn(f"PDF file not found: {non_existent_pdf_path}", results['errors'])


    @patch('scripts.extraction.image_extractor.fitz.open')
    @patch('scripts.extraction.image_extractor.os.makedirs', side_effect=OSError("Mock mkdir failed"))
    def test_makedirs_error_handling(self, mock_makedirs: MagicMock, mock_fitz_open: MagicMock) -> None:
        # This path doesn't need to be creatable, as os.makedirs is mocked to fail.
        output_dir = os.path.join(self.temp_dir, "uncreatable_output_dir") 
        results = self.extractor.extract_images_from_pdf(self.dummy_pdf_path, output_dir)

        mock_makedirs.assert_called_once_with(output_dir, exist_ok=True)
        mock_fitz_open.assert_not_called()

        self.assertEqual(self.mock_coordinator._call_count, 0)
        self.assertEqual(len(self.mock_processor.process_and_save_calls), 0)

        self.assertEqual(len(self.mock_reporter.errors), 1)
        self.assertIn(f"Failed to create output directory {output_dir}: Mock mkdir failed", self.mock_reporter.errors[0])
        self.assertEqual(self.mock_reporter.finalize_calls, [output_dir])

        self.assertFalse(results['success'])
        self.assertEqual(results['extracted_count'], 0)
        self.assertEqual(results['failed_count'], 0)
        self.assertEqual(results['problematic_count'], 0)
        self.assertEqual(results['metrics']['total_images_in_doc'], 0)
        self.assertIn(f"Failed to create output directory {output_dir}: Mock mkdir failed", results['errors'])

if __name__ == '__main__':
    unittest.main()