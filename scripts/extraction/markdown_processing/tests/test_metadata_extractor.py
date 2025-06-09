# scripts/extraction/markdown_processing/tests/test_metadata_extractor.py
"""Unit tests for the MetadataExtractor."""
import pytest
from unittest.mock import patch
import os
from datetime import datetime

class TestMetadataExtractor:

    @pytest.fixture
    def extractor(self):
        from scripts.extraction.markdown_processing.metadata_extractor import MetadataExtractor
        return MetadataExtractor()

    @pytest.mark.parametrize("pdf_path, expected_unit_id, expected_title_id, expected_module, expected_course, expected_phase", [
        # Original test cases (updated where needed)
        ("COU101/MOD202/UNI303_MyUnit.pdf", "UNI303", "MyUnit", "MOD202", "COU101", "Unknown"),
        ("course_stuff/course-ABC/module-DEF/unit-GHI-My_Unit_Name.pdf", "unit-GHI", "My_Unit_Name", "module-DEF", "course-ABC", "Unknown"),
        ("archive/A Level/Physics/COU-PHY1/MOD-PHY101/UNI-PHY101A_Kinematics.pdf", "UNI-PHY101A", "Kinematics", "MOD-PHY101", "COU-PHY1", "A Level"),
        ("IGCSE_Maths/unit_maths_topic1.pdf", "unit_maths", "topic1", "MOD0000", "COU0000", "IGCSE"), # No explicit MOD/COU in path
        ("UNI123.pdf", "UNI123", "UNI123", "MOD0000", "COU0000", "Unknown"),
        ("unit_456_Advanced_Concepts.pdf", "unit_456", "Advanced_Concepts", "MOD0000", "COU0000", "Unknown"),
        ("no_ids_just_a_filename.pdf", "UNI0000", "no_ids_just_a_filename", "MOD0000", "COU0000", "Unknown"),
        ("/another/path/to/GCSE/Science/course_bio/mod_cell/unit_dna_structure_and_replication.pdf", "unit_dna", "structure_and_replication", "mod_cell", "course_bio", "GCSE"),
        
        # New test cases for improved logic
        ("/COU0001_camb_as_physics/MOD0001_camb_as_physics_m1/UNI0001_camb_as_physics_m1_l1.pdf", "UNI0001", "camb_as_physics_m1_l1", "MOD0001", "COU0001", "AS Level"), # AS Level due to "as"
        
        ("COU-101/MOD-202/UNI-303_MyUnit_Final.pdf", "UNI-303", "MyUnit_Final", "MOD-202", "COU-101", "Unknown"),
        ("COU_101/MOD_202/UNI_303-MyUnit-Final.pdf", "UNI_303", "MyUnit-Final", "MOD_202", "COU_101", "Unknown"),
        
        ("course/module/UNI123NoDelimiterAfterPrefix.pdf", "UNI123NoDelimiterAfterPrefix", "UNI123NoDelimiterAfterPrefix", "module", "course", "Unknown"), # Title ID is tricky here
        ("course/module/UNI-NoDigits_MyTitle.pdf", "UNI-NoDigits", "MyTitle", "module", "course", "Unknown"),


        ("Course_Bio/Module_Cell/Unit_DNA_Structure.pdf", "Unit_DNA", "Structure", "Module_Cell", "Course_Bio", "Unknown"),
        ("path/A2 Level/file.pdf", "UNI0000", "file", "MOD0000", "COU0000", "A2 Level"),
        ("path/AS Level/file.pdf", "UNI0000", "file", "MOD0000", "COU0000", "AS Level"),
    ])
    def test_extract_metadata(self, extractor, pdf_path, expected_unit_id, expected_title_id, expected_module, expected_course, expected_phase):
        norm_pdf_path = pdf_path.replace("/", os.sep)
        metadata = extractor.extract_metadata_from_path(norm_pdf_path)
        
        assert metadata['unit_id'] == expected_unit_id
        assert metadata['unit_title_id'] == expected_title_id
        assert metadata['parent_module_id'] == expected_module
        assert metadata['parent_course_id'] == expected_course
        assert metadata['phase'] == expected_phase
        assert 'batch_id' in metadata
        assert 'extraction_date' in metadata
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
        pdf_path = "COU1/MOD1/UNI1_from_path_but_UNI2_in_filename.pdf"
        metadata = extractor.extract_metadata_from_path(pdf_path)
        assert metadata['unit_id'] == 'UNI2' 
        assert metadata['unit_title_id'] == 'in_filename'

    @pytest.mark.parametrize("pdf_path, expected_phase", [
        ("/stuff/A Level/Physics/unit.pdf", "A Level"),
        ("/stuff/AS/Biology/unit.pdf", "AS"), # Will match AS
        ("/stuff/A2/Chemistry/unit.pdf", "A2"), # Will match A2
        ("/stuff/AS Level/Biology/unit.pdf", "AS Level"), # More specific
        ("/stuff/A2 Level/Chemistry/unit.pdf", "A2 Level"), # More specific
        ("/stuff/IGCSE/Maths/unit.pdf", "IGCSE"),
        ("/stuff/GCSE/English/unit.pdf", "GCSE"),
        ("/stuff/IB/Geography/unit.pdf", "IB"),
        ("/stuff/ALevel/Physics/unit.pdf", "A Level"), 
        ("/path/with/A2/and/A Level/unit.pdf", "A Level"), 
        ("/no_phase_indicators/unit.pdf", "Unknown"),
        ("/cambridge_as_physics/file.pdf", "AS Level"), # "as" should be caught
    ])
    def test_phase_detection_priority(self, extractor, pdf_path, expected_phase):
        metadata = extractor.extract_metadata_from_path(pdf_path)
        assert metadata['phase'] == expected_phase

    def test_extract_metadata_malformed_paths(self, extractor):
        malformed_paths = [
            "", 
            "   ", 
            "///multiple///slashes///file.pdf", 
            "/path/with/empty//components/file.pdf", 
        ]
        
        for path in malformed_paths:
            metadata = extractor.extract_metadata_from_path(path)
            assert isinstance(metadata, dict)
            assert 'unit_id' in metadata
            assert 'unit_title_id' in metadata
            if not path.strip() or path.endswith("///"): # if effectively no filename
                 assert metadata['unit_title_id'] == 'unknown_unit'
            elif "file.pdf" in path :
                 assert metadata['unit_title_id'] == 'file'


    def test_extract_metadata_none_path_handling(self, extractor):
        metadata = extractor.extract_metadata_from_path(None)
        assert isinstance(metadata, dict)
        assert metadata['unit_id'] == 'UNI0000'
        assert metadata['unit_title_id'] == 'unknown_unit'


    def test_extract_metadata_complex_real_world_path(self, extractor):
        complex_path = "/courses/2024/cambridge/A Level/physics/advanced_topics/COU0015_cambridge_physics_advanced/MOD0003_waves_and_optics/UNI0045_wave_interference_and_diffraction_patterns.pdf"
        metadata = extractor.extract_metadata_from_path(complex_path)
        
        assert metadata['unit_id'] == 'UNI0045'
        assert metadata['unit_title_id'] == 'wave_interference_and_diffraction_patterns'
        assert metadata['parent_module_id'] == 'MOD0003'
        assert metadata['parent_course_id'] == 'COU0015'
        assert metadata['phase'] == 'A Level'

    @pytest.mark.parametrize("filename, expected_title_id", [
        ("UNI123_", ""), 
        ("UNI_multiple_underscores_here", "multiple_underscores_here"),
        ("unit-with-dashes", "with-dashes"),
        ("UNI123NoDelimiterAfterPrefix", "UNI123NoDelimiterAfterPrefix"), 
        ("uni456_lowercase_prefix", "lowercase_prefix"), 
        ("UNI-MyTitle", "MyTitle"),
        ("unit_AnotherTitle", "AnotherTitle"),
        ("JustATitle", "JustATitle"),
        ("", "unknown_title_id"), # Empty filename
    ])
    def test_extract_unit_title_id_edge_cases(self, extractor, filename, expected_title_id):
        result = extractor._extract_unit_title_id(filename)
        assert result == expected_title_id

    @pytest.mark.parametrize("component, expected_id", [
        ("COU123-description", "COU123"),
        ("MOD456_description", "MOD456"),
        ("UNI789-multiple-parts-here", "UNI789"),
        ("simple_id_only", ""), # Not starting with known prefix
        ("NoDelimitersHere", ""), # Not starting with known prefix
        ("UNIT100", "UNIT100"),
        ("module-200", "module-200"),
        ("cou_300_extra", "cou_300"),
        ("", ""),
    ])
    def test_extract_id_from_component_variations(self, extractor, component, expected_id):
        result = extractor._extract_id_from_component(component)
        assert result == expected_id

    def test_logging_on_successful_extraction(self, extractor, caplog):
        with caplog.at_level("DEBUG"):
            extractor.extract_metadata_from_path("COU123/MOD456/UNI789_test_unit.pdf")
            
        assert any("Extracted metadata from" in record.message for record in caplog.records)

    def test_error_logging_on_exception(self, extractor, caplog):
        # Mock os.path.basename to raise an exception to test the general except block
        with patch('scripts.extraction.markdown_processing.metadata_extractor.os.path.basename', side_effect=Exception("Test error")):
            with caplog.at_level("ERROR"):
                metadata = extractor.extract_metadata_from_path("some_path.pdf") # Path itself doesn't matter due to mock
                
            assert metadata['unit_id'] == 'UNI0000' # Should return safe defaults
            # The path passed to basename would be "some_path.pdf"
            assert metadata['unit_title_id'] == 'unknown_unit' # Default from exception
            assert any("Error extracting metadata" in record.message and "Test error" in record.message for record in caplog.records)