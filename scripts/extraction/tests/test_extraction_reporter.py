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

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_initialization_resets_metrics(self):
        """Test that metrics are correctly initialized."""
        self.assertEqual(self.reporter.metrics["total_images_in_doc"], 0)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 0)
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0)
        self.assertEqual(self.reporter.metrics["validation_failures"], 0)
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertGreaterEqual(len(self.reporter.metrics["issue_types"]), len(ImageIssueType)) # Check if issue types are initialized
        self.assertEqual(len(self.reporter.problematic_images), 0)
        self.assertEqual(len(self.reporter.errors), 0)
        self.assertIsNone(self.reporter.pdf_path)
        self.assertIsNone(self.reporter.start_time)
        self.assertEqual(self.reporter.extracted_count, 0)
        self.assertEqual(self.reporter.failed_count, 0)


    def test_start_document_report_resets_and_sets(self):
        """Test that start_document_report resets state and sets document info."""
        # Simulate some previous state
        self.reporter.metrics["total_images_in_doc"] = 5
        self.reporter.problematic_images.append({"issue": "test"})
        self.reporter.errors.append("test error")
        self.reporter.extracted_count = 2
        self.reporter.failed_count = 3

        self.reporter.start_document_report(self.mock_pdf_path)

        self.assertEqual(self.reporter.metrics["total_images_in_doc"], 0)
        self.assertEqual(len(self.reporter.problematic_images), 0)
        self.assertEqual(len(self.reporter.errors), 0)
        self.assertEqual(self.reporter.extracted_count, 0)
        self.assertEqual(self.reporter.failed_count, 0)
        self.assertEqual(self.reporter.pdf_path, self.mock_pdf_path)
        self.assertIsNotNone(self.reporter.start_time)


    def test_track_image_attempt(self):
        """Test tracking of image attempts."""
        self.reporter.start_document_report(self.mock_pdf_path)
        self.reporter.track_image_attempt((10, ...)) # Mock img_info
        self.reporter.track_image_attempt((20, ...)) # Mock img_info

        self.assertEqual(self.reporter.metrics["total_images_in_doc"], 2)
        # Attempted extractions is tracked when track_extraction_result is called
        self.assertEqual(self.reporter.metrics["attempted_extractions"], 0)


    def test_track_extraction_result_success(self):
        """Test tracking a fully successful image extraction and processing."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True,
            'attempt_count': 1,
            'attempts': [{'strategy': 'standard', 'success': True, 'details': {}}],
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
            'attempt_count': 3,
            'attempts': [{}, {}, {'strategy': 'page_based', 'success': False}],
            'duration': 0.15,
            'page': 2, 'index_on_page': 1, 'xref': 20,
            'final_error': 'All strategies failed',
            'issue_type': 'extraction_failed'
        }
        # Processing result will be skipped or minimal if extraction fails
        processing_result = {
            'success': False,
            'issue': 'Extraction failed, skipping processing.',
            'issue_type': 'processing_skipped_extraction_failed'
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 0)
        self.assertEqual(self.reporter.metrics["failed_extractions"], 1) # Extraction failure counts here
        self.assertEqual(self.reporter.metrics["validation_failures"], 0)
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 0)
        self.assertEqual(self.reporter.failed_count, 1) # Global failed count
        self.assertEqual(len(self.reporter.problematic_images), 1)
        self.assertEqual(len(self.reporter.errors), 1)
        self.assertEqual(self.reporter.metrics["issue_types"]["extraction_failed"], 1)
        self.assertIn('All strategies failed', self.reporter.problematic_images[0]['issue'])


    def test_track_extraction_result_validation_failure(self):
        """Test tracking an image that succeeded extraction but failed validation."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True, # Extraction succeeded
            'attempt_count': 1,
            'attempts': [{'strategy': 'standard', 'success': True, 'details': {}}],
            'duration': 0.05,
            'page': 3, 'index_on_page': 2, 'xref': 30
        }
        processing_result = {
            'success': False, # Processing/Validation failed
            'path': '/fake/path/small.png',
            'issue': 'Image validation failed: size too small',
            'issue_type': ImageIssueType.SIZE_ISSUES.value, # Use enum value
            'validation_info': {'size': '40x40', 'min_size': '50x50'},
            'processing_details': {}
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 1) # Counts as extracted
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0) # Doesn't count as extraction failure
        self.assertEqual(self.reporter.metrics["validation_failures"], 1) # Counts as validation failure
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 1) # Global extracted count
        self.assertEqual(self.reporter.failed_count, 1) # Global failed count (validation issues contribute)
        self.assertEqual(len(self.reporter.problematic_images), 1)
        self.assertEqual(len(self.reporter.errors), 1)
        self.assertEqual(self.reporter.metrics["issue_types"][ImageIssueType.SIZE_ISSUES.value], 1)
        self.assertIn('validation failed', self.reporter.problematic_images[0]['issue'].lower())
        self.assertEqual(self.reporter.problematic_images[0]['issue_type'], ImageIssueType.SIZE_ISSUES.value)


    def test_track_extraction_result_processing_failure(self):
        """Test tracking an image that succeeded extraction but failed during processing/saving."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True, # Extraction succeeded
            'attempt_count': 1,
            'attempts': [{'strategy': 'standard', 'success': True, 'details': {}}],
            'duration': 0.05,
            'page': 4, 'index_on_page': 3, 'xref': 40
        }
        processing_result = {
            'success': False, # Processing/Validation failed
            'path': '/fake/path/error.png',
            'issue': 'Failed to save file: Permission denied',
            'issue_type': 'save_error', # Custom issue type for processing errors
            'validation_info': {}, # No validation info if save failed
            'processing_details': {}
        }

        self.reporter.track_extraction_result(extraction_info, processing_result)

        self.assertEqual(self.reporter.metrics["attempted_extractions"], 1)
        self.assertEqual(self.reporter.metrics["successful_extractions"], 1) # Counts as extracted initially
        self.assertEqual(self.reporter.metrics["failed_extractions"], 0)
        self.assertEqual(self.reporter.metrics["validation_failures"], 0) # Not a validation failure
        self.assertEqual(self.reporter.metrics["retry_successes"], 0)
        self.assertEqual(self.reporter.extracted_count, 1) # Global extracted count (produced PIL)
        self.assertEqual(self.reporter.failed_count, 1) # Global failed count (processing issues contribute)
        self.assertEqual(len(self.reporter.problematic_images), 1)
        self.assertEqual(len(self.reporter.errors), 1)
        # Check if processing_failed or save_error is tracked
        self.assertEqual(self.reporter.metrics["issue_types"].get('save_error', 0), 1)
        self.assertIn('Failed to save file', self.reporter.problematic_images[0]['issue'])
        self.assertEqual(self.reporter.problematic_images[0]['issue_type'], 'save_error')


    def test_track_extraction_result_retry_success(self):
        """Test tracking an image that succeeded after a retry."""
        self.reporter.start_document_report(self.mock_pdf_path)

        extraction_info = {
            'success': True, # Extraction succeeded
            'attempt_count': 2, # More than 1 attempt means a retry occurred
            'attempts': [
                 {'strategy': 'standard', 'success': False, 'error': 'initial fail'},
                 {'strategy': 'alternate', 'success': True, 'details': {}} # Succeeded on 2nd attempt
            ],
            'duration': 0.10,
            'page': 5, 'index_on_page': 0, 'xref': 50
        }
        processing_result = {
            'success': True, # Processing/Validation succeeded
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
        self.assertEqual(self.reporter.metrics["retry_successes"], 1) # Should count as a retry success
        self.assertEqual(self.reporter.extracted_count, 1)
        self.assertEqual(self.reporter.failed_count, 0)
        self.assertEqual(len(self.reporter.problematic_images), 0)
        self.assertEqual(len(self.reporter.errors), 0)


    def test_finalize_report_success_case(self):
        """Test finalizing a report with only successful extractions."""
        self.reporter.start_document_report(self.mock_pdf_path)
        # Simulate 5 successful extractions
        for i in range(5):
            extraction_info = {
                'success': True, 'attempt_count': 1, 'attempts': [{'strategy': 'standard', 'success': True, 'details': {}}],
                'duration': 0.01, 'page': 1, 'index_on_page': i, 'xref': 10 + i
            }
            processing_result = {'success': True, 'path': f'/fake/path/{i}.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
            self.reporter.track_extraction_result(extraction_info, processing_result)

        # Mock time for consistent duration calculation
        with patch('scripts.extraction.extraction_reporter.time.time', side_effect=[self.reporter.start_time, self.reporter.start_time + 2.5]):
             summary = self.reporter.finalize_report(output_dir=self.temp_dir) # Save report to temp dir

        self.assertTrue(summary['success'])
        self.assertEqual(summary['extracted_count'], 5)
        self.assertEqual(summary['failed_count'], 0)
        self.assertEqual(summary['problematic_count'], 0)
        self.assertEqual(summary['errors_count'], 0)
        self.assertEqual(summary['metrics']['successful_extractions'], 5)
        self.assertEqual(summary['metrics']['failed_extractions'], 0)
        self.assertEqual(summary['metrics']['validation_failures'], 0)
        self.assertEqual(summary['metrics']['retry_successes'], 0)
        self.assertAlmostEqual(summary['total_elapsed_time'], 2.5, places=1) # Check elapsed time

        self.assertIn('report_path', summary)
        self.assertTrue(os.path.exists(summary['report_path']))
        self.assertIn("Image Extraction Diagnostic Report", summary['report_text'])
        self.assertIn("Successfully extracted & processed: 5", summary['report_text'])
        self.assertIn("Failed extraction or processing/validation: 0", summary['report_text'])
        self.assertIn("No problematic images were identified.", summary['report_text'])


    def test_finalize_report_with_failures(self):
        """Test finalizing a report with a mix of successes and failures."""
        self.reporter.start_document_report(self.mock_pdf_path)

        # Success 1
        ext_info_s1 = {'success': True, 'attempt_count': 1, 'attempts': [{'strategy': 'standard', 'success': True, 'details': {}}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10}
        proc_res_s1 = {'success': True, 'path': '/fake/path/s1.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
        self.reporter.track_extraction_result(ext_info_s1, proc_res_s1)

        # Extraction Failure 1
        ext_info_ef1 = {'success': False, 'attempt_count': 2, 'attempts': [{}, {}], 'duration': 0.1, 'page': 1, 'index_on_page': 1, 'xref': 11, 'final_error': 'Ext Fail', 'issue_type': 'extraction_failed'}
        proc_res_ef1 = {'success': False, 'issue': 'Ext failed', 'issue_type': 'processing_skipped_extraction_failed'}
        self.reporter.track_extraction_result(ext_info_ef1, proc_res_ef1)

        # Validation Failure 1
        ext_info_vf1 = {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.02, 'page': 1, 'index_on_page': 2, 'xref': 12}
        proc_res_vf1 = {'success': False, 'path': '/fake/path/vf1.png', 'issue': 'Valid Fail', 'issue_type': ImageIssueType.SIZE_ISSUES.value, 'validation_info': {}}
        self.reporter.track_extraction_result(ext_info_vf1, proc_res_vf1)

        # Success with Retry 1
        ext_info_sr1 = {'success': True, 'attempt_count': 2, 'attempts': [{}, {'success': True, 'details': {}}], 'duration': 0.05, 'page': 1, 'index_on_page': 3, 'xref': 13}
        proc_res_sr1 = {'success': True, 'path': '/fake/path/sr1.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
        self.reporter.track_extraction_result(ext_info_sr1, proc_res_sr1)

        # Processing Failure 1
        ext_info_pf1 = {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.03, 'page': 1, 'index_on_page': 4, 'xref': 14}
        proc_res_pf1 = {'success': False, 'path': '/fake/path/pf1.png', 'issue': 'Proc Fail', 'issue_type': 'processing_error'}
        self.reporter.track_extraction_result(ext_info_pf1, proc_res_pf1)


        # Mock time
        with patch('scripts.extraction.extraction_reporter.time.time', side_effect=[self.reporter.start_time, self.reporter.start_time + 3.0]):
             summary = self.reporter.finalize_report(output_dir=self.temp_dir)

        # Total attempted: 5
        # Extracted (produced PIL): S1, VF1, SR1, PF1 -> 4
        # Failed (did not produce PIL): EF1 -> 1
        # Validation Failures: VF1 -> 1
        # Retry Successes: SR1 -> 1
        # Global Extracted Count (processed ok): S1, SR1 -> 2
        # Global Failed Count (problematic): EF1, VF1, PF1 -> 3
        # Problematic Images List: EF1, VF1, PF1 -> 3

        self.assertFalse(summary['success']) # 3/5 failures = 0.6 failure ratio > 0.25
        self.assertEqual(summary['extracted_count'], 2) # Total successful pipeline
        self.assertEqual(summary['failed_count'], 3) # Total problematic pipeline
        self.assertEqual(summary['problematic_count'], 3) # Count of items in problematic_images list
        self.assertEqual(summary['errors_count'], 3) # Count of items in errors list

        self.assertEqual(summary['metrics']['attempted_extractions'], 5)
        self.assertEqual(summary['metrics']['successful_extractions'], 4) # Extraction succeeded count
        self.assertEqual(summary['metrics']['failed_extractions'], 1) # Extraction failed count
        self.assertEqual(summary['metrics']['validation_failures'], 1)
        self.assertEqual(summary['metrics']['retry_successes'], 1)
        self.assertEqual(summary['metrics']['issue_types']['extraction_failed'], 1)
        self.assertEqual(summary['metrics']['issue_types'][ImageIssueType.SIZE_ISSUES.value], 1)
        self.assertEqual(summary['metrics']['issue_types']['processing_error'], 1)
        # processing_skipped_extraction_failed is not a top-level issue type counter in metrics
        self.assertEqual(summary['metrics']['issue_types'].get('processing_skipped_extraction_failed', 0), 0)


        self.assertEqual(len(summary['problematic_images']), 3)
        self.assertEqual(len(summary['errors']), 3)

        self.assertIn('report_path', summary)
        self.assertTrue(os.path.exists(summary['report_path']))
        report_content = summary['report_text']
        self.assertIn("Successfully extracted & processed: 2", report_content)
        self.assertIn("Failed extraction or processing/validation: 3", report_content)
        self.assertIn("Total problematic images reported: 3", report_content)
        self.assertIn("Extraction Attempts: 2", report_content) # For the EF1 case
        self.assertIn("Validation Details", report_content) # For the VF1 case
        self.assertIn("Proc Fail", report_content) # For the PF1 case


    def test_finalize_report_no_output_dir(self):
        """Test finalizing report without saving to a file."""
        self.reporter.start_document_report(self.mock_pdf_path)
        extraction_info = {'success': True, 'attempt_count': 1, 'attempts': [{}], 'duration': 0.01, 'page': 1, 'index_on_page': 0, 'xref': 10}
        processing_result = {'success': True, 'path': '/fake/path/s1.png', 'issue': None, 'issue_type': None, 'validation_info': {}}
        self.reporter.track_extraction_result(extraction_info, processing_result)

        with patch('scripts.extraction.extraction_reporter.time.time', side_effect=[self.reporter.start_time, self.reporter.start_time + 1.0]):
             summary = self.reporter.finalize_report(output_dir=None)

        self.assertTrue(summary['success'])
        self.assertEqual(summary['extracted_count'], 1)
        self.assertEqual(summary['failed_count'], 0)
        self.assertEqual(summary['problematic_count'], 0)
        self.assertNotIn('report_path', summary) # Report file should not be saved
        self.assertIn('report_text', summary) # Report text should still be generated


if __name__ == '__main__':
    unittest.main()