# scripts/extraction/markdown_processing/tests/test_content_processor.py
"""Unit tests for the ContentProcessor."""
import pytest
from unittest.mock import MagicMock

# from scripts.extraction.markdown_processing.content_processor import ContentProcessor
# from scripts.extraction.markdown_processing.frontmatter_generator import FrontmatterGenerator

class TestContentProcessor:

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

    @pytest.mark.parametrize("markdown_keyword", ["markdown", "md", "Markdown", "MARKDOWN"])
    def test_process_llm_output_with_frontmatter_and_markdown_block_variants(self, content_processor, mock_frontmatter_generator, markdown_keyword):
        raw_llm_content = f"""```{markdown_keyword}
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
        args_passed_to_fg = mock_frontmatter_generator.generate_frontmatter.call_args[0][0]
        assert args_passed_to_fg['unit_title'] == "LLM Title"
        assert args_passed_to_fg['subject'] == "LLM Subject"
        assert args_passed_to_fg['unit_id'] == "U1" 
        assert args_passed_to_fg['phase'] == "AS"

        assert "mocked_unit_title: \"LLM Title\"" in processed_content
        assert "mocked_subject: \"LLM Subject\"" in processed_content
        assert "This is the main body content." in processed_content
        assert "## A heading" in processed_content
        assert f"```{markdown_keyword}" not in processed_content.split("---", 2)[-1] 
        assert not processed_content.split("---", 2)[-1].strip().startswith("---") 

        assert merged_metadata['unit_title'] == "LLM Title"
        assert merged_metadata['subject'] == "LLM Subject"
        assert merged_metadata['unit_id'] == "U1"
        # Reset mock for next parameterized call
        mock_frontmatter_generator.generate_frontmatter.reset_mock()


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

    @pytest.mark.parametrize("markdown_keyword", ["markdown", "md", "Markdown", "MARKDOWN"])
    def test_process_llm_output_only_markdown_block_no_frontmatter_variants(self, content_processor, mock_frontmatter_generator, markdown_keyword):
        raw_llm_content = f"""```{markdown_keyword}
Just body content inside a markdown block.
No frontmatter here.
```"""
        base_metadata = {'unit_title': 'Base Title', 'subject': 'Base Subject'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)

        assert "mocked_unit_title: \"Base Title\"" in processed_content 
        assert "mocked_subject: \"Base Subject\"" in processed_content 
        assert "Just body content inside a markdown block." in processed_content
        assert "No frontmatter here." in processed_content
        assert f"```{markdown_keyword}" not in processed_content.split("---", 2)[-1]

        assert merged_metadata['unit_title'] == "Base Title" 
        mock_frontmatter_generator.generate_frontmatter.reset_mock()


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
        
        assert "mocked_unit_title: \"Malformed Title\"" in processed_content 
        assert "mocked_subject: \"Base Subject\"" in processed_content        
        assert "Body content." in processed_content
        
        assert merged_metadata['unit_title'] == "Malformed Title" 
        assert merged_metadata['subject'] == "Base Subject" 
        

    def test_process_llm_output_empty_body_after_frontmatter(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """---
unit-title: Title Only
---
""" 
        base_metadata = {}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)
        
        assert "mocked_unit_title: \"Title Only\"" in processed_content
        # Check that the content ends with the frontmatter closing "---" 
        # and not double newlines if body is empty
        # The ContentProcessor adds "\n\n" separator if body_content is not empty.
        # If body_content is empty, final_frontmatter_str is returned directly.
        assert processed_content.strip() == "---\nmocked_unit_title: \"Title Only\"\nmocked_subject: \"DefaultSub\"\n---"
        assert len(processed_content.split("---",2)[-1].strip()) == 0

    def test_frontmatter_eof_case(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """---
unit-title: EOF Title
subject: EOF Subject
---""" # No newline after final ---
        base_metadata = {'unit_id': 'U-EOF'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)

        assert "mocked_unit_title: \"EOF Title\"" in processed_content
        assert "mocked_subject: \"EOF Subject\"" in processed_content
        assert merged_metadata['unit_title'] == "EOF Title"
        assert merged_metadata['subject'] == "EOF Subject"
        # Body should be empty
        body_part = processed_content.split("---", 2)[-1].strip()
        assert body_part == ""

    def test_frontmatter_in_markdown_block_eof_case(self, content_processor, mock_frontmatter_generator):
        raw_llm_content = """```markdown
---
unit-title: Block EOF Title
subject: Block EOF Subject
---
```""" # No body content after frontmatter inside block
        base_metadata = {'unit_id': 'U-BlockEOF'}
        processed_content, merged_metadata = content_processor.process_llm_output(raw_llm_content, base_metadata)

        assert "mocked_unit_title: \"Block EOF Title\"" in processed_content
        assert "mocked_subject: \"Block EOF Subject\"" in processed_content
        assert merged_metadata['unit_title'] == "Block EOF Title"
        assert merged_metadata['subject'] == "Block EOF Subject"
        body_part = processed_content.split("---", 2)[-1].strip()
        assert body_part == ""
        assert "```" not in body_part