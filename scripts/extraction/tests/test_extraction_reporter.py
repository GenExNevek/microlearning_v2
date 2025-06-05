# scripts/extraction/tests/test_extraction_reporter.py

"""Unit tests for the ExtractionReporter."""

import unittest
from unittest.mock import MagicMock, patch, call
import os
import tempfile
import shutil
import time
from typing import Dict, Any

# Import the ExtractionReporter and ImageIssueType
from ..extraction_reporter import ExtractionReporter
from ...utils.image_validation import ImageIssueType # Adjust import as necessary

# Mock configuration
MOCK_CONFIG = {
    "dpi": 150, # Needed by reporter init ( indirectly via default metrics )
    "validate_images": True, # Needed by reporter init ( indirectly via issue types )
}

class TestExtractionReporter(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.reporter = ExtractionReporter(MOCK_CONFIG)
        self.mock_pdf_path = "/fake/path/to/document.pdf"
        
        # Set a fixed start time that will be returned by the mock
        # when time.time() is called during start_document_report
        self.fixed_start_time = time.time() # Capture current time once
        
        # Patch time.time() globally for the test class.
        # It will return self.fixed_start_time for all calls to time.time()
        # unless a more specific patch is used within a test method.
        self.time_patcher = patch('scripts.extraction.extraction_reporter.time.time', MagicMock(return_value=self.fixed_start_time))
        self.time_patcher.start()


    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        self.time_patcher.stop() # Stop the global patch

    def test_initialization_resets_metrics(self):
        """Test that metrics are correctly initialized."""
        # For this test, create a new reporter instance to ensure it's pristine
        # and not affected by the global time patch if its __init__ used time.time()
        # (though in this case, ExtractionReporter.__init__ doesn't directly use time.time())
        local_reporter = ExtractionReporter(MOCK_CONFIG)
        self.assertEqual(local_reporter.metrics["total_images_in_doc"], 0)
        self.assertEqual(local_reporter.metrics["successful_extractions"], 0)
        self.assertEqual(local_reporter.metrics["failed_extractions"], 0)
        self.assertEqual(local_reporter.metrics["validation_failures"], 0)
        self.assertEqual(local_reporter.metrics["retry_successes"], 0)
        self.assertGreaterEqual(len(local_reporter.metrics["issue_types"]), len(ImageIssueType)) 
        self.assertEqual(len(local_reporter.problematic_images), 0)
        self.assertEqual(len(local_reporter.errors), 0)
        self.assertIsNone(local_reporter.pdf_path)
        self.assertIsNone(local_reporter.start_time) # start_time is set by start_document_report
        self.assertEqual(local_reporter.extracted_count, 0)
        self.assertEqual(local_reporter.failed_count, 0)


    def test_start_document_report_resets_and_sets(self):
        """Test that start_document_report resets state and sets document info."""
        self.reporter.metrics["total_images_in_doc"] = 5
        self.reporter.problematic_images.append({"issue": "test"})
        self.reporter.errors.append("test error")
        self.reporter.extracted_count = 2
        self.reporter.failed_count = 3

        # time.time() will be called here, and the global patch will make it return self.fixed_start_time
        self.reporter.start_document_report(self.mock_pdf_path)

        self.assertEqual(self.reporter.metrics["total_images_in_doc"], 0)
        self.assertEqual(len(self.reporter.problematic_images), 0)
        self.assertEqual(len(self.reporter.errors), 0)
        self.assertEqual(self.reporter.extracted_count, 0)
        self.assertEqual(self.reporter.failed_count, 0)
        self.assertEqual(self.reporter.pdf_path, self.mock_pdf_path)
        self.assertEqual(self.reporter.start_time, self.fixed_start_time) # Verify start_time was set by the mock


    def test_track_image_attempt(self):
        """Test tracking of image attempts."""
        self.reporter.start_document_report(self.mock_pdf_path)
        self.reporter.track_image_attempt((10, ...)) 
        self.reporter.track_image_attempt((20, ...)) 

        self.assertEqual(self.reporter.metrics["total_images_in_doc"], 2)
        self.assertEqual(self.reporter.metrics["attempted_extractions"], 0)


    def test_track_extraction_result_success(self):
        """Test tracking a fully successful image extraction and processing."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True,
            'attempt_count': 1,
            'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.05}],
            'duration': 0.05,
            'page': 1, 'index_on_page': 0, 'xref': 10
        }
        processing_result = {
            'success': True,
            'path': '/fake/path',
            'issue': None,
            'issue_type': None,
            'validation_info': {'size': '100x100'}
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 1)
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0)
        self.assertEqual(self.reporter.metrics["validation_failures"], 0)
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 1) 
        self.assertEqual(self.reporter.failed_count, 0)
        self.assertEqual(len(self.reporter.problematic_images), 0)
        self.assertEqual(len(self.reporter.errors), 0)
        self.assertGreater(self.reporter.metrics["total_extraction_duration"], 0)


    def test_track_extraction_result_extraction_failure(self):
        """Test tracking an image that failed extraction."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': False,
            'attempt_count': 2, 
            'attempts': [
                {'strategy': 'standard', 'success': False, 'error': 'fail1', 'attempt_num': 1, 'duration': 0.07}, 
                {'strategy': 'page_based', 'success': False, 'error': 'fail2', 'attempt_num': 2, 'duration': 0.08}
            ],
            'duration': 0.15,
            'page': 2, 'index_on_page': 1, 'xref': 20,
            'final_error': 'All strategies failed',
            'issue_type': 'extraction_failed'
        }
        processing_result = {
            'success': False,
            'issue': 'Extraction failed, skipping processing.',
            'issue_type': 'processing_skipped_extraction_failed'
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 0)
        self.assertEqual(self.reporter.metrics["failed_extractions"], 1) 
        self.assertEqual(self.reporter.metrics["validation_failures"], 0)
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 0) 
        self.assertEqual(self.reporter.failed_count, 1) 
        self.assertEqual(len(self.reporter.problematic_images), 1)
        self.assertEqual(len(self.reporter.errors), 1)
        self.assertEqual(self.reporter.metrics["issue_types"]["extraction_failed"], 1)
        self.assertIn('All strategies failed', self.reporter.problematic_images[0]['issue'])


    def test_track_extraction_result_validation_failure(self):
        """Test tracking an image that succeeded extraction but failed validation."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True, 
            'attempt_count': 1,
            'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.05}],
            'duration': 0.05,
            'page': 3, 'index_on_page': 2, 'xref': 30
        }
        processing_result = {
            'success': False, 
            'path': '/fake/path/small.png',
            'issue': 'Image validation failed: size too small',
            'issue_type': ImageIssueType.SIZE_ISSUES.value, 
            'validation_info': {'size': '40x40', 'min_size': '50x50'},
            'processing_details': {}
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 1) 
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0) 
        self.assertEqual(self.reporter.metrics["validation_failures"], 1) 
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 0) 
        self.assertEqual(self.reporter.failed_count, 1) 
        self.assertEqual(len(self.reporter.problematic_images), 1)
        self.assertEqual(len(self.reporter.errors), 1)
        self.assertEqual(self.reporter.metrics["issue_types"][ImageIssueType.SIZE_ISSUES.value], 1)
        self.assertIn('validation failed', self.reporter.problematic_images[0]['issue'].lower())
        self.assertEqual(self.reporter.problematic_images[0]['issue_type'], ImageIssueType.SIZE_ISSUES.value)


    def test_track_extraction_result_processing_failure(self):
        """Test tracking an image that succeeded extraction but failed during processing/saving."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True, 
            'attempt_count': 1,
            'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.05}],
            'duration': 0.05,
            'page': 4, 'index_on_page': 3, 'xref': 40
        }
        processing_result = {
            'success': False, 
            'path': '/fake/path/error.png',
            'issue': 'Failed to save file: Permission denied',
            'issue_type': 'save_error', 
            'validation_info': {}, 
            'processing_details': {}
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 1) 
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0)
        self.assertEqual(self.reporter.metrics["validation_failures"], 0) 
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 0) 
        self.assertEqual(self.reporter.failed_count, 1) 
        self.assertEqual(len(self.reporter.problematic_images), 1)
        self.assertEqual(len(self.reporter.errors), 1)
        self.assertEqual(self.reporter.metrics["issue_types"].get('save_error', 0), 1)
        self.assertIn('Failed to save file', self.reporter.problematic_images[0]['issue'])
        self.assertEqual(self.reporter.problematic_images[0]['issue_type'], 'save_error')


    def test_track_extraction_result_retry_success(self):
        """Test tracking an image that succeeded after a retry."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True, 
            'attempt_count': 2, 
            'attempts': [
                 {'strategy': 'standard', 'success': False, 'error': 'initial fail', 'attempt_num': 1, 'duration': 0.04},
                 {'strategy': 'alternate', 'success': True, 'details': {}, 'attempt_num': 2, 'duration': 0.06} 
            ],
            'duration': 0.10,
            'page': 5, 'index_on_page': 0, 'xref': 50
        }
        processing_result = {
            'success': True, 
            'path': '/fake/path/retry.png',
            'issue': None,
            'issue_type': None,
            'validation_info': {},
            'processing_details': {}
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 1)
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0)
        self.assertEqual(self.reporter.metrics["validation_failures"], 0)
        self.assertEqual(self.reporter.metrics["retry_successes"], 1) 
        self.assertEqual(self.reporter.extracted_count, 1) 
        self.assertEqual(self.reporter.failed_count, 0)
        self.assertEqual(len(self.reporter.problematic_images), 0)
        self.assertEqual(len(self.reporter.errors), 0)


    def test_finalize_report_success_case(self):
        """Test finalizing a report with only successful extractions."""
        self.reporter.start_document_report(self.mock_pdf_path) # self.reporter.start_time is now self.fixed_start_time
        
        for i in range(5):
            extraction_info = {
                'success': True, 'attempt_count': 1, 
                'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.01}],
                'duration': 0.01, 'page': 1, 'index_on_page': i, 'xref': 10 + i
            }
            processing_result = {'success': True, 'path': f'/fake/path/{i}.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
            self.reporter.track_extraction_result(extraction_info, processing_result)

        mock_end_time = self.fixed_start_time + 2.5
        
        # Temporarily stop the class-level patcher and use a local one for this specific call's end_time
        self.time_patcher.stop()
        with patch('scripts.extraction.extraction_reporter.time.time', return_value=mock_end_time):
             summary = self.reporter.finalize_report(output_dir=self.temp_dir)
        self.time_patcher.start() # Restart the class-level patcher

        self.assertTrue(summary['success'])
        self.assertEqual(summary['extracted_count'], 5) 
        self.assertEqual(summary['failed_count'], 0)
        self.assertEqual(summary['problematic_count'], 0)
        self.assertEqual(summary['errors_count'], 0)
        self.assertEqual(summary['metrics']['successful_extractions'], 5) 
        self.assertEqual(summary['metrics']['failed_extractions'], 0)
        self.assertEqual(summary['metrics']['validation_failures'], 0)
        self.assertEqual(summary['metrics']['retry_successes'], 0)
        self.assertAlmostEqual(summary['total_elapsed_time'], 2.5, places=1) 

        self.assertIn('report_path', summary)
        self.assertTrue(os.path.exists(summary['report_path']))
        self.assertIn("Image Extraction Diagnostic Report", summary['report_text'])
        self.assertIn("Successfully extracted & processed: 5", summary['report_text'])
        self.assertIn("Failed extraction or processing/validation: 0", summary['report_text'])
        self.assertIn("No problematic images were identified.", summary['report_text'])


    def test_finalize_report_with_failures(self):
        """Test finalizing a report with a mix of successes and failures."""
        self.reporter.start_document_report(self.mock_pdf_path) # self.reporter.start_time is now self.fixed_start_time

        # Success 1 (S1)
        ext_info_s1 = {'success': True, 'attempt_count': 1, 
                       'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.01}], 
                       'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10}
        proc_res_s1 = {'success': True, 'path': '/fake/path/s1.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
        self.reporter.track_extraction_result(ext_info_s1, proc_res_s1)

        # Extraction Failure 1 (EF1)
        ext_info_ef1 = {'success': False, 'attempt_count': 2, 
                        'attempts': [
                            {'strategy': 's1', 'success': False, 'error': 'e1', 'attempt_num': 1, 'duration': 0.04}, 
                            {'strategy': 's2', 'success': False, 'error': 'e2', 'attempt_num': 2, 'duration': 0.06}
                        ], 
                        'duration': 0.1, 'page': 1, 'index_on_page': 1, 'xref': 11, 'final_error': 'Ext Fail', 'issue_type': 'extraction_failed'}
        proc_res_ef1 = {'success': False, 'issue': 'Ext failed', 'issue_type': 'processing_skipped_extraction_failed'}
        self.reporter.track_extraction_result(ext_info_ef1, proc_res_ef1)

        # Validation Failure 1 (VF1)
        ext_info_vf1 = {'success': True, 'attempt_count': 1, 
                        'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.02}], 
                        'duration': 0.02, 'page': 1, 'index_on_page': 2, 'xref': 12}
        proc_res_vf1 = {'success': False, 'path': '/fake/path/vf1.png', 'issue': 'Valid Fail', 'issue_type': ImageIssueType.SIZE_ISSUES.value, 'validation_info': {'size': '40x40', 'min_size': '50x50'}}
        self.reporter.track_extraction_result(ext_info_vf1, proc_res_vf1)

        # Success with Retry 1 (SR1)
        ext_info_sr1 = {'success': True, 'attempt_count': 2, 
                        'attempts': [
                            {'strategy': 's1', 'success': False, 'error': 'e1', 'attempt_num': 1, 'duration': 0.02}, 
                            {'strategy': 's2', 'success': True, 'details': {}, 'attempt_num': 2, 'duration': 0.03}
                        ], 
                        'duration': 0.05, 'page': 1, 'index_on_page': 3, 'xref': 13}
        proc_res_sr1 = {'success': True, 'path': '/fake/path/sr1.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
        self.reporter.track_extraction_result(ext_info_sr1, proc_res_sr1)

        # Processing Failure 1 (PF1)
        ext_info_pf1 = {'success': True, 'attempt_count': 1, 
                        'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.03}], 
                        'duration': 0.03, 'page': 1, 'index_on_page': 4, 'xref': 14}
        proc_res_pf1 = {'success': False, 'path': '/fake/path/pf1.png', 'issue': 'Proc Fail', 'issue_type': 'processing_error'}
        self.reporter.track_extraction_result(ext_info_pf1, proc_res_pf1)


        mock_end_time = self.fixed_start_time + 3.0
        self.time_patcher.stop()
        with patch('scripts.extraction.extraction_reporter.time.time', return_value=mock_end_time):
             summary = self.reporter.finalize_report(output_dir=self.temp_dir)
        self.time_patcher.start()


        self.assertFalse(summary['success']) 
        self.assertEqual(summary['extracted_count'], 2) 
        self.assertEqual(summary['failed_count'], 3) 
        self.assertEqual(summary['problematic_count'], 3) 
        self.assertEqual(summary['errors_count'], 3) 

        self.assertEqual(summary['metrics']['attempted_extractions'], 5)
        self.assertEqual(summary['metrics']['successful_extractions'], 4) 
        self.assertEqual(summary['metrics']['failed_extractions'], 1) 
        self.assertEqual(summary['metrics']['validation_failures'], 1)
        self.assertEqual(summary['metrics']['retry_successes'], 1)
        self.assertEqual(summary['metrics']['issue_types']['extraction_failed'], 1)
        self.assertEqual(summary['metrics']['issue_types'][ImageIssueType.SIZE_ISSUES.value], 1)
        self.assertEqual(summary['metrics']['issue_types']['processing_error'], 1)
        self.assertEqual(summary['metrics']['issue_types'].get('processing_skipped_extraction_failed', 0), 0)


        self.assertEqual(len(summary['problematic_images']), 3)
        self.assertEqual(len(summary['errors']), 3)

        self.assertIn('report_path', summary)
        self.assertTrue(os.path.exists(summary['report_path']))
        report_content = summary['report_text']

        self.assertIn("Successfully extracted & processed: 2", report_content)
        self.assertIn("Failed extraction or processing/validation: 3", report_content)
        self.assertIn("Total problematic images reported: 3", report_content)
        
        # For EF1 (Problematic Image 1)
        self.assertIn("### Problematic Image 1 (Page 1, Index 1)", report_content)
        self.assertIn("- **Issue Type**: extraction_failed", report_content)
        self.assertIn("- **Extraction Attempts**: 2", report_content) 
        self.assertIn("    - Attempt 1: Strategy='s1', Status=FAILED", report_content)
        self.assertIn("    - Attempt 2: Strategy='s2', Status=FAILED", report_content)

        # For VF1 (Problematic Image 2)
        self.assertIn("### Problematic Image 2 (Page 1, Index 2)", report_content)
        self.assertIn("- **Issue Type**: size_issues", report_content)
        self.assertIn("- **Extraction Attempts**: 1", report_content)
        self.assertIn("    - Attempt 1: Strategy='standard', Status=SUCCESS", report_content) 
        self.assertIn("- **Validation Details**: {'size': '40x40', 'min_size': '50x50'}", report_content)

        # For PF1 (Problematic Image 3)
        self.assertIn("### Problematic Image 3 (Page 1, Index 4)", report_content)
        self.assertIn("- **Issue Type**: processing_error", report_content)
        self.assertIn("- **Extraction Attempts**: 1", report_content)
        self.assertIn("    - Attempt 1: Strategy='standard', Status=SUCCESS", report_content) 
        self.assertIn("- **Issue**: Proc Fail", report_content)


    def test_finalize_report_no_output_dir(self):
        """Test finalizing report without saving to a file."""
        self.reporter.start_document_report(self.mock_pdf_path) # self.reporter.start_time is now self.fixed_start_time
        
        extraction_info = {'success': True, 'attempt_count': 1, 
                           'attempts': [{'strategy': 'standard', 'success': True, 'details': {}, 'attempt_num': 1, 'duration': 0.01}], 
                           'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10}
        processing_result = {'success': True, 'path': '/fake/path/s1.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
        self.reporter.track_extraction_result(extraction_info, processing_result)

        mock_end_time = self.fixed_start_time + 1.0
        self.time_patcher.stop()
        with patch('scripts.extraction.extraction_reporter.time.time', return_value=mock_end_time):
             summary = self.reporter.finalize_report(output_dir=None)
        self.time_patcher.start()

        self.assertTrue(summary['success'])
        self.assertEqual(summary['extracted_count'], 1)
        self.assertEqual(summary['failed_count'], 0)
        self.assertEqual(summary['problematic_count'], 0)
        self.assertNotIn('report_path', summary) 
        self.assertIn('report_text', summary) 


if __name__ == '__main__':
    unittest.main()