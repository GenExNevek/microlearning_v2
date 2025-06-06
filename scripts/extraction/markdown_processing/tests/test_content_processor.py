# scripts/extraction/markdown_processing/tests/test_content_processor.py
"""Unit tests for the ContentProcessor."""
import pytest
from unittest.mock import MagicMock

# from scripts.extraction.markdown_processing.content_processor import ContentProcessor
# from scripts.extraction.markdown_processing.frontmatter_generator import FrontmatterGenerator

class TestContentProcessor:
    # TODO: Add tests for LLM output parsing, frontmatter extraction,
    # body cleaning, and metadata merging.

    @pytest.fixture
    def mock_frontmatter_generator(self):
        fg = MagicMock()
        # Make generate_frontmatter return a simple string based on input for easy verification
        fg.generate_frontmatter.side_effect = lambda meta: f"---\nmocked_unit_title: \"{meta.get('unit_title', 'Default')}\"\nmocked_subject: \"{meta.get('subject', 'DefaultSub')}\"\n---"
        return fg

    @pytest.fixture
    def content_processor(self, mock_frontmatter_generator):
        from scripts.extraction.markdown_processing.content_processor import ContentProcessor
        return ContentProcessor(mock_frontmatter_generator)

    def test_process_llm_output_with_frontmatter_and_markdown_block(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """```markdown
---
unit-title: LLM Title
subject: LLM Subject
---

This is the main body content.
## A heading
More text.
```"""
        base_metadata = {'unit_id': 'U1', 'unit_title_id': 'base_title_id', 'phase': 'AS'}
        
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)
        
        mock_frontmatter_generator.generate_frontmatter.assert_called_once()
        # Check that the merged metadata was passed to the generator
        args_passed_to_fg = mock_frontmatter_generator.generate_frontmatter.call_args[0][0]
        assert args_passed_to_fg['unit_title'] == "LLM Title"
        assert args_passed_to_fg['subject'] == "LLM Subject"
        assert args_passed_to_fg['unit_id'] == "U1" # from base
        assert args_passed_to_fg['phase'] == "AS" # from base

        assert "mocked_unit_title: \"LLM Title\"" in processed_content
        assert "mocked_subject: \"LLM Subject\"" in processed_content
        assert "This is the main body content." in processed_content
        assert "## A heading" in processed_content
        assert "```markdown" not in processed_content.split("---", 2)[-1] # Check body part
        assert not processed_content.split("---", 2)[-1].strip().startswith("---") # Ensure LLM frontmatter removed from body

        assert merged_metadata['unit_title'] == "LLM Title"
        assert merged_metadata['subject'] == "LLM Subject"
        assert merged_metadata['unit_id'] == "U1"

    def test_process_llm_output_with_only_frontmatter_no_block(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """---
unit-title: Another LLM Title
---

Body directly after frontmatter.
"""
        base_metadata = {'unit_id': 'U2'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)

        assert "mocked_unit_title: \"Another LLM Title\"" in processed_content
        assert "Body directly after frontmatter." in processed_content
        assert merged_metadata['unit_title'] == "Another LLM Title"
        assert merged_metadata['unit_id'] == "U2"

    def test_process_llm_output_only_markdown_block_no_frontmatter(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """```markdown
Just body content inside a markdown block.
No frontmatter here.
```"""
        base_metadata = {'unit_title': 'Base Title', 'subject': 'Base Subject'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)

        assert "mocked_unit_title: \"Base Title\"" in processed_content # From base metadata
        assert "mocked_subject: \"Base Subject\"" in processed_content # From base metadata
        assert "Just body content inside a markdown block." in processed_content
        assert "No frontmatter here." in processed_content
        assert "```markdown" not in processed_content.split("---", 2)[-1]

        assert merged_metadata['unit_title'] == "Base Title" # Unchanged

    def test_process_llm_output_plain_content_no_frontmatter_no_block(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = "This is plain content.\nNo special formatting."
        base_metadata = {'unit_title': 'Plain Title'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)

        assert "mocked_unit_title: \"Plain Title\"" in processed_content
        assert "This is plain content." in processed_content
        assert merged_metadata['unit_title'] == "Plain Title"

    def test_process_llm_output_malformed_llm_frontmatter(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """---
unit-title: Malformed Title
subject: [Not a string, but a list]
---
Body content.
"""
        base_metadata = {'unit_title': 'Base Title', 'subject': 'Base Subject'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)
        
        # Should use base metadata for frontmatter generation due to parsing error
        assert "mocked_unit_title: \"Base Title\"" in processed_content
        assert "mocked_subject: \"Base Subject\"" in processed_content
        assert "Body content." in processed_content
        
        # Merged metadata should reflect the attempt, but FrontmatterGenerator uses defaults/base
        assert merged_metadata['unit_title'] == "Malformed Title" # This gets merged
        assert merged_metadata['subject'] == ['Not a string, but a list'] # This also gets merged
        # The FrontmatterGenerator mock would then use these, or its defaults if they are not suitable.
        # Our mock uses them directly. If the real FG had validation, it might differ.

    def test_process_llm_output_empty_body_after_frontmatter(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """---
unit-title: Title Only
---
""" # Empty body
        base_metadata = {}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)
        
        assert "mocked_unit_title: \"Title Only\"" in processed_content
        # Check that the content ends with the frontmatter closing "---" and not double newlines if body is empty
        assert processed_content.strip().endswith("---")
        assert len(processed_content.split("---",2)[-1].strip()) == 0