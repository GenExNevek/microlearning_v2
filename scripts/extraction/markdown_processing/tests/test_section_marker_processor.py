
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
        # Should mostly be unchanged, just normalized spacing and trailing newline
        assert "<!-- SECTION: INTRODUCTION -->" in processed
        assert "<!-- SECTION: LEARNING-OBJECTIVES -->" in processed
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->" in processed
        assert "<!-- SECTION: KEY-TAKEAWAYS -->" in processed
        
        # Check for standardized newlines (2 before, 2 after, unless start/end of doc)
        # The processor adds a single trailing newline after strip() if content exists.
        expected_intro = "<!-- SECTION: INTRODUCTION -->\n\n## Intro" # Intro marker at start
        expected_lo = "\n\n<!-- SECTION: LEARNING-OBJECTIVES -->\n\n## LOs"
        expected_main = "\n\n<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## Main"
        expected_kt = "\n\n<!-- SECTION: KEY-TAKEAWAYS -->\n\n## Takeaways\n" # KT marker at end (before final strip/add \n)

        assert expected_intro in processed
        assert expected_lo in processed
        assert expected_main in processed
        assert expected_kt in processed 
        assert processed.endswith("\n")


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
        # The appended section will have its default heading
        # And it will be normalized with newlines around it.
        # The final content will also have a trailing newline.
        assert "\n\n<!-- SECTION: LEARNING-OBJECTIVES -->\n\n## Learning Objectives\n\n" in processed
        assert processed.strip().endswith("## Learning Objectives")


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
        assert "\n\n<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## First Real Heading (H2)" in processed

    def test_missing_main_content_area_appends_if_no_h2(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->
# Only H1 Headings
<!-- SECTION: LEARNING-OBJECTIVES -->
<!-- SECTION: KEY-TAKEAWAYS -->
""" # Missing MAIN-CONTENT-AREA
        processed = processor.process_sections(content)
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->" in processed
        # It will be appended. The order of appended missing sections depends on loop order.
        # MAIN-CONTENT-AREA is processed before KEY-TAKEAWAYS if both are missing and appended.
        # The key is that it's present and correctly formatted.
        assert "\n\n<!-- SECTION: MAIN-CONTENT-AREA -->\n\n" in processed
        assert processed.strip().endswith("<!-- SECTION: MAIN-CONTENT-AREA -->")


    def test_custom_required_sections(self, custom_processor):
        content = "## Some initial content" # MAIN-CONTENT-AREA will be inserted before this
        processed = custom_processor.process_sections(content)
        # CUSTOM_SECTION_1 will be appended (no default heading)
        assert "\n\n<!-- SECTION: CUSTOM_SECTION_1 -->\n\n" in processed.strip()
        # MAIN-CONTENT-AREA inserted before H2
        assert "\n\n<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## Some initial content" in processed
        assert "<!-- SECTION: INTRODUCTION -->" not in processed

    def test_spacing_normalization(self, processor):
        content = """<!-- SECTION: INTRODUCTION -->## Intro
<!--SECTION: LEARNING-OBJECTIVES-->
## LOs<!-- SECTION: MAIN-CONTENT-AREA -->  ## Main
<!-- SECTION: KEY-TAKEAWAYS -->## Takeaways"""
        processed = processor.process_sections(content)
        
        assert "<!-- SECTION: INTRODUCTION -->\n\n## Intro" in processed # Start of content
        assert "\n\n<!-- SECTION: LEARNING-OBJECTIVES -->\n\n## LOs" in processed
        assert "\n\n<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## Main" in processed
        assert "\n\n<!-- SECTION: KEY-TAKEAWAYS -->\n\n## Takeaways\n" in processed # End of content
        
        assert processed.count("<!-- SECTION: INTRODUCTION -->") == 1
        
        # Check no more than triple newlines (processor cleans \n{4,} to \n\n\n)
        # The replace_marker_spacing aims for \n\n before and after, so \n\n\n shouldn't occur from it.
        # The final strip and add \n ensures clean end.
        assert "\n\n\n\n" not in processed 
        assert not processed.startswith("\n\n") # Should be stripped
        assert processed.endswith("\n") and not processed.endswith("\n\n")


    def test_empty_content(self, processor):
        content = ""
        processed = processor.process_sections(content)
        # All required sections are added with their default headings if applicable.
        # The order of addition matters for how they appear.
        # Example: INTRODUCTION is first in DEFAULT_REQUIRED_SECTIONS
        # The final output is stripped and a single newline is added.
        
        assert "<!-- SECTION: INTRODUCTION -->\n\n## Introduction" in processed
        assert "<!-- SECTION: LEARNING-OBJECTIVES -->\n\n## Learning Objectives" in processed
        assert "<!-- SECTION: MAIN-CONTENT-AREA -->" in processed # No default heading
        assert "<!-- SECTION: KEY-TAKEAWAYS -->\n\n## Key Takeaways" in processed
        
        # Check overall structure for empty input
        expected_structure_parts = [
            "<!-- SECTION: INTRODUCTION -->\n\n## Introduction",
            "<!-- SECTION: LEARNING-OBJECTIVES -->\n\n## Learning Objectives",
            "<!-- SECTION: MAIN-CONTENT-AREA -->", # No heading, just marker
            "<!-- SECTION: KEY-TAKEAWAYS -->\n\n## Key Takeaways"
        ]
        
        current_pos = 0
        for part in expected_structure_parts:
            assert part in processed
            # Check order if possible (simplified check)
            assert processed.find(part, current_pos) != -1
            current_pos = processed.find(part, current_pos) + len(part)
            
        assert processed.endswith("\n")

    def test_marker_at_very_start_and_end(self, processor):
        content = "<!-- SECTION: INTRODUCTION -->"
        processed = processor.process_sections(content)
        # INTRODUCTION is present. Others will be added.
        # The existing INTRODUCTION should have no leading/trailing newlines from the spacing function
        # before other markers are appended.
        # After all processing, it should be "<!-- SECTION: INTRODUCTION -->\n\n...other markers...\n"
        assert processed.startswith("<!-- SECTION: INTRODUCTION -->\n\n")
        assert "<!-- SECTION: LEARNING-OBJECTIVES -->" in processed
        assert processed.endswith("\n")

    def test_only_main_content_area_present(self, processor):
        content = "<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## Some Content"
        processed = processor.process_sections(content)
        # INTRODUCTION, LO, KT should be added.
        # MAIN-CONTENT-AREA should be correctly spaced.
        assert processed.startswith("<!-- SECTION: INTRODUCTION -->\n\n## Introduction\n\n")
        assert "\n\n<!-- SECTION: LEARNING-OBJECTIVES -->\n\n## Learning Objectives\n\n" in processed
        assert "\n\n<!-- SECTION: MAIN-CONTENT-AREA -->\n\n## Some Content\n\n" in processed
        assert processed.strip().endswith("## Key Takeaways") # KT is last default, appended.