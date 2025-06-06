# scripts/extraction/markdown_processing/tests/test_metadata_extractor.py
"""Unit tests for the MetadataExtractor."""
import pytest
from unittest.mock import patch
import os
from datetime import datetime

# from scripts.extraction.markdown_processing.metadata_extractor import MetadataExtractor

class TestMetadataExtractor:
    # TODO: Port relevant tests from the original test_markdown_formatter.py
    # for extract_metadata_from_path.

    @pytest.fixture
    def extractor(self):
        from scripts.extraction.markdown_processing.metadata_extractor import MetadataExtractor
        return MetadataExtractor()

    @pytest.mark.parametrize("pdf_path, expected_unit_id, expected_title_id, expected_module, expected_course, expected_phase", [
        ("CON101/MOD202/UNI303_MyUnit.pdf", "UNI303", "MyUnit", "MOD202", "CON101", "Unknown"),
        ("course_stuff/course-ABC/module-DEF/unit-GHI-My_Unit_Name.pdf", "unit-GHI", "My_Unit_Name", "module-DEF", "course-ABC", "Unknown"),
        ("archive/A Level/Physics/CON-PHY1/MOD-PHY101/UNI-PHY101A_Kinematics.pdf", "UNI-PHY101A", "Kinematics", "MOD-PHY101", "CON-PHY1", "A Level"),
        ("IGCSE_Maths/unit_maths_topic1.pdf", "unit_maths", "topic1", "MOD0000", "COU0000", "IGCSE"),
        ("UNI123.pdf", "UNI123", "UNI123", "MOD0000", "COU0000", "Unknown"), # Title ID defaults to filename w/o ext
        ("unit_456_Advanced_Concepts.pdf", "unit_456", "Advanced_Concepts", "MOD0000", "COU0000", "Unknown"),
        ("no_ids_just_a_filename.pdf", "UNI0000", "no_ids_just_a_filename", "MOD0000", "COU0000", "Unknown"),
        ("/another/path/to/GCSE/Science/course_bio/mod_cell/unit_dna_structure_and_replication.pdf", "unit_dna", "structure_and_replication", "mod_cell", "course_bio", "GCSE"),
    ])
    def test_extract_metadata(self, extractor, pdf_path, expected_unit_id, expected_title_id, expected_module, expected_course, expected_phase):
        # Normalize path for consistent testing across OS
        norm_pdf_path = pdf_path.replace("/", os.sep)
        metadata = extractor.extract_metadata_from_path(norm_pdf_path)
        
        assert metadata['unit_id'] == expected_unit_id
        assert metadata['unit_title_id'] == expected_title_id
        assert metadata['parent_module_id'] == expected_module
        assert metadata['parent_course_id'] == expected_course
        assert metadata['phase'] == expected_phase
        assert 'batch_id' in metadata
        assert 'extraction_date' in metadata
        # Check date format
        datetime.strptime(metadata['extraction_date'], '%Y-%m-%d')

    def test_extract_metadata_default_ids_if_none_found(self, extractor):
        pdf_path = "some_random_file.pdf"
        metadata = extractor.extract_metadata_from_path(pdf_path)
        assert metadata['unit_id'] == 'UNI0000'
        assert metadata['unit_title_id'] == 'some_random_file'
        assert metadata['parent_module_id'] == 'MOD0000'
        assert metadata['parent_course_id'] == 'COU0000'
        assert metadata['phase'] == 'Unknown'

    def test_extract_metadata_filename_priority_for_unit_id(self, extractor):
        pdf_path = "CON1/MOD1/UNI1_from_path_but_UNI2_in_filename.pdf"
        metadata = extractor.extract_metadata_from_path(pdf_path)
        # Filename should take precedence for unit_id if it starts with UNI/unit
        assert metadata['unit_id'] == 'UNI2' 
        assert metadata['unit_title_id'] == 'in_filename'