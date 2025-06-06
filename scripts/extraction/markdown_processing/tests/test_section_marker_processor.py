# scripts/extraction/markdown_processing/tests/test_section_marker_processor.py
"""Unit tests for the SectionMarkerProcessor."""
import pytest
import re

# from scripts.extraction.markdown_processing.section_marker_processor import SectionMarkerProcessor

class TestSectionMarkerProcessor:
    # TODO: Add tests for section marker validation, injection, and spacing.

    @pytest.fixture
    def processor(self):
        from scripts.extraction.markdown_processing.section_marker_processor import SectionMarkerProcessor
        return SectionMarkerProcessor() # Uses default required sections

    @pytest.fixture
    def custom_processor(self):
        from scripts.extraction.markdown_processing.section_marker_processor import SectionMarkerProcessor
        return SectionMarkerProcessor(required_sections=['CUSTOM_SECTION_1', 'MAIN-CONTENT-AREA'])


    def test_all_default_markers_present(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->
## Intro

<!-- SECTION: LEARNING-OBJECTIVES -->
## LOs

<!-- SECTION: MAIN-CONTENT-AREA -->
## Main

<!-- SECTION: KEY-TAKEAWAYS -->
## Takeaways
"""
        processed = processor.process_sections(content)
        # Should mostly be unchanged, just normalized spacing
        assert "<!-- SECTION: INTRODUCTION -->" in processed
        assert "<!-- SECTION: LEARNING-OBJECTIVES -->" in processed
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->" in processed
        assert "<!-- SECTION: KEY-TAKEAWAYS -->" in processed
        # Check for standardized newlines (2 before, 2 after, unless start/end of doc)
        assert "\n\n<!-- SECTION: INTRODUCTION -->\n\n" in processed
        assert processed.strip().endswith("## Takeaways") # Content itself is preserved

    def test_missing_one_default_marker_appends_with_heading(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->
## Intro

<!-- SECTION: MAIN-CONTENT-AREA -->
## Main

<!-- SECTION: KEY-TAKEAWAYS -->
## Takeaways
""" # Missing LEARNING-OBJECTIVES
        processed = processor.process_sections(content)
        assert "<!-- SECTION: LEARNING-OBJECTIVES -->" in processed
        assert "## Learning Objectives" in processed.split("<!-- SECTION: LEARNING-OBJECTIVES -->")[1]
        # Ensure it's added at the end
        assert processed.strip().endswith("## Learning Objectives\n\n") or processed.strip().endswith("## Learning Objectives")


    def test_missing_main_content_area_inserts_before_h2(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->
## Intro

<!-- SECTION: LEARNING-OBJECTIVES -->
## LOs

## First Real Heading (H2)
Some text.

<!-- SECTION: KEY-TAKEAWAYS -->
## Takeaways
"""
        processed = processor.process_sections(content)
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## First Real Heading (H2)" in processed

    def test_missing_main_content_area_appends_if_no_h2(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->
# Only H1 Headings
<!-- SECTION: LEARNING-OBJECTIVES -->
<!-- SECTION: KEY-TAKEAWAYS -->
"""
        processed = processor.process_sections(content)
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->" in processed
        # Check it's appended (likely before KEY-TAKEAWAYS if that was also missing and added)
        # The order of appending might depend on the loop order in processor.
        # For simplicity, just check presence and that it's at the end part.
        assert "<!-- SECTION: KEY-TAKEAWAYS -->\n\n\n\n<!-- SECTION: MAIN-CONTENT-AREA -->" in processed or \
               "<!-- SECTION: MAIN-CONTENT-AREA -->\n\n\n\n<!-- SECTION: KEY-TAKEAWAYS -->" in processed


    def test_custom_required_sections(self, custom_processor):
        content = "## Some initial content"
        processed = custom_processor.process_sections(content)
        assert "<!-- SECTION: CUSTOM_SECTION_1 -->" in processed
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## Some initial content" in processed
        # Default sections like INTRODUCTION should not be there
        assert "<!-- SECTION: INTRODUCTION -->" not in processed

    def test_spacing_normalization(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->## Intro
<!--SECTION: LEARNING-OBJECTIVES-->
## LOs<!-- SECTION: MAIN-CONTENT-AREA -->  ## Main
<!-- SECTION: KEY-TAKEAWAYS -->## Takeaways"""
        processed = processor.process_sections(content)
        
        # Check for exactly two newlines before and after each marker (unless at very start/end)
        # This is a bit tricky to assert perfectly with regex for all cases including start/end of string.
        # We can check a specific marker.
        assert "\n\n<!-- SECTION: LEARNING-OBJECTIVES -->\n\n" in processed
        
        # Count occurrences to ensure no duplication
        assert processed.count("<!-- SECTION: INTRODUCTION -->") == 1
        
        # Check no triple newlines
        assert "\n\n\n" not in processed

    def test_empty_content(self, processor):
        content = ""
        processed = processor.process_sections(content)
        assert "<!-- SECTION: INTRODUCTION -->" in processed
        assert "<!-- SECTION: LEARNING-OBJECTIVES -->" in processed
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->" in processed
        assert "<!-- SECTION: KEY-TAKEAWAYS -->" in processed
        # Check that default headings are added for appended sections
        assert "## Introduction" in processed
        assert "## Learning Objectives" in processed
        assert "## Key Takeaways" in processed