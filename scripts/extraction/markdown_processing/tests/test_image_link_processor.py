# scripts/extraction/markdown_processing/tests/test_image_link_processor.py
"""Unit tests for the ImageLinkProcessor."""
import pytest
from unittest.mock import patch, MagicMock
import os

# To import settings and ImageIssueType correctly if tests are run from project root:
from scripts.config import settings
from scripts.utils.image_validation import ImageIssueType


class TestImageLinkProcessor:
    @pytest.fixture
    def processor(self):
        # Import the class to be tested
        from scripts.extraction.markdown_processing.image_link_processor import ImageLinkProcessor
        return ImageLinkProcessor()

    @pytest.fixture
    def mock_assets_dir(self, tmp_path):
        assets_path = tmp_path / "test_unit_id-img-assets"
        assets_path.mkdir()
        return str(assets_path) 

    def test_process_image_links_simple_sequential_match(self, processor, mock_assets_dir):
        # Create dummy files with the new naming convention
        (open(os.path.join(mock_assets_dir, "fig1-page1-img1.png"), "w")).write("dummy")
        (open(os.path.join(mock_assets_dir, "fig2-page1-img2.png"), "w")).write("dummy")

        content = """Some text ![Alt for image 1](image1.png) and ![Alt for image 2](another/path/image2.jpg)."""
        unit_title_id = "test_unit_id"
        image_extraction_results = {
            'problematic_images': [],
            'output_dir': mock_assets_dir # Ensure output_dir is provided
        }
        
        # Mock os.path.isfile to return True for the dummy files
        def mock_isfile_side_effect(path):
            return path.endswith((".png", ".jpg"))

        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir') as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists') as mock_exists, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.isfile', side_effect=mock_isfile_side_effect):
            
            mock_exists.return_value = True 
            mock_listdir.return_value = ["fig1-page1-img1.png", "fig2-page1-img2.png"]

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )
        
        expected_path_base = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        assert f"![Alt for image 1]({expected_path_base}/fig1-page1-img1.png)" in processed_content
        assert f"![Alt for image 2]({expected_path_base}/fig2-page1-img2.png)" in processed_content
        mock_listdir.assert_called_once_with(mock_assets_dir)


    def test_process_image_links_problematic_image_uses_placeholder(self, processor, mock_assets_dir):
        unit_title_id = "problem_unit"
        # Problematic images: 'page' is 1-indexed, 'index_on_page' is 0-indexed
        image_extraction_results = {
            'problematic_images': [{
                'page': 1, 'index_on_page': 0, 
                'issue': 'Image is blank', 'issue_type': ImageIssueType.BLANK.value
            }],
            'extracted_count': 0, 'failed_count': 1,
            'output_dir': mock_assets_dir
        }
        # MD path uses legacy "page1-img1" which _parse_page_index_from_md should handle
        # It will parse to page_num=1 (1-idx), img_idx_on_page=0 (0-idx)
        content = "![A blank image from page 1, image 1](p1_img1.png)"

        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir') as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists') as mock_exists:
            
            mock_exists.return_value = True
            mock_listdir.return_value = [] 

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )

        expected_path_base = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        placeholder_name = "placeholder-blank.png"
        assert f"![A blank image from page 1, image 1 (Issue: {ImageIssueType.BLANK.value})]({expected_path_base}/{placeholder_name})" in processed_content
        assert f"<!-- WARNING: Image from Page 1, Index 1 had an issue: Image is blank. Using placeholder. -->" in processed_content


    def test_process_image_links_match_by_filename_and_alt_text_parsing_new_format(self, processor, mock_assets_dir):
        # Disk image uses new format
        (open(os.path.join(mock_assets_dir, "fig1-page2-img3.png"), "w")).write("dummy")
        unit_title_id = "complex_match_new"
        image_extraction_results = {'problematic_images': [], 'output_dir': mock_assets_dir}

        content = """
        ![Figure on page 2 image 3](some_generic_name.png) 
        ![Another one](prefix-fig1-page2-img3-suffix.png) 
        """
        # Mock os.path.isfile
        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir') as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists') as mock_exists, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.isfile', return_value=True):
            mock_exists.return_value = True
            mock_listdir.return_value = ["fig1-page2-img3.png"]

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )
        
        expected_img_path = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}/fig1-page2-img3.png"
        # Both MD references should resolve to the same disk image due to specific P/I matching
        assert processed_content.count(expected_img_path) == 2 
        assert f"![Figure on page 2 image 3]({expected_img_path})" in processed_content # Parsed from alt text
        assert f"![Another one]({expected_img_path})" in processed_content # Parsed from MD path (new format)


    def test_process_image_links_match_by_filename_and_alt_text_parsing_legacy_format(self, processor, mock_assets_dir):
        # Disk image uses legacy format
        (open(os.path.join(mock_assets_dir, "actual-disk-page2-img3.png"), "w")).write("dummy")
        unit_title_id = "complex_match_legacy"
        image_extraction_results = {'problematic_images': [], 'output_dir': mock_assets_dir}

        content = """
        ![Figure on page 2 image 3](some_generic_name.png)
        ![Another one](prefix-page2-img3-suffix.png) 
        """
        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir') as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists') as mock_exists, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.isfile', return_value=True):
            mock_exists.return_value = True
            mock_listdir.return_value = ["actual-disk-page2-img3.png"]

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )
        
        expected_img_path = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}/actual-disk-page2-img3.png"
        assert processed_content.count(expected_img_path) == 2 
        assert f"![Figure on page 2 image 3]({expected_img_path})" in processed_content # Parsed from alt text
        assert f"![Another one]({expected_img_path})" in processed_content # Parsed from MD path (legacy format)


    def test_process_image_links_no_assets_dir_uses_generic_placeholder(self, processor):
        content = "![Local image](local.png)"
        unit_title_id = "no_assets_dir_test"
        # image_extraction_results is None or output_dir is None
        image_extraction_results_none = None
        
        processed_content = processor.process_image_links(
            content, unit_title_id, image_extraction_results_none, None 
        )
        
        expected_path_base = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        assert f"![Local image]({expected_path_base}/placeholder-image.png)" in processed_content
        assert "<!-- WARNING: Image assets directory missing (None). Local image links may be placeholders. -->" in processed_content

        # Test with image_extraction_results present but actual_disk_img_assets_path is None
        image_extraction_results_no_path = {'problematic_images': [], 'output_dir': None}
        processed_content_2 = processor.process_image_links(
            content, unit_title_id, image_extraction_results_no_path, None
        )
        assert f"![Local image]({expected_path_base}/placeholder-image.png)" in processed_content_2
        assert "<!-- WARNING: Image assets directory missing (None). Local image links may be placeholders. -->" in processed_content_2


    def test_process_image_links_unused_disk_images_warning(self, processor, mock_assets_dir):
        # Disk images with new format
        (open(os.path.join(mock_assets_dir, "fig1-page1-img1.png"), "w")).write("dummy") # Used
        (open(os.path.join(mock_assets_dir, "fig2-page2-img1.png"), "w")).write("dummy") # Unused
        
        # MD path uses new format, or alt text that resolves to page 1, image 1 (0-indexed)
        content = "![Image from page 1 fig 1](fig1-page1-img1.png)"
        unit_title_id = "unused_test"
        image_extraction_results = {'problematic_images': [], 'output_dir': mock_assets_dir}

        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir') as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists') as mock_exists, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.isfile', return_value=True):
            mock_exists.return_value = True
            mock_listdir.return_value = ["fig1-page1-img1.png", "fig2-page2-img1.png"]

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )

        expected_used_path = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}/fig1-page1-img1.png"
        assert f"![Image from page 1 fig 1]({expected_used_path})" in processed_content
        assert "<!-- WARNING: 1 extracted images on disk were not referenced in the markdown: fig2-page2-img1.png. -->" in processed_content

    def test_skip_external_images(self, processor, mock_assets_dir):
        content = """
        ![Local image](local.png)
        ![External image](http://example.com/image.png)
        ![Absolute path image](/images/abs.png)
        ![Data URI image](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA)
        """
        unit_title_id = "external_skip"
        image_extraction_results = {'problematic_images': [], 'output_dir': mock_assets_dir}

        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir') as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists') as mock_exists, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.isfile', return_value=True):
            
            mock_exists.return_value = True
            mock_listdir.return_value = ["fig1-some-disk-image.png"] 

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )
        
        expected_local_path = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}/fig1-some-disk-image.png"
        assert f"![Local image]({expected_local_path})" in processed_content 
        assert "![External image](http://example.com/image.png)" in processed_content
        assert "![Absolute path image](/images/abs.png)" in processed_content
        assert "![Data URI image](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA)" in processed_content

    def test_empty_actual_disk_img_assets_path_but_extraction_results_exist(self, processor):
        content = "![Local image](local.png)"
        unit_title_id = "empty_path_test"
        # image_extraction_results exists but actual_disk_img_assets_path is None
        image_extraction_results = {'problematic_images': [], 'output_dir': None} 
        
        processed_content = processor.process_image_links(
            content, unit_title_id, image_extraction_results, None 
        )
        
        expected_path_base = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        assert f"![Local image]({expected_path_base}/placeholder-image.png)" in processed_content
        assert "<!-- WARNING: Image assets directory missing (None). Local image links may be placeholders. -->" in processed_content

    def test_file_not_found_for_listdir(self, processor, mock_assets_dir):
        content = "![Local image](local.png)"
        unit_title_id = "dir_not_found_test"
        image_extraction_results = {'problematic_images': [], 'output_dir': mock_assets_dir}

        with patch('scripts.extraction.markdown_processing.image_link_processor.os.listdir', side_effect=FileNotFoundError("Dir gone")) as mock_listdir, \
             patch('scripts.extraction.markdown_processing.image_link_processor.os.path.exists', return_value=True) as mock_exists: # Exists might be true before listdir fails

            processed_content = processor.process_image_links(
                content, unit_title_id, image_extraction_results, mock_assets_dir
            )
        
        expected_path_base = f"./{unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        # Since listdir fails, saved_image_files will be empty, leading to placeholder.
        assert f"![Local image (Image Not Found)]({expected_path_base}/placeholder-error.png)" in processed_content
        # No "unused images" warning because no images were found on disk.
        assert "unreferenced disk images" not in processed_content
        mock_listdir.assert_called_once_with(mock_assets_dir)