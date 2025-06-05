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
from scripts.extraction.image_processor import ImageProcessor
# Import original ImageValidator for type checking if needed, and ImageIssueType
from scripts.utils.image_validation import ImageValidator as OriginalImageValidator, ImageIssueType


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
    def __init__(self, *args, **kwargs): # Accept args and kwargs like the original
        self._validation_result = MagicMock()
        self._validation_result.is_valid = True
        self._validation_result.details = None
        self._validation_result.issue_type = None
        # Provide default metrics to avoid issues if accessed before set_validation_result
        self._validation_result.metrics = {"size": "default_size", "format": "default_format", "is_valid": True}


    def set_validation_result(self, is_valid: bool, details: str = None, issue_type: ImageIssueType = None, metrics: Dict = None):
        self._validation_result.is_valid = is_valid
        self._validation_result.details = details
        self._validation_result.issue_type = issue_type
        if metrics is not None:
            self._validation_result.metrics = metrics
        # Ensure is_valid is also in metrics for consistency with how result['validation_info'] might be populated
        self._validation_result.metrics['is_valid'] = is_valid


    def validate_image_file(self, path):
        # Add path to metrics for easier debugging/assertion
        self._validation_result.metrics['validated_path'] = path
        return self._validation_result


# Remove the class-level patch:
# @patch('scripts.extraction.image_processor.ImageValidator', new=MockImageValidator)
class TestImageProcessor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Initialize processor with real validator first
        self.processor = ImageProcessor(MOCK_CONFIG)

        # Replace the validator instance on self.processor with our mock
        self.mock_validator_replacement = MockImageValidator(
            min_width=MOCK_CONFIG["min_width"],
            min_height=MOCK_CONFIG["min_height"],
            supported_formats=MOCK_CONFIG["supported_formats"]
        )
        self.processor.validator = self.mock_validator_replacement
        # self.mock_validator_instance now refers to the mock we control
        self.mock_validator_instance = self.processor.validator


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
        self.assertTrue(result['validation_info']['is_valid'])
        self.assertEqual(result['validation_info']['validated_path'], output_path)
        self.assertFalse(result['processing_details'].get('resize_applied', False))

        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
        mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_success_with_resize_width(self, mock_makedirs, mock_save):
        """Test processing/saving a large image (resize by overall constraints), validation succeeds."""
        output_path = os.path.join(self.temp_dir, "large_image_resized.png")
        # The large_image is 1000x800, max is 800x600.
        # Scale factor for width: 800/1000 = 0.8.
        # Scale factor for height: 600/800 = 0.75.
        # Min scale factor is 0.75.
        # New size should be 1000*0.75 x 800*0.75 = 750x600.
        expected_resized_size = (750, 600) # Corrected expected size

        # Mock the resize operation on the PIL Image object
        # Create a new image instance for the return_value of resize to avoid issues with closed images
        resized_pil_image = Image.new('RGB', expected_resized_size)
        with patch.object(self.large_image, 'resize', return_value=resized_pil_image) as mock_resize:
            self.mock_validator_instance.set_validation_result(True, metrics={'size': f'{expected_resized_size[0]}x{expected_resized_size[1]}', 'format': 'png'})

            result = self.processor.process_and_save_image(self.large_image, output_path)

            self.assertTrue(result['success'])
            self.assertEqual(result['path'], output_path)
            self.assertIsNone(result['issue'])
            self.assertIsNone(result['issue_type'])
            self.assertTrue(result['validation_info']['is_valid'])
            self.assertTrue(result['processing_details'].get('resize_applied', False))
            self.assertEqual(result['processing_details'].get('original_dimensions'), '1000x800')
            self.assertEqual(result['processing_details'].get('resized_dimensions'), f'{expected_resized_size[0]}x{expected_resized_size[1]}') # Corrected

            mock_resize.assert_called_once_with(expected_resized_size, Image.Resampling.LANCZOS)
            mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
            mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)
        resized_pil_image.close()


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_success_with_resize_height(self, mock_makedirs, mock_save):
        """Test processing/saving a large tall image (resize by height), validation succeeds."""
        output_path = os.path.join(self.temp_dir, "large_tall_image_resized.png")
        # The large_tall_image is 700x900, max is 800x600. Scale factor is 600/900 = 2/3.
        # New size should be 700*(2/3) x 900*(2/3) = ~466x600.
        expected_resized_size = (466, 600)

        resized_pil_image = Image.new('RGB', expected_resized_size)
        with patch.object(self.large_tall_image, 'resize', return_value=resized_pil_image) as mock_resize:
             self.mock_validator_instance.set_validation_result(True, metrics={'size': f'{expected_resized_size[0]}x{expected_resized_size[1]}', 'format': 'png'})

             result = self.processor.process_and_save_image(self.large_tall_image, output_path)

             self.assertTrue(result['success'])
             self.assertTrue(result['processing_details'].get('resize_applied', False))
             self.assertEqual(result['processing_details'].get('original_dimensions'), '700x900')
             self.assertEqual(result['processing_details'].get('resized_dimensions'), '466x600')

             mock_resize.assert_called_once_with(expected_resized_size, Image.Resampling.LANCZOS)
             mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)
        resized_pil_image.close()


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs')
    def test_process_and_save_validation_failure(self, mock_makedirs, mock_save):
        """Test processing/saving where validation fails after saving."""
        output_path = os.path.join(self.temp_dir, "invalid_image.png")

        self.mock_validator_instance.set_validation_result(
            False,
            details="Validation failed: image too small post-save",
            issue_type=ImageIssueType.SIZE_ISSUES,
            metrics={'size': '45x45'}
        )

        result = self.processor.process_and_save_image(self.medium_image, output_path)

        self.assertFalse(result['success'])
        self.assertEqual(result['path'], output_path)
        self.assertIn('Validation failed', result['issue'])
        self.assertEqual(result['issue_type'], ImageIssueType.SIZE_ISSUES.value)
        self.assertFalse(result['validation_info']['is_valid'])
        self.assertEqual(result['validation_info']['validated_path'], output_path)

        mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)
        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)


    @patch('scripts.extraction.image_processor.Image.Image.save')
    @patch('scripts.extraction.image_processor.os.makedirs', side_effect=OSError("Mock save directory error"))
    def test_process_and_save_makedirs_failure(self, mock_makedirs, mock_save):
        """Test handling error during directory creation."""
        output_path = "/invalid/path/to/save/image.png" # Intentionally invalid for os.makedirs

        result = self.processor.process_and_save_image(self.medium_image, output_path)

        self.assertFalse(result['success'])
        self.assertEqual(result['path'], output_path)
        self.assertIn('Error during image processing or saving', result['issue'])
        self.assertEqual(result['issue_type'], 'processing_error')
        mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
        mock_save.assert_not_called()
        # Check that validate_image_file was not called on our mock
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
        self.assertNotIn('validated_path', self.mock_validator_instance._validation_result.metrics)


    def test_process_and_save_validation_disabled(self):
        """Test processing/saving when validation is disabled."""
        config_no_validation = MOCK_CONFIG.copy()
        config_no_validation['validate_images'] = False
        processor_no_validation = ImageProcessor(config_no_validation)
        # processor_no_validation.validator is now a real OriginalImageValidator

        output_path = os.path.join(self.temp_dir, "no_validation.png")

        # We need to patch _save_image on processor_no_validation
        # And also patch validate_image_file on its *actual* validator instance
        with patch.object(processor_no_validation, '_save_image') as mock_internal_save_method, \
             patch.object(processor_no_validation.validator, 'validate_image_file') as mock_validate_method_on_real_validator:

            result = processor_no_validation.process_and_save_image(self.medium_image, output_path)

            self.assertTrue(result['success'])
            self.assertEqual(result['path'], output_path)
            self.assertIsNone(result['issue'])
            self.assertIsNone(result['issue_type'])
            self.assertEqual(result['validation_info'], {}) # Validation info should be empty

            mock_internal_save_method.assert_called_once()
            mock_validate_method_on_real_validator.assert_not_called() # Crucial check


    def test_save_image_format_jpg(self):
        """Test saving image as JPG."""
        config_jpg = MOCK_CONFIG.copy()
        config_jpg['image_format'] = 'jpg' # Will be canonicalized to JPEG
        config_jpg['quality'] = 80
        processor_jpg = ImageProcessor(config_jpg)

        output_path = os.path.join(self.temp_dir, "test_image.jpg")
        mock_image = MagicMock(spec=Image.Image)
        mock_image.mode = 'RGB'

        with patch('scripts.extraction.image_processor.os.makedirs') as mock_makedirs:
            with patch.object(mock_image, 'save') as mock_save:
                 processor_jpg._save_image(mock_image, output_path, {})

                 mock_makedirs.assert_called_once_with(os.path.dirname(output_path), exist_ok=True)
                 mock_save.assert_called_once_with(output_path, format='JPEG', quality=80, optimize=True)


    def test_save_image_format_png_rgba_to_rgb_for_jpg(self):
        """Test saving RGBA image as JPG (should convert to RGB)."""
        config_jpg = MOCK_CONFIG.copy()
        config_jpg['image_format'] = 'jpg' # Will be canonicalized to JPEG
        processor_jpg = ImageProcessor(config_jpg)

        output_path = os.path.join(self.temp_dir, "test_rgba_jpg.jpg")
        mock_image_rgba = MagicMock(spec=Image.Image)
        mock_image_rgba.mode = 'RGBA'
        mock_image_rgb = MagicMock(spec=Image.Image)
        mock_image_rgb.mode = 'RGB' # Mock the converted image's mode

        with patch('scripts.extraction.image_processor.os.makedirs'):
            with patch.object(mock_image_rgba, 'convert', return_value=mock_image_rgb) as mock_convert:
                with patch.object(mock_image_rgb, 'save') as mock_save_rgb: # Save is called on the converted image
                    processor_jpg._save_image(mock_image_rgba, output_path, {})

                    mock_convert.assert_called_once_with('RGB')
                    mock_save_rgb.assert_called_once_with(output_path, format='JPEG', quality=MOCK_CONFIG['quality'], optimize=True)


    def test_save_image_format_png(self):
        """Test saving image as PNG."""
        config_png = MOCK_CONFIG.copy()
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
        config_png = MOCK_CONFIG.copy()
        processor_png = ImageProcessor(config_png)

        output_path = os.path.join(self.temp_dir, "test_image_rgba.png")
        mock_image = MagicMock(spec=Image.Image)
        mock_image.mode = 'RGBA'
        mock_image.getbands.return_value = ('R', 'G', 'B', 'A')

        with patch('scripts.extraction.image_processor.os.makedirs'):
            with patch.object(mock_image, 'convert') as mock_convert:
                with patch.object(mock_image, 'save') as mock_save:
                    processor_png._save_image(mock_image, output_path, {})

                    mock_convert.assert_not_called()
                    mock_save.assert_called_once_with(output_path, format='PNG', compress_level=9)


    def test_resize_image_no_resize_needed(self):
        """Test resize method when no resizing is needed."""
        processing_details = {}
        resized_image = self.processor._resize_image(self.medium_image, processing_details)

        self.assertEqual(resized_image.size, (100, 100))
        self.assertEqual(processing_details.get('original_dimensions'), '100x100')
        self.assertFalse(processing_details.get('resize_applied', False))
        self.assertNotIn('resized_dimensions', processing_details)

    def test_resize_image_resize_needed_width(self): # Name implies width is limiter, but it's overall
        """Test resize method when image exceeds max dimensions (height is more limiting)."""
        processing_details = {}
        # large_image is 1000x800, max is 800x600
        # Scale factor for width: 800/1000 = 0.8. Height: 600/800 = 0.75. Min is 0.75.
        # New size: 1000*0.75=750, 800*0.75=600.
        expected_size = (750, 600) # Corrected

        resized_pil_image = Image.new('RGB', expected_size)
        with patch.object(self.large_image, 'resize', return_value=resized_pil_image) as mock_resize:
            resized_image = self.processor._resize_image(self.large_image, processing_details)

            self.assertEqual(resized_image.size, expected_size)
            self.assertEqual(processing_details.get('original_dimensions'), '1000x800')
            self.assertTrue(processing_details.get('resize_applied', False))
            self.assertEqual(processing_details.get('resized_dimensions'), f'{expected_size[0]}x{expected_size[1]}')

            mock_resize.assert_called_once_with(expected_size, Image.Resampling.LANCZOS)
        resized_pil_image.close()


    def test_resize_image_resize_needed_height(self):
        """Test resize method when height is the limiting factor."""
        processing_details = {}
        # large_tall_image is 700x900, max is 800x600
        # Scale factor for width: 800/700 > 1. Height: 600/900 = 2/3. Min is 2/3.
        # New size: 700*(2/3)=466, 900*(2/3)=600.
        expected_size = (466, 600)

        resized_pil_image = Image.new('RGB', expected_size)
        with patch.object(self.large_tall_image, 'resize', return_value=resized_pil_image) as mock_resize:
             resized_image = self.processor._resize_image(self.large_tall_image, processing_details)

             self.assertEqual(resized_image.size, expected_size)
             self.assertEqual(processing_details.get('original_dimensions'), '700x900')
             self.assertTrue(processing_details.get('resize_applied', False))
             self.assertEqual(processing_details.get('resized_dimensions'), f'{expected_size[0]}x{expected_size[1]}')

             mock_resize.assert_called_once_with(expected_size, Image.Resampling.LANCZOS)
        resized_pil_image.close()

    def test_resize_image_aspect_ratio_disabled(self):
        """
        Test _resize_image method directly.
        It should still resize and maintain aspect ratio as it doesn't use the maintain_aspect_ratio flag itself.
        """
        config_no_aspect = MOCK_CONFIG.copy()
        config_no_aspect['maintain_aspect_ratio'] = False # This flag affects process_and_save_image
        processor_no_aspect = ImageProcessor(config_no_aspect) # _resize_image is called on this

        processing_details = {}
        # large_image is 1000x800, max is 800x600.
        # _resize_image will calculate scale factor: min(800/1000, 600/800) = min(0.8, 0.75) = 0.75
        # Expected size: (1000*0.75, 800*0.75) = (750, 600)
        expected_resized_size = (750, 600)

        # We need to mock the 'resize' method of the actual self.large_image PIL object
        resized_pil_image = Image.new('RGB', expected_resized_size)
        with patch.object(self.large_image, 'resize', return_value=resized_pil_image) as mock_pil_resize:
            # Call _resize_image on the processor configured with maintain_aspect_ratio=False
            # The _resize_image method of ImageProcessor itself doesn't check this flag.
            resized_image_obj = processor_no_aspect._resize_image(self.large_image, processing_details)

            self.assertEqual(resized_image_obj.size, expected_resized_size)
            self.assertTrue(processing_details.get('resize_applied'))
            self.assertEqual(processing_details.get('resized_dimensions'), f'{expected_resized_size[0]}x{expected_resized_size[1]}')
            self.assertEqual(processing_details.get('original_dimensions'), '1000x800')
            mock_pil_resize.assert_called_once_with(expected_resized_size, Image.Resampling.LANCZOS)
        resized_pil_image.close()


if __name__ == '__main__':
    unittest.main()