# scripts/extraction/image_processing/tests/test_extraction_strategies/test_compression_retry_strategy.py
import unittest
from unittest.mock import MagicMock, patch, call
from PIL import Image
import io # For io.BytesIO

from scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy import CompressionRetryStrategy
from ._test_helpers import BaseStrategyTestCase, MOCK_CONFIG, create_mock_extract_image_data_helper

class TestCompressionRetryStrategy(BaseStrategyTestCase):

    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.Image.load') # Patch instance method
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.fitz.Document') # To mock doc.extract_image
    def test_compression_retry_extraction_success(self, MockFitzDocument: MagicMock, mock_pil_open: MagicMock, mock_pil_load: MagicMock) -> None:
        # Mock the document instance's extract_image method
        mock_doc_instance = MockFitzDocument.return_value # Not used directly, self.mock_doc is used
        valid_jpeg_data = create_mock_extract_image_data_helper(self.dummy_image, 'jpeg')
        self.mock_doc.extract_image = MagicMock(return_value=valid_jpeg_data) # Attach to self.mock_doc

        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (100, 100)
        mock_pil_image_instance.width = 100
        mock_pil_image_instance.height = 100
        mock_pil_image_instance.mode = 'RGB'
        mock_pil_image_instance.convert.return_value = mock_pil_image_instance # Assume no conversion needed or returns self
        mock_pil_image_instance.load = mock_pil_load # Assign the patched load
        mock_pil_image_instance.close = MagicMock()
        mock_pil_open.return_value = mock_pil_image_instance
        
        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNotNone(extracted_img)
        self.assertIsInstance(extracted_img, Image.Image)
        self.assertEqual(extracted_img.size, (100, 100))
        self.assertEqual(extracted_img.mode, 'RGB')
        self.assertTrue(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertEqual(info['dimensions'], '100x100')
        self.assertEqual(info['mode'], 'RGB')
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

        self.mock_doc.extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once()
        args, _ = mock_pil_open.call_args
        self.assertIsInstance(args[0], io.BytesIO)
        mock_pil_load.assert_called_once() # Check that Image.Image.load was called
        
        # The returned image should not be closed by the strategy
        # mock_pil_image_instance.close.assert_not_called() # This depends on convert logic
        if extracted_img: extracted_img.close()


    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.fitz.Document')
    def test_compression_retry_extraction_no_data(self, MockFitzDocument: MagicMock, mock_pil_open: MagicMock) -> None:
        self.mock_doc.extract_image = MagicMock(return_value={}) # Empty dict

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertIn('No raw image data found in extract_image result', info['error'])
        self.assertEqual(info['issue_type'], 'extraction_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.mock_doc.extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_not_called()

    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.Image.load')
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.fitz.Document')
    def test_compression_retry_extraction_invalid_data(self, MockFitzDocument: MagicMock, mock_pil_open: MagicMock, mock_pil_load: MagicMock) -> None:
        self.mock_doc.extract_image = MagicMock(return_value={"ext": "jpeg", "image": b'invalid_image_data'})

        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (100,100); mock_pil_image_instance.width=100; mock_pil_image_instance.height=100
        mock_pil_image_instance.mode = 'RGB'
        mock_pil_image_instance.convert.return_value = mock_pil_image_instance
        mock_pil_image_instance.load = mock_pil_load # Assign the patched load
        mock_pil_load.side_effect = IOError("Mock PIL load error") # Simulate load failure
        mock_pil_image_instance.close = MagicMock()
        mock_pil_open.return_value = mock_pil_image_instance

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertIn('Alternate compression extraction failed for xref 10: Error during image decoding: Mock PIL load error', info['error'])
        self.assertEqual(info['issue_type'], 'decoding_failed')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.mock_doc.extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once()
        mock_pil_load.assert_called_once()
        mock_pil_image_instance.close.assert_called_once() # Should be closed on error

    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.Image.load')
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.Image.open')
    @patch('scripts.extraction.image_processing.extraction_strategies.compression_retry_strategy.fitz.Document')
    def test_compression_retry_extraction_too_small(self, MockFitzDocument: MagicMock, mock_pil_open: MagicMock, mock_pil_load: MagicMock) -> None:
        valid_png_data = create_mock_extract_image_data_helper(self.small_image, 'png')
        self.mock_doc.extract_image = MagicMock(return_value=valid_png_data)

        mock_pil_image_instance = MagicMock(spec=Image.Image)
        mock_pil_image_instance.size = (30, 30)
        mock_pil_image_instance.width = 30
        mock_pil_image_instance.height = 30
        mock_pil_image_instance.mode = 'RGB'
        mock_pil_image_instance.convert.return_value = mock_pil_image_instance
        mock_pil_image_instance.load = mock_pil_load
        mock_pil_image_instance.close = MagicMock()
        mock_pil_open.return_value = mock_pil_image_instance

        strategy = CompressionRetryStrategy(MOCK_CONFIG)
        self.extraction_info = {}
        extracted_img, info = strategy.extract(self.mock_doc, self.mock_img_info, self.page_num, self.extraction_info)

        self.assertIsNone(extracted_img)
        self.assertFalse(info['success'])
        self.assertEqual(info['extraction_method'], 'alternate_compression')
        self.assertIn(f'Image too small: 30x30 (min: {MOCK_CONFIG["min_width"]}x{MOCK_CONFIG["min_height"]})', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertNotIn('dimensions', info)
        self.assertNotIn('mode', info)
        self.mock_doc.extract_image.assert_called_once_with(self.mock_img_info[0])
        mock_pil_open.assert_called_once()
        mock_pil_load.assert_called_once()
        mock_pil_image_instance.close.assert_called_once() # Closed because it's too small

if __name__ == '__main__':
    unittest.main()