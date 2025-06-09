from typing import Dict, Any
from unittest.mock import MagicMock

class MockStrategyA:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self, pdf_document, img_info, page_num, extraction_info_details_dict):
        extraction_info_details_dict['dimensions'] = '100x100'
        extraction_info_details_dict['mode'] = 'RGB'
        mock_image = MagicMock()
        return mock_image, {'success': True, 'details': extraction_info_details_dict}


class MockStrategyB:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self, pdf_document, img_info, page_num, extraction_info_details_dict):
        extraction_info_details_dict['dimensions'] = '200x200'
        extraction_info_details_dict['mode'] = 'L'
        mock_image = MagicMock()
        return mock_image, {'success': True, 'details': extraction_info_details_dict}


class MockStrategyC:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def extract(self, pdf_document, img_info, page_num, extraction_info_details_dict):
        extraction_info_details_dict['dimensions'] = '300x300'
        extraction_info_details_dict['mode'] = 'CMYK'
        mock_image = MagicMock()
        return mock_image, {'success': True, 'details': extraction_info_details_dict}
