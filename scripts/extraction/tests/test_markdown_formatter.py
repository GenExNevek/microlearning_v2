# scripts/extraction/tests/test_markdown_formatter.py

"""Test script for the Markdown Formatter module."""

import os
import sys
import argparse
import shutil
from typing import Any, Optional, Dict
from unittest.mock import patch, MagicMock # For mocking

import pytest # For marking tests

# Add the project root to sys.path
# This assumes your tests are in 'scripts/extraction/tests' and project root is three levels up
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.extraction.pdf_reader import PDFReader
from scripts.extraction.markdown_formatter import MarkdownFormatter
from scripts.config import settings
from scripts.utils.image_validation import ImageIssueType # If needed for constructing mock results

# --- Test Data and Helper Functions ---

DUMMY_PDF_FILENAME = "dummy_test_pdf.pdf"
DUMMY_PDF_CONTENT = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n178\n%%EOF"
TEST_OUTPUT_DIR = os.path.join(project_root, 'test_output', 'markdown_formatter_tests') # Ensure TEST_OUTPUT_DIR is in project root

def setup_module(module):
    """Create dummy files and directories needed for tests."""
    os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)
    os.makedirs(settings.PDF_SOURCE_DIR, exist_ok=True)
    dummy_pdf_path_in_source = os.path.join(settings.PDF_SOURCE_DIR, DUMMY_PDF_FILENAME)
    if not os.path.exists(dummy_pdf_path_in_source):
        with open(dummy_pdf_path_in_source, "wb") as f:
            f.write(DUMMY_PDF_CONTENT)

def teardown_module(module):
    """Clean up dummy files and directories after tests."""
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR)
    dummy_pdf_path_in_source = os.path.join(settings.PDF_SOURCE_DIR, DUMMY_PDF_FILENAME)
    if os.path.exists(dummy_pdf_path_in_source):
        try:
            os.remove(dummy_pdf_path_in_source)
        except OSError as e:
            print(f"Warning: Could not remove dummy PDF {dummy_pdf_path_in_source}: {e}")


# --- End-to-End / Integration Test ---

@pytest.mark.slow
@pytest.mark.integration
def test_end_to_end_markdown_extraction_smoke(pdf_path: Optional[str] = None, output_path_arg: Optional[str] = None):
    """
    End-to-end smoke test for PDF extraction to markdown format.
    This test involves live API calls and full file processing.
    """
    reader = PDFReader()
    formatter = MarkdownFormatter(reader)

    if not pdf_path:
        pdf_path = os.path.join(settings.PDF_SOURCE_DIR, DUMMY_PDF_FILENAME)

    assert os.path.exists(pdf_path), f"Test PDF file not found: {pdf_path}"

    print(f"\n[E2E Test] Testing markdown extraction for: {pdf_path}")

    try:
        pdf_info: Dict[str, Any] = reader.read_pdf_from_path(pdf_path)
        assert pdf_info.get('error') is None, f"PDFReader failed: {pdf_info.get('error')}"

        metadata: Dict[str, Any] = formatter.extract_metadata_from_path(pdf_path)
        print("\n[E2E Test] Extracted metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")

        print("\n[E2E Test] Extracting and formatting content (this may take a while due to API calls)...")
        result: Dict[str, Any] = formatter.extract_and_format(pdf_info, metadata)

        assert result.get('success'), f"[E2E Test] Content extraction failed: {result.get('error', 'Unknown error')}"
        print("[E2E Test] SUCCESS! Content was extracted and formatted successfully.")

        output_filename_base = os.path.splitext(os.path.basename(pdf_path))[0]
        final_output_path = output_path_arg or os.path.join(TEST_OUTPUT_DIR, f"{output_filename_base}_e2e_output.md")
        
        os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
        with open(final_output_path, 'w', encoding='utf-8') as f:
            f.write(result.get('content', ''))
        print(f"[E2E Test] Content saved to: {final_output_path}")

        image_extraction_results = result.get('image_extraction', {})
        print(f"\n[E2E Test] Image Extraction Summary:")
        print(f"  Successfully extracted: {image_extraction_results.get('extracted_count', 0)}")
        print(f"  Problematic/Failed: {image_extraction_results.get('failed_count', 0)}")
        if image_extraction_results.get('report_path'):
            print(f"  Report Path: {image_extraction_results.get('report_path')}")

    except Exception as e:
        print(f"[E2E Test] ERROR: An unexpected exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        assert False, f"[E2E Test] Unexpected exception: {e}"

# --- Unit Tests for MarkdownFormatter ---

class TestMarkdownFormatterUnit:

    @pytest.fixture
    def mock_pdf_reader(self):
        reader = MagicMock(spec=PDFReader)
        reader._generate_content_direct.return_value = MagicMock(text="Mocked Gemini Content (direct)")
        reader._generate_content_file_api.return_value = MagicMock(text="Mocked Gemini Content (file_api)")
        reader.read_pdf_from_path.return_value = {
            'method': 'direct',
            'data': b'dummy pdf data',
            'path': 'dummy/path/test.pdf',
            'normalized_path': 'dummy/path/test.pdf',
            'error': None
        }
        return reader

    @pytest.fixture
    def mock_image_extractor_instance(self):
        extractor_instance = MagicMock()
        extractor_instance.extract_images_from_pdf.return_value = {
            'success': True, 'extracted_count': 0, 'failed_count': 0,
            'problematic_images': [], 'metrics': {}, 'errors': [],
            'output_dir': os.path.join(TEST_OUTPUT_DIR, 'dummy_pdf-img-assets'),
            'report_path': os.path.join(TEST_OUTPUT_DIR, 'dummy_pdf-img-assets', 'report.md')
        }
        return extractor_instance

    @pytest.fixture
    def formatter_instance(self, mock_pdf_reader, mock_image_extractor_instance):
        with patch('scripts.extraction.markdown_formatter.ImageExtractor') as MockedImageExtractorClass:
            MockedImageExtractorClass.return_value = mock_image_extractor_instance
            formatter = MarkdownFormatter(mock_pdf_reader)
            return formatter

    def test_extract_metadata_from_path_simple(self, formatter_instance: MarkdownFormatter):
        pdf_path = os.path.join("course_materials", "CON101-MyCourse", "MOD202-MyModule", "UNI303_MyUnitName.pdf")
        metadata = formatter_instance.extract_metadata_from_path(pdf_path)
        assert metadata['unit_id'] == 'UNI303'
        assert metadata['unit_title_id'] == 'MyUnitName'
        assert metadata['parent_module_id'] == 'MOD202'
        assert metadata['parent_course_id'] == 'CON101'

    def test_extract_metadata_from_path_with_phase(self, formatter_instance: MarkdownFormatter):
        pdf_path = os.path.join("igcse_papers", "CON101", "MOD202", "UNI303_MyUnitName_IGCSE.pdf")
        metadata = formatter_instance.extract_metadata_from_path(pdf_path)
        assert metadata['unit_id'] == 'UNI303'
        assert metadata['phase'] == 'IGCSE'

    def test_generate_frontmatter(self, formatter_instance: MarkdownFormatter):
        metadata = {
            'unit_id': 'U001', 'unit_title_id': 'title_id', 'unit_title': 'Test Unit',
            'phase': 'AS', 'subject': 'Physics', 'parent_module_id': 'M001',
            'parent_course_id': 'C001', 'batch_id': 'B001',
            'extraction_date': '2023-01-01',
        }
        frontmatter = formatter_instance.generate_frontmatter(metadata)
        assert "unit-id: U001" in frontmatter
        assert "unit-title: Test Unit" in frontmatter

    @patch('scripts.extraction.markdown_formatter.os.makedirs')
    def test_get_image_assets_dir(self, mock_makedirs, formatter_instance: MarkdownFormatter):
        pdf_path = os.path.join(settings.PDF_SOURCE_DIR, "courseA", "unitB.pdf")
        metadata = {'unit_title_id': 'unitB_title'}
        
        rel_path_from_source = os.path.join("courseA", "unitB")
        expected_dir_under_markdown_target = os.path.join(settings.MARKDOWN_TARGET_DIR, os.path.dirname(rel_path_from_source))
        expected_assets_dirname = f"{os.path.basename(rel_path_from_source)}{settings.IMAGE_ASSETS_SUFFIX}"
        expected_full_path = os.path.join(expected_dir_under_markdown_target, expected_assets_dirname)
        
        assets_dir = formatter_instance._get_image_assets_dir(pdf_path, metadata)
        
        assert os.path.normpath(assets_dir) == os.path.normpath(expected_full_path)
        mock_makedirs.assert_called_once_with(assets_dir, exist_ok=True)

    def test_post_process_markdown_basic_frontmatter(self, formatter_instance: MarkdownFormatter):
        content = "## Hello World"
        metadata = {'unit_id': 'test001', 'unit_title_id': 'hello_world_test'}
        processed_content = formatter_instance.post_process_markdown(content, metadata, None, "dummy.pdf")
        assert processed_content.startswith("---")
        assert "unit-id: test001" in processed_content

    @patch('scripts.extraction.markdown_formatter.os.path.exists')
    @patch('scripts.extraction.markdown_formatter.os.listdir')
    def test_post_process_markdown_image_linking_simple(self, mock_listdir, mock_exists, formatter_instance: MarkdownFormatter):
        mock_exists.return_value = True
        mock_listdir.return_value = ["fig1-page1-img1.png"]

        content = "Some text ![An image](some_image.png) more text."
        metadata = {'unit_id': 'imgtest', 'unit_title_id': 'image_linking_test'}
        
        mock_assets_dir_on_disk = os.path.join(TEST_OUTPUT_DIR, f"{metadata['unit_title_id']}{settings.IMAGE_ASSETS_SUFFIX}")
        image_extraction_results = {
            'success': True, 'extracted_count': 1, 'failed_count': 0,
            'problematic_images': [], 'errors': [],
            'output_dir': mock_assets_dir_on_disk,
            'report_path': os.path.join(mock_assets_dir_on_disk, 'report.md')
        }

        processed_content = formatter_instance.post_process_markdown(
            content, metadata, image_extraction_results,
            original_pdf_path=f"{metadata['unit_title_id']}.pdf"
        )
        
        expected_image_path_in_md = f"./{metadata['unit_title_id']}{settings.IMAGE_ASSETS_SUFFIX}/fig1-page1-img1.png"
        assert f"![An image]({expected_image_path_in_md})" in processed_content
        mock_listdir.assert_called_once_with(mock_assets_dir_on_disk)

    @patch('scripts.extraction.markdown_formatter.os.path.exists')
    @patch('scripts.extraction.markdown_formatter.os.listdir')
    def test_post_process_markdown_image_linking_problematic(self, mock_listdir, mock_exists, formatter_instance: MarkdownFormatter):
        mock_exists.return_value = True
        mock_listdir.return_value = [] # No images successfully saved on disk

        # LLM generates a reference that implies page 1, image/figure 1
        content = "Text with ![A blank image](page1-fig1.png) that should be a placeholder."
        metadata = {'unit_id': 'problem', 'unit_title_id': 'problematic_image_test'}
        
        mock_assets_dir_on_disk = os.path.join(TEST_OUTPUT_DIR, f"{metadata['unit_title_id']}{settings.IMAGE_ASSETS_SUFFIX}")
        image_extraction_results = {
            'success': True, 'extracted_count': 0, 'failed_count': 1,
            'problematic_images': [{'page': 1, 'index_on_page': 0, 'issue': 'Image is blank', 'issue_type': ImageIssueType.BLANK.value}],
            'errors': [], 'output_dir': mock_assets_dir_on_disk,
            'report_path': os.path.join(mock_assets_dir_on_disk, 'report.md')
        }

        processed_content = formatter_instance.post_process_markdown(
            content, metadata, image_extraction_results,
            original_pdf_path=f"{metadata['unit_title_id']}.pdf"
        )
        
        expected_placeholder_path = f"./{metadata['unit_title_id']}{settings.IMAGE_ASSETS_SUFFIX}/placeholder-blank.png"
        # The alt text should now reflect the issue because it was identified as problematic
        assert f"![A blank image (Issue: {ImageIssueType.BLANK.value})]({expected_placeholder_path})" in processed_content
        assert "<!-- WARNING: Image from Page 1, Index 1 had an issue: blank_image. Details: Image is blank. Using placeholder. -->" in processed_content


    def test_extract_and_format_orchestration(self, formatter_instance: MarkdownFormatter, mock_pdf_reader):
        dummy_pdf_path = "test_files/dummy.pdf"
        pdf_info_for_reader = {
            'method': 'direct', 'data': b'sample pdf data',
            'path': dummy_pdf_path, 'normalized_path': os.path.normpath(dummy_pdf_path),
            'error': None
        }
        # We provide pdf_info_for_reader directly to extract_and_format, so PDFReader.read_pdf_from_path
        # is not called by the method under test.
        
        mock_pdf_reader._generate_content_direct.return_value = MagicMock(text="## Raw Title\nRaw Content from Gemini.")

        custom_image_report = {
            'success': True, 'extracted_count': 0, 'failed_count': 0,
            'problematic_images': [], 'metrics': {}, 'errors': [],
            'output_dir': os.path.join(TEST_OUTPUT_DIR, f'dummy_orchestration{settings.IMAGE_ASSETS_SUFFIX}'),
            'report_path': os.path.join(TEST_OUTPUT_DIR, f'dummy_orchestration{settings.IMAGE_ASSETS_SUFFIX}', 'report.md')
        }
        formatter_instance.image_extractor.extract_images_from_pdf.return_value = custom_image_report

        metadata = formatter_instance.extract_metadata_from_path(dummy_pdf_path)
        metadata['unit_title'] = "Orchestration Test Title"

        result = formatter_instance.extract_and_format(pdf_info_for_reader, metadata)

        assert result['success']
        assert "unit-title: Orchestration Test Title" in result['content']
        assert "Raw Content from Gemini." in result['content']
        assert "<!-- SECTION: INTRODUCTION -->" in result['content']

        # Assert that the methods *called by extract_and_format* were invoked
        mock_pdf_reader._generate_content_direct.assert_called_once()
        formatter_instance.image_extractor.extract_images_from_pdf.assert_called_once()


# --- Main execution for running this test file directly (optional) ---
def main_test_runner():
    parser = argparse.ArgumentParser(description='Test markdown extraction.')
    parser.add_argument('--pdf', help='Path to a specific PDF file for E2E test')
    parser.add_argument('--output', help='Path to save the E2E test output markdown file')
    args = parser.parse_args()

    print("Running End-to-End Smoke Test (if PDF available)...")
    try:
        e2e_pdf_path = args.pdf or os.path.join(settings.PDF_SOURCE_DIR, DUMMY_PDF_FILENAME)
        if not os.path.exists(e2e_pdf_path) and e2e_pdf_path.endswith(DUMMY_PDF_FILENAME):
            print(f"Dummy PDF for E2E test not found at {e2e_pdf_path}. Skipping E2E test when run directly.")
        else:
            test_end_to_end_markdown_extraction_smoke(e2e_pdf_path, args.output)
            print("\nE2E smoke test function completed (check output for PASS/FAIL based on asserts).")
    except AssertionError as e:
        print(f"\nE2E smoke test function FAILED: {e}")
    except Exception as e:
        print(f"\nE2E smoke test function ERRORED: {e}")

    print("\nUnit tests should be run using `pytest` for proper execution and reporting.")

if __name__ == "__main__":
    print("This script contains pytest tests. Recommended: `pytest scripts/extraction/tests/test_markdown_formatter.py -v`")
    print("Running main_test_runner for a basic E2E check (if a PDF is found/provided)...")
    setup_module(None)
    main_test_runner()
    teardown_module(None)