# scripts/extraction/tests/test_image_processor.py

"""Unit tests for the ImageProcessor."""

import unittest
from unittest.mock import MagicMock, patch, call, ANY
from PIL import Image
import os
import tempfile
import shutil
import io
from typing import Dict


# Import the ImageProcessor and its dependency
from ..image_processor import ImageProcessor
from ...utils.image_validation import ImageValidator, ImageIssueType # Adjust import as necessary

# Mock configuration
MOCK_CONFIG = {
    "image_format": "png",
    "quality": 95,
    "max_width": 800, # Use smaller max size for easier testing
    "max_height": 600,
    "min_width": 50,
    "min_height": 50,
    "supported_formats": ["png", "jpg", "jpeg"],
    "validate_images": True,
    "maintain_aspect_ratio": True,
}

class MockImageValidator:
    """Mock validator returning configurable results."""
    def __init__(self, *args, **kwargs):
        self._validation_result = MagicMock()
        self._validation_result.is_valid = True
        self._validation_result.details = None
        self._validation_result.issue_type = None
        self._validation_result.metrics = {"size": "100x100", "format": "png"}

    def set_validation_result(self, is_valid: bool, details: str = None, issue_type: ImageIssueType = None, metrics: Dict = None):
        self._validation_result.is_valid = is_valid
        self._validation_result.details = details
        self._validation_result.issue_type = issue_type
        self._validation_result.metrics = metrics if metrics is not None else {}

    def validate_image_file(self, path):
        # Add path to metrics for easier debugging/assertion
        self._validation_result.metrics['validated_path'] = path
        return self._validation_result


@patch('scripts.extraction.image_processor.ImageValidator', new=MockImageValidator)
class TestImageProcessor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.processor = ImageProcessor(MOCK_CONFIG)
        self.mock_validator_instance = self.processor.validator # Get the mock instance created by __init__

        # Create dummy PIL Images
        self.small_image = Image.new('RGB', (40, 40)) # Smaller than min
        self.medium_image = Image.new('RGB', (100, 100)) # Within min/max
        self.large_image = Image.new('RGB', (1000, 800)) # Larger than max
        self.large_tall_image = Image.new('RGB', (700, 900)) # Taller than max height, within max width

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        self.small_image.close()
        self.medium_image.close()
        self.large_image.close()
        self.large_tall_image.close()

    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_success_no_resize(self, mock_makedirs, mock_save):
        """Test processing/saving a medium image (no resize needed), validation succeeds."""
        output_path = os.path.join(self.temp_dir, "medium_image.png")

        # Configure validator to succeed
        self.mock_validator_instance.set_validation_result(True, metrics={'size': '100x100', 'format': 'png'})

        result = self.processor.process_and_save_image(self.medium_image, output_path)

        self.assertTrue(result['success'])
        self.assertEqual(result['path'], output_path)
        self.assertIsNone(result['issue'])
        self.assertIsNone(result['issue_type'])
        self.assertTrue(result['validation_info']['is_valid']) # Check through mock validator result
        self.assertEqual(result['validation_info']['validated_path'], output_path) # Ensure validator was called with correct path
        self.assertFalse(result['processing_details'].get('resize_applied', False)) # No resize should happen

        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
        mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_success_with_resize_width(self, mock_makedirs, mock_save):
        """Test processing/saving a large image (resize by width), validation succeeds."""
        output_path = os.path.join(self.temp_dir, "large_image_resized.png")
        # The large_image is 1000x800, max is 800x600. Scale factor is 800/1000 = 0.8.
        # New size should be 1000*0.8 x 800*0.8 = 800x640.
        expected_resized_size = (800, 640)

        # Mock the resize operation on the PIL Image object
        with patch.object(self.large_image, 'resize', return_value=Image.new('RGB', expected_resized_size)) as mock_resize:
            # Configure validator to succeed for the *expected resized size*
            self.mock_validator_instance.set_validation_result(True, metrics={'size': f'{expected_resized_size[0]}x{expected_resized_size[1]}', 'format': 'png'})

            result = self.processor.process_and_save_image(self.large_image, output_path)

            self.assertTrue(result['success'])
            self.assertEqual(result['path'], output_path)
            self.assertIsNone(result['issue'])
            self.assertIsNone(result['issue_type'])
            self.assertTrue(result['validation_info']['is_valid'])
            self.assertTrue(result['processing_details'].get('resize_applied', False)) # Resize should happen
            self.assertEqual(result['processing_details'].get('original_dimensions'), '1000x800')
            self.assertEqual(result['processing_details'].get('resized_dimensions'), '800x640')


            mock_resize.assert_called_once_with(expected_resized_size, Image.Resampling.LANCZOS)
            mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
            # The save method is called on the result of the mock_resize
            mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_success_with_resize_height(self, mock_makedirs, mock_save):
        """Test processing/saving a large tall image (resize by height), validation succeeds."""
        output_path = os.path.join(self.temp_dir, "large_tall_image_resized.png")
        # The large_tall_image is 700x900, max is 800x600. Scale factor is 600/900 = 2/3.
        # New size should be 700*(2/3) x 900*(2/3) = ~466x600.
        expected_resized_size = (466, 600) # Integer calculation result might vary slightly, allow small tolerance or mock precisely

        # Mock the resize operation
        with patch.object(self.large_tall_image, 'resize', return_value=Image.new('RGB', expected_resized_size)) as mock_resize:
             self.mock_validator_instance.set_validation_result(True, metrics={'size': f'{expected_resized_size[0]}x{expected_resized_size[1]}', 'format': 'png'})

             result = self.processor.process_and_save_image(self.large_tall_image, output_path)

             self.assertTrue(result['success'])
             self.assertTrue(result['processing_details'].get('resize_applied', False))
             self.assertEqual(result['processing_details'].get('original_dimensions'), '700x900')
             self.assertEqual(result['processing_details'].get('resized_dimensions'), '466x600')

             mock_resize.assert_called_once_with(expected_resized_size, Image.Resampling.LANCZOS)
             mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_validation_failure(self, mock_makedirs, mock_save):
        """Test processing/saving where validation fails after saving."""
        output_path = os.path.join(self.temp_dir, "invalid_image.png")

        # Configure validator to FAIL
        self.mock_validator_instance.set_validation_result(
            False,
            details="Validation failed: image too small post-save",
            issue_type=ImageIssueType.SIZE_ISSUES,
            metrics={'size': '45x45'}
        )

        result = self.processor.process_and_save_image(self.medium_image, output_path)

        self.assertFalse(result['success']) # Overall success is False due to validation failure
        self.assertEqual(result['path'], output_path)
        self.assertIn('Validation failed', result['issue'])
        self.assertEqual(result['issue_type'], ImageIssueType.SIZE_ISSUES.value) # Issue type should come from validator
        self.assertFalse(result['validation_info']['is_valid'])
        self.assertEqual(result['validation_info']['validated_path'], output_path)

        mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)
        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs', side_effect=OSError("Mock save directory error"))
    def test_process_and_save_makedirs_failure(self, mock_makedirs, mock_save):
        """Test handling error during directory creation."""
        output_path = "/invalid/path/to/save/image.png"

        result = self.processor.process_and_save_image(self.medium_image, output_path)

        self.assertFalse(result['success'])
        self.assertEqual(result['path'], output_path)
        self.assertIn('Error during image processing or saving', result['issue'])
        self.assertEqual(result['issue_type'], 'processing_error')
        # Validation and save should not have been called if makedirs fails
        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
        mock_save.assert_not_called()
        # Validator instance is created but validate_image_file shouldn't be called
        self.assertNotIn('validated_path', self.mock_validator_instance._validation_result.metrics)


    @patch('scripts.extraction.image_processor.Image.Image.save', side_effect=IOError("Mock save error"))
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_save_failure(self, mock_makedirs, mock_save):
        """Test handling error during image saving."""
        output_path = os.path.join(self.temp_dir, "save_fail.png")

        result = self.processor.process_and_save_image(self.medium_image, output_path)

        self.assertFalse(result['success'])
        self.assertEqual(result['path'], output_path)
        self.assertIn('Error during image processing or saving', result['issue'])
        self.assertEqual(result['issue_type'], 'processing_error')
        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
        mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)
        # Validation should not be called if save fails
        self.assertNotIn('validated_path', self.mock_validator_instance._validation_result.metrics)


    def test_process_and_save_validation_disabled(self):
        """Test processing/saving when validation is disabled."""
        config_no_validation = MOCK_CONFIG.copy()
        config_no_validation['validate_images'] = False
        processor_no_validation = ImageProcessor(config_no_validation)

        output_path = os.path.join(self.temp_dir, "no_validation.png")

        # Ensure save succeeds
        with patch.object(processor_no_validation, '_save_image') as mock_save:
            result = processor_no_validation.process_and_save_image(self.medium_image, output_path)

            self.assertTrue(result['success']) # Success is true because save succeeded and validation is off
            self.assertEqual(result['path'], output_path)
            self.assertIsNone(result['issue'])
            self.assertIsNone(result['issue_type'])
            self.assertFalse(result['validation_info'].get('is_valid')) # Mock validator returns default True, but result success is based on validation_enabled
             # More accurately, the validation_info might reflect that validation was skipped.
             # The mock validator was never called to set 'validated_path'
            self.assertNotIn('validated_path', self.mock_validator_instance._validation_result.metrics)

            mock_save.assert_called_once() # Save should still happen


    def test_save_image_format_jpg(self):
        """Test saving image as JPG."""
        config_jpg = MOCK_CONFIG.copy()
        config_jpg['image_format'] = 'jpg'
        config_jpg['quality'] = 80
        processor_jpg = ImageProcessor(config_jpg)

        output_path = os.path.join(self.temp_dir, "test_image.jpg")
        mock_image = MagicMock(spec=Image.Image)
        mock_image.mode = 'RGB' # Ensure it's RGB for JPG

        with patch('scripts.extraction.image_processor.os.makedirs') as mock_makedirs:
            with patch.object(mock_image, 'save') as mock_save:
                 processor_jpg._save_image(mock_image, output_path, {})

                 mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
                 mock_save.assert_called_once_with(output_path, format='JPEG', quality=80, optimize=True)


    def test_save_image_format_png_rgba_to_rgb_for_jpg(self):
        """Test saving RGBA image as JPG (should convert to RGB)."""
        config_jpg = MOCK_CONFIG.copy()
        config_jpg['image_format'] = 'jpg'
        processor_jpg = ImageProcessor(config_jpg)

        output_path = os.path.join(self.temp_dir, "test_rgba_jpg.jpg")
        mock_image_rgba = MagicMock(spec=Image.Image)
        mock_image_rgba.mode = 'RGBA'
        mock_image_rgb = MagicMock(spec=Image.Image) # Mock the converted image

        with patch('scripts.extraction.image_processor.os.makedirs'):
            with patch.object(mock_image_rgba, 'convert', return_value=mock_image_rgb) as mock_convert:
                with patch.object(mock_image_rgb, 'save') as mock_save_rgb:
                    processor_jpg._save_image(mock_image_rgba, output_path, {})

                    mock_convert.assert_called_once_with('RGB')
                    mock_save_rgb.assert_called_once_with(output_path, format='JPEG', quality=95, optimize=True) # Use default quality


    def test_save_image_format_png(self):
        """Test saving image as PNG."""
        config_png = MOCK_CONFIG.copy() # Default is PNG
        processor_png = ImageProcessor(config_png)

        output_path = os.path.join(self.temp_dir, "test_image.png")
        mock_image = MagicMock(spec=Image.Image)
        mock_image.mode = 'RGB'

        with patch('scripts.extraction.image_processor.os.makedirs') as mock_makedirs:
            with patch.object(mock_image, 'save') as mock_save:
                 processor_png._save_image(mock_image, output_path, {})

                 mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
                 mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)

    def test_save_image_format_png_rgba(self):
        """Test saving RGBA image as PNG."""
        config_png = MOCK_CONFIG.copy() # Default is PNG
        processor_png = ImageProcessor(config_png)

        output_path = os.path.join(self.temp_dir, "test_image_rgba.png")
        mock_image = MagicMock(spec=Image.Image)
        mock_image.mode = 'RGBA'
        mock_image.getbands.return_value = ('R', 'G', 'B', 'A') # Indicate it has alpha

        # No convert should happen for RGBA -> PNG
        with patch('scripts.extraction.image_processor.os.makedirs'):
            with patch.object(mock_image, 'convert') as mock_convert:
                with patch.object(mock_image, 'save') as mock_save:
                    processor_png._save_image(mock_image, output_path, {})

                    mock_convert.assert_not_called()
                    mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)


    def test_resize_image_no_resize_needed(self):
        """Test resize method when no resizing is needed."""
        processing_details = {}
        resized_image = self.processor._resize_image(self.medium_image, processing_details) # 100x100 vs max 800x600

        self.assertEqual(resized_image.size, (100, 100))
        self.assertEqual(processing_details.get('original_dimensions'), '100x100')
        self.assertFalse(processing_details.get('resize_applied', False))
        self.assertNotIn('resized_dimensions', processing_details)

    def test_resize_image_resize_needed_width(self):
        """Test resize method when width is the limiting factor."""
        processing_details = {}
        # large_image is 1000x800, max is 800x600
        expected_size = (800, 640)

        # Mock the resize call on the image instance
        with patch.object(self.large_image, 'resize', return_value=Image.new('RGB', expected_size)) as mock_resize:
            resized_image = self.processor._resize_image(self.large_image, processing_details)

            self.assertEqual(resized_image.size, expected_size)
            self.assertEqual(processing_details.get('original_dimensions'), '1000x800')
            self.assertTrue(processing_details.get('resize_applied', False))
            self.assertEqual(processing_details.get('resized_dimensions'), f'{expected_size[0]}x{expected_size[1]}')

            mock_resize.assert_called_once_with(expected_size, Image.Resampling.LANCZOS)


    def test_resize_image_resize_needed_height(self):
        """Test resize method when height is the limiting factor."""
        processing_details = {}
        # large_tall_image is 700x900, max is 800x600
        expected_size = (466, 600)

        with patch.object(self.large_tall_image, 'resize', return_value=Image.new('RGB', expected_size)) as mock_resize:
             resized_image = self.processor._resize_image(self.large_tall_image, processing_details)

             self.assertEqual(resized_image.size, expected_size)
             self.assertEqual(processing_details.get('original_dimensions'), '700x900')
             self.assertTrue(processing_details.get('resize_applied', False))
             self.assertEqual(processing_details.get('resized_dimensions'), f'{expected_size[0]}x{expected_size[1]}')

             mock_resize.assert_called_once_with(expected_size, Image.Resampling.LANCZOS)

    def test_resize_image_aspect_ratio_disabled(self):
        """Test resize method when aspect ratio maintenance is disabled."""
        config_no_aspect = MOCK_CONFIG.copy()
        config_no_aspect['maintain_aspect_ratio'] = False
        processor_no_aspect = ImageProcessor(config_no_aspect)

        processing_details = {}
        # large_image is 1000x800, max is 800x600
        # If aspect ratio is not maintained and max is exceeded, behavior depends on implementation.
        # The current _resize_image only applies scaling if *any* dimension exceeds the max.
        # If maintain_aspect_ratio is False, the scale factor calculation might still happen,
        # but the resize logic is inside an `if self.maintain_aspect_ratio:` block.
        # So, if maintain_aspect_ratio is False, no resizing should occur *by this method*.
        resized_image = processor_no_aspect._resize_image(self.large_image, processing_details)

        self.assertEqual(resized_image.size, (1000, 800)) # Should be original size
        self.assertFalse(processing_details.get('resize_applied', False))
        self.assertNotIn('resized_dimensions', processing_details)
        self.assertEqual(processing_details.get('original_dimensions'), '1000x800')


if __name__ == '__main__':
    unittest.main()