# scripts/extraction/image_processing/tests/test_extraction_strategies/test_base_strategy.py
import unittest
from unittest.mock import MagicMock
from PIL import Image
from typing import Dict, Any

# from scripts.extraction.image_processing.extraction_strategies.base_strategy import BaseExtractionStrategy # Not directly tested, but through ConcreteDummy
from ._test_helpers import MOCK_CONFIG, ConcreteDummyExtractionStrategy

class TestBaseExtractionStrategy(unittest.TestCase):

    def test_base_strategy_check_min_size_pass(self) -> None:
        """Test base strategy min size check passes."""
        strategy = ConcreteDummyExtractionStrategy(MOCK_CONFIG)
        # Use a MagicMock that directly has width and height attributes
        mock_image = MagicMock(spec=Image.Image)
        mock_image.width = 100
        mock_image.height = 100
        info: Dict[str, Any] = {}
        self.assertTrue(strategy._check_min_size(mock_image, info))
        self.assertNotIn('error', info)
        self.assertNotIn('issue_type', info)

    def test_base_strategy_check_min_size_fail(self) -> None:
        """Test base strategy min size check fails."""
        strategy = ConcreteDummyExtractionStrategy(MOCK_CONFIG)
        mock_image = MagicMock(spec=Image.Image)
        mock_image.width = 30
        mock_image.height = 30
        info: Dict[str, Any] = {}
        self.assertFalse(strategy._check_min_size(mock_image, info))
        self.assertIn('Image too small', info['error'])
        self.assertEqual(info['issue_type'], 'size_issues')
        self.assertIn('30x30', info['error'])
        self.assertIn(f"min: {MOCK_CONFIG['min_width']}x{MOCK_CONFIG['min_height']}", info['error'])

if __name__ == '__main__':
    unittest.main()