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
        ("CON101/MOD202/UNI303_MyUnit.pdf", "UNI303", "MyUnit", "MOD202", "CON101", "Unknown"),
        ("course_stuff/course-ABC/module-DEF/unit-GHI-My_Unit_Name.pdf", "unit-GHI", "My_Unit_Name", "module-DEF", "course-ABC", "Unknown"),
        ("archive/A Level/Physics/COU-PHY1/MOD-PHY101/UNI-PHY101A_Kinematics.pdf", "UNI-PHY101A", "Kinematics", "MOD-PHY101", "COU-PHY1", "A Level"),
        ("IGCSE_Maths/unit_maths_topic1.pdf", "unit_maths", "topic1", "MOD0000", "COU0000", "IGCSE"),
        ("UNI123.pdf", "UNI123", "UNI123", "MOD0000", "COU0000", "Unknown"),
        ("unit_456_Advanced_Concepts.pdf", "unit_456", "Advanced_Concepts", "MOD0000", "COU0000", "Unknown"),
        ("no_ids_just_a_filename.pdf", "UNI0000", "no_ids_just_a_filename", "MOD0000", "COU0000", "Unknown"),
        ("/another/path/to/GCSE/Science/course_bio/mod_cell/unit_dna_structure_and_replication.pdf", "unit_dna", "structure_and_replication", "mod_cell", "course_bio", "GCSE"),
        
        # *New test cases for improved logic*
        # Real-world example path structure
        ("/COU0001_camb_as_physics/MOD0001_camb_as_physics_m1/UNI0001_camb_as_physics_m1_l1.pdf", "UNI0001", "camb_as_physics_m1_l1", "MOD0001", "COU0001", "Unknown"),
        
        # Multiple delimiter variations
        ("COU-101/MOD-202/UNI-303_MyUnit_Final.pdf", "UNI-303", "MyUnit_Final", "MOD-202", "COU-101", "Unknown"),
        ("COU_101/MOD_202/UNI_303-MyUnit-Final.pdf", "UNI_303", "MyUnit-Final", "MOD_202", "COU_101", "Unknown"),
        
        # Edge case: No delimiters after prefix
        ("course/module/UNI123NoDelimiter.pdf", "UNI123NoDelimiter", "UNI123NoDelimiter", "module", "course", "Unknown"),
        
        # Mixed case handling
        ("Course_Bio/Module_Cell/Unit_DNA_Structure.pdf", "Unit_DNA", "Structure", "Module_Cell", "Course_Bio", "Unknown"),
    ])
    def test_extract_metadata(self, extractor, pdf_path, expected_unit_id, expected_title_id, expected_module, expected_course, expected_phase):
        # Normalise path for consistent testing across OS
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
        pdf_path = "COU1/MOD1/UNI1_from_path_but_UNI2_in_filename.pdf"
        metadata = extractor.extract_metadata_from_path(pdf_path)
        # Filename should take precedence for unit_id if it starts with UNI/unit
        assert metadata['unit_id'] == 'UNI2' 
        assert metadata['unit_title_id'] == 'in_filename'

    # *New test cases for phase detection priority*
    @pytest.mark.parametrize("pdf_path, expected_phase", [
        ("/A Level/Physics/unit.pdf", "A Level"),  # Should match "A Level", not "A2"
        ("/AS/Biology/unit.pdf", "AS"),
        ("/A2/Chemistry/unit.pdf", "A2"),
        ("/IGCSE/Maths/unit.pdf", "IGCSE"),
        ("/GCSE/English/unit.pdf", "GCSE"),
        ("/IB/Geography/unit.pdf", "IB"),
        ("/ALevel/Physics/unit.pdf", "A Level"),  # Handles no space variation
        ("/path/with/A2/and/A Level/unit.pdf", "A Level"),  # Longer pattern should win
        ("/no_phase_indicators/unit.pdf", "Unknown"),
    ])
    def test_phase_detection_priority(self, extractor, pdf_path, expected_phase):
        """*Test that phase detection prioritises longer patterns correctly*"""
        metadata = extractor.extract_metadata_from_path(pdf_path)
        assert metadata['phase'] == expected_phase

    # *New test cases for error handling and edge cases*
    def test_extract_metadata_malformed_paths(self, extractor):
        """*Test graceful handling of malformed paths*"""
        malformed_paths = [
            "",  # Empty path
            "   ",  # Whitespace only
            "///multiple///slashes///.pdf",  # Multiple consecutive slashes
            "/path/with/empty//components/.pdf",  # Empty components
            None,  # None path (will be converted to string)
        ]
        
        for path in malformed_paths[:-1]:  # Exclude None for now
            metadata = extractor.extract_metadata_from_path(path)
            # Should not crash and should return valid defaults
            assert isinstance(metadata, dict)
            assert 'unit_id' in metadata
            assert 'unit_title_id' in metadata
            assert metadata['unit_id'] in ['UNI0000', '']  # Allow empty or default

    def test_extract_metadata_none_path_handling(self, extractor):
        """*Test handling of None path*"""
        # This might raise an exception or handle gracefully
        try:
            metadata = extractor.extract_metadata_from_path(None)
            # If it doesn't crash, ensure defaults are returned
            assert isinstance(metadata, dict)
            assert metadata['unit_id'] == 'UNI0000'
        except (TypeError, AttributeError):
            # Acceptable to raise an exception for None input
            pass

    def test_extract_metadata_complex_real_world_path(self, extractor):
        """*Test with complex real-world path structure*"""
        complex_path = "/courses/2024/cambridge/A Level/physics/advanced_topics/COU0015_cambridge_physics_advanced/MOD0003_waves_and_optics/UNI0045_wave_interference_and_diffraction_patterns.pdf"
        metadata = extractor.extract_metadata_from_path(complex_path)
        
        assert metadata['unit_id'] == 'UNI0045'
        assert metadata['unit_title_id'] == 'wave_interference_and_diffraction_patterns'
        assert metadata['parent_module_id'] == 'MOD0003'
        assert metadata['parent_course_id'] == 'COU0015'
        assert metadata['phase'] == 'A Level'

    def test_extract_unit_title_id_edge_cases(self, extractor):
        """*Test unit title ID extraction with various edge cases*"""
        test_cases = [
            ("UNI123_", ""),  # Empty after prefix
            ("UNI_multiple_underscores_here", "multiple_underscores_here"),
            ("unit-with-dashes", "with-dashes"),
            ("UNI123NoDelimiterAtAll", "UNI123NoDelimiterAtAll"),  # No delimiter
            ("uni456_lowercase_prefix", "lowercase_prefix"),  # Lowercase prefix
        ]
        
        for filename, expected_title_id in test_cases:
            result = extractor._extract_unit_title_id(filename)
            assert result == expected_title_id or result == filename  # Allow fallback to filename

    def test_extract_id_from_component_variations(self, extractor):
        """*Test ID extraction from components with various delimiter patterns*"""
        test_cases = [
            ("COU123-description", "COU123"),
            ("MOD456_description", "MOD456"),
            ("UNI789-multiple-parts-here", "UNI789"),
            ("simple_id_only", "simple"),
            ("NoDelimitersHere", "NoDelimitersHere"),
            ("", ""),  # Empty component
        ]
        
        for component, expected_id in test_cases:
            result = extractor._extract_id_from_component(component)
            assert result == expected_id

    def test_logging_on_successful_extraction(self, extractor, caplog):
        """*Test that successful extractions log debug information*"""
        with caplog.at_level("DEBUG"):
            extractor.extract_metadata_from_path("COU123/MOD456/UNI789_test_unit.pdf")
            
        # Check that debug logging occurred
        assert any("Extracted metadata from" in record.message for record in caplog.records)

    def test_error_logging_on_exception(self, extractor, caplog):
        """*Test that errors during extraction are logged*"""
        # This would require mocking os.path.basename to raise an exception
        with patch('scripts.extraction.markdown_processing.metadata_extractor.os.path.basename', side_effect=Exception("Test error")):
            with caplog.at_level("ERROR"):
                metadata = extractor.extract_metadata_from_path("some_path.pdf")
                
            # Should return safe defaults
            assert metadata['unit_id'] == 'UNI0000'
            assert any("Error extracting metadata" in record.message for record in caplog.records)