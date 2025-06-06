# scripts/extraction/markdown_processing/frontmatter_generator.py

"""Module for generating YAML frontmatter from metadata."""

from datetime import datetime
from typing import Dict, Any

class FrontmatterGenerator:
    """Generates YAML frontmatter from metadata."""

    def generate_frontmatter(self, metadata: Dict[str, Any]) -> str:
        """Generate YAML frontmatter from metadata."""
        unit_id = metadata.get('unit_id', 'UNI0000')
        unit_title_id = metadata.get('unit_title_id', 'unknown_title_id')
        unit_title = metadata.get('unit_title', 'Unknown Title')
        phase = metadata.get('phase', 'Unknown')
        subject = metadata.get('subject', 'Unknown Subject')
        parent_module_id = metadata.get('parent_module_id', 'MOD0000')
        parent_course_id = metadata.get('parent_course_id', 'COU0000')
        batch_id = metadata.get('batch_id', 'BAT0001')
        extraction_date = metadata.get('extraction_date', datetime.now().strftime('%Y-%m-%d'))
        extractor_name = metadata.get('extractor_name', "Automated Extraction")

        # Quoting values that might contain special characters or be multi-word
        return f"""---
unit-id: {unit_id}
unit-title-id: "{unit_title_id}"
unit-title: "{unit_title}"
phase: {phase}
subject: "{subject}"
parent-module-id: {parent_module_id}
parent-course-id: {parent_course_id}
batch-id: {batch_id}
extraction-date: {extraction_date}
extractor-name: "{extractor_name}"
---"""