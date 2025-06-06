# scripts/extraction/markdown_processing/tests/test_frontmatter_generator.py
"""Unit tests for the FrontmatterGenerator."""
import pytest
from datetime import datetime, date # Added date for clarity, though str() works on datetime.date
import yaml # To parse and validate generated YAML

# from scripts.extraction.markdown_processing.frontmatter_generator import FrontmatterGenerator

class TestFrontmatterGenerator:

    @pytest.fixture
    def generator(self):
        from scripts.extraction.markdown_processing.frontmatter_generator import FrontmatterGenerator
        return FrontmatterGenerator()

    def test_generate_frontmatter_all_fields(self, generator):
        # current_date = datetime.now().strftime('%Y-%m-%d') # Not needed here as date is fixed
        metadata = {
            'unit_id': 'U001', 
            'unit_title_id': 'test_unit_one', 
            'unit_title': 'Test Unit One: An Adventure',
            'phase': 'AS Level', 
            'subject': 'Computer Science & Programming', 
            'parent_module_id': 'M001',
            'parent_course_id': 'C001', 
            'batch_id': 'B001-XYZ',
            'extraction_date': '2023-10-26', # This is a string, as it would be from MetadataExtractor
            'extractor_name': "Test Extractor"
        }
        frontmatter_str = generator.generate_frontmatter(metadata)
        
        assert frontmatter_str.startswith("---")
        assert frontmatter_str.endswith("---")
        
        # Parse the YAML to check structure and values
        parsed_yaml = yaml.safe_load(frontmatter_str.strip("---"))
        
        assert parsed_yaml['unit-id'] == 'U001'
        assert parsed_yaml['unit-title-id'] == "test_unit_one" # Quoted
        assert parsed_yaml['unit-title'] == "Test Unit One: An Adventure" # Quoted
        assert parsed_yaml['phase'] == 'AS Level'
        assert parsed_yaml['subject'] == "Computer Science & Programming" # Quoted
        assert parsed_yaml['parent-module-id'] == 'M001'
        assert parsed_yaml['parent-course-id'] == 'C001'
        assert parsed_yaml['batch-id'] == 'B001-XYZ'
        # Compare string representation of the parsed date object
        assert str(parsed_yaml['extraction-date']) == '2023-10-26' 
        assert parsed_yaml['extractor-name'] == "Test Extractor" # Quoted

    def test_generate_frontmatter_default_fields(self, generator):
        current_date_str = datetime.now().strftime('%Y-%m-%d')
        metadata = {
            'unit_title_id': 'minimal_unit' # Only one non-default field
            # extraction_date will be defaulted by FrontmatterGenerator if not provided
        }
        frontmatter_str = generator.generate_frontmatter(metadata)
        parsed_yaml = yaml.safe_load(frontmatter_str.strip("---"))

        assert parsed_yaml['unit-id'] == 'UNI0000'
        assert parsed_yaml['unit-title-id'] == "minimal_unit"
        assert parsed_yaml['unit-title'] == "Unknown Title"
        assert parsed_yaml['phase'] == 'Unknown'
        assert parsed_yaml['subject'] == "Unknown Subject"
        assert parsed_yaml['parent-module-id'] == 'MOD0000'
        assert parsed_yaml['parent-course-id'] == 'COU0000'
        assert parsed_yaml['batch-id'] == 'BAT0001'
        # Compare string representation of the parsed date object
        assert str(parsed_yaml['extraction-date']) == current_date_str
        assert parsed_yaml['extractor-name'] == "Automated Extraction"

    def test_generate_frontmatter_empty_metadata(self, generator):
        current_date_str = datetime.now().strftime('%Y-%m-%d')
        metadata = {}
        frontmatter_str = generator.generate_frontmatter(metadata)
        parsed_yaml = yaml.safe_load(frontmatter_str.strip("---"))

        assert parsed_yaml['unit-id'] == 'UNI0000'
        assert parsed_yaml['unit-title-id'] == "unknown_title_id"
        assert parsed_yaml['unit-title'] == "Unknown Title"
        # ... and so on for all defaults
        # Compare string representation of the parsed date object
        assert str(parsed_yaml['extraction-date']) == current_date_str