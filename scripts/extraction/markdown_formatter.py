"""Module for formatting extracted content as markdown."""

import re
import os
import logging
import yaml
from datetime import datetime
from google.genai import types  # Add this import
from ..config.extraction_prompt import get_extraction_prompt
from ..config import settings
from .image_extractor import ImageExtractor, generate_extraction_report
from ..utils.langsmith_utils import traced_operation, extract_file_metadata
from ..utils.image_validation import ImageIssueType

logger = logging.getLogger(__name__)

class MarkdownFormatter:
    """Formats PDF content into structured markdown."""
    
    def __init__(self, pdf_reader):
        """Initialize with a PDFReader instance."""
        self.pdf_reader = pdf_reader
        self.image_extractor = ImageExtractor()
    
    @traced_operation("metadata_extraction")
    def extract_metadata_from_path(self, pdf_path):
        """Extract metadata from PDF path components."""
        # Normalize path separators
        path = pdf_path.replace('\\', '/')
        
        # Extract components from path
        parts = path.split('/')
        filename = os.path.basename(pdf_path)
        filename_without_ext = os.path.splitext(filename)[0]
        
        # Extract course, module, and unit information
        course_id = None
        module_id = None
        unit_id = None
        
        for part in parts:
            if part.startswith('CON'):
                course_id = part.split('-')[0]
            elif part.startswith('MOD'):
                module_id = part.split('-')[0]
            elif part.startswith('UNI'):
                unit_id = part.split('-')[0] if '-' in part else part.split('_')[0]
        
        # If unit_id wasn't found in the path, extract from filename
        if not unit_id and filename_without_ext.startswith('UNI'):
            unit_id = filename_without_ext.split('-')[0] if '-' in filename_without_ext else filename_without_ext.split('_')[0]
        
        # Extract unit_title_id from filename (removing .pdf extension and UNI prefix)
        unit_title_id = filename_without_ext
        if unit_title_id.startswith('UNI'):
            # Remove the UNI#### prefix if present
            unit_title_id = '_'.join(unit_title_id.split('_')[1:])
        
        # Extract phase (AS, IGCSE, etc.)
        phase = None
        for phase_option in ['AS', 'IGCSE', 'A2']:
            if phase_option.lower() in pdf_path.lower():
                phase = phase_option
                break
        
        return {
            'unit_id': unit_id or 'UNI0001',  # Fallback if extraction failed
            'unit_title_id': unit_title_id or os.path.splitext(filename)[0],
            'parent_module_id': module_id or 'MOD0001',
            'parent_course_id': course_id or 'COU0001',
            'phase': phase or 'Unknown',
            'batch_id': 'BAT0001',  # Default batch ID
            'extraction_date': datetime.now().strftime('%Y-%m-%d')
        }
    
    @traced_operation(
        "content_extraction_and_formatting",
        metadata_extractor=lambda self, pdf_info, metadata=None: extract_file_metadata(pdf_info.get('path', ''))
    )
    def extract_and_format(self, pdf_info, metadata=None):
        """Extract content from PDF and format as markdown."""
        # If metadata not provided, try to extract from path
        if not metadata and 'path' in pdf_info:
            metadata = self.extract_metadata_from_path(pdf_info['path'])
        
        # Extract images from the PDF
        image_extraction_results = self._extract_images(pdf_info, metadata)
        
        # Prepare the extraction prompt with metadata
        prompt = get_extraction_prompt(metadata)
        
        # Send to Gemini for extraction
        try:
            if pdf_info['method'] == 'direct':
                # For direct method (files under 20MB)
                response = self.pdf_reader._generate_content_direct(
                    pdf_info['data'],
                    prompt
                )
            else:
                # For File API method (files over 20MB)
                response = self.pdf_reader._generate_content_file_api(
                    pdf_info['path'],
                    prompt
                )
            
            # Get the markdown content from the response
            markdown_content = response.text
            
            # Post-process the markdown content
            processed_content = self.post_process_markdown(
                markdown_content, 
                metadata, 
                image_extraction_results
            )
            
            return {
                'success': True,
                'content': processed_content,
                'metadata': metadata,
                'image_extraction': image_extraction_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'metadata': metadata,
                'image_extraction': image_extraction_results
            }
    
    @traced_operation("image_extraction")
    def _extract_images(self, pdf_info, metadata):
        """Extract images from the PDF file."""
        # Get the PDF path
        pdf_path = pdf_info.get('normalized_path') or pdf_info.get('path')
        
        if not pdf_path:
            logger.warning("No PDF path available for image extraction")
            return {'success': False, 'error': 'No PDF path available'}
        
        # Determine the image assets directory
        img_assets_dir = self._get_image_assets_dir(pdf_path, metadata)
        
        # Extract images
        try:
            results = self.image_extractor.extract_images_from_pdf(pdf_path, img_assets_dir)
            logger.info(f"Image extraction completed: {results['extracted_count']} images extracted")
            return results
        except Exception as e:
            error_msg = f"Failed to extract images: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _get_image_assets_dir(self, pdf_path, metadata):
        """Determine the image assets directory path."""
        # Get the relative path from the PDF source directory
        try:
            rel_path = os.path.relpath(pdf_path, settings.PDF_SOURCE_DIR)
        except ValueError:
            # If the paths are on different drives (Windows), use the basename
            rel_path = os.path.basename(pdf_path)
        
        # Change extension from .pdf to .md
        md_rel_path = rel_path.replace('.pdf', '.md')
        
        # Create the full target markdown path
        target_md_path = os.path.join(settings.MARKDOWN_TARGET_DIR, md_rel_path)
        
        # Get the directory and filename without extension
        md_dir = os.path.dirname(target_md_path)
        md_filename_without_ext = os.path.splitext(os.path.basename(target_md_path))[0]
        
        # Create the image assets directory path
        img_assets_dir = os.path.join(md_dir, f"{md_filename_without_ext}-img-assets")
        
        # Ensure the directory exists
        os.makedirs(img_assets_dir, exist_ok=True)
        
        return img_assets_dir
    
    @traced_operation("markdown_post_processing")
    def post_process_markdown(self, content, metadata, image_extraction_results=None):
        """Apply post-processing to the generated markdown."""
        logger.info("Starting markdown post-processing")
        
        # Check if content contains a markdown code block marker
        markdown_code_pattern = r'```\s*markdown\s*\n'
        has_markdown_marker = bool(re.search(markdown_code_pattern, content))
        if has_markdown_marker:
            logger.info("Found markdown code block marker in content")
        
        # First, check if content has Gemini-generated frontmatter
        # Look for frontmatter either at the start of the document or after a markdown code block marker
        frontmatter_patterns = [
            # Pattern 1: Frontmatter at the start of the document
            r'^---\s+(.*?)\s+---',
            # Pattern 2: Frontmatter after a markdown code block marker
            r'```\s*markdown\s*\n---\s+(.*?)\s+---'
        ]
        
        frontmatter_match = None
        for pattern in frontmatter_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                frontmatter_match = match
                logger.info(f"Found frontmatter using pattern: {pattern}")
                break
        
        if frontmatter_match:
            try:
                # Extract the frontmatter text
                frontmatter_text = frontmatter_match.group(1)
                
                # Parse frontmatter as YAML
                extracted_metadata = yaml.safe_load(frontmatter_text) or {}
                logger.info(f"Extracted metadata from Gemini: {extracted_metadata}")
                
                # Remove the frontmatter and any markdown code markers from content
                if has_markdown_marker:
                    # First remove the entire section including markdown marker and frontmatter
                    content = re.sub(r'```\s*markdown\s*\n---\s+.*?\s+---', '', content, flags=re.DOTALL)
                    # Then also check for and remove any trailing markdown code end markers
                    content = re.sub(r'```\s*\n', '', content)
                else:
                    # Just remove the frontmatter if no markdown marker
                    content = content[frontmatter_match.end():].strip()
                
                logger.info("Removed Gemini frontmatter from content")
                
                # Merge extracted metadata with the provided metadata
                merged_metadata = metadata.copy()
                
                # Only take specific fields from Gemini extraction
                if 'unit-title' in extracted_metadata:
                    merged_metadata['unit_title'] = extracted_metadata['unit-title']
                    logger.info(f"Using Gemini-extracted title: {extracted_metadata['unit-title']}")
                if 'subject' in extracted_metadata:
                    merged_metadata['subject'] = extracted_metadata['subject']
                    logger.info(f"Using Gemini-extracted subject: {extracted_metadata['subject']}")
                
                # Generate new frontmatter with merged data
                new_frontmatter = self.generate_frontmatter(merged_metadata)
                logger.info("Generated new merged frontmatter")
                
                # Reconstruct content with the new frontmatter
                content = f"{new_frontmatter}\n\n{content}"
                logger.info("Reconstructed content with merged frontmatter")
            except Exception as e:
                logger.error(f"Error processing frontmatter: {e}")
                # If there's an error, ensure we have some frontmatter
                if not content.startswith('---'):
                    new_frontmatter = self.generate_frontmatter(metadata)
                    content = f"{new_frontmatter}\n\n{content}"
        else:
            logger.info("No Gemini frontmatter found, generating standard frontmatter")
            # No frontmatter from Gemini, add our standard frontmatter
            new_frontmatter = self.generate_frontmatter(metadata)
            content = f"{new_frontmatter}\n\n{content}"
        
        # Ensure all section markers are present
        required_sections = [
            'INTRODUCTION',
            'LEARNING-OBJECTIVES',
            'MAIN-CONTENT-AREA',
            'KEY-TAKEAWAYS'
        ]
        
        for section in required_sections:
            section_marker = f"<!-- SECTION: {section} -->"
            if section_marker not in content:
                # Add missing section markers where they most likely belong
                if section == 'INTRODUCTION' and '# ' in content:
                    # Add after the first heading
                    content = re.sub(r'(# .+?\n)', r'\1\n' + section_marker + '\n', content, count=1)
                elif section == 'LEARNING-OBJECTIVES' and '## Learning Objectives' in content:
                    # Add before the learning objectives heading
                    content = content.replace('## Learning Objectives', section_marker + '\n## Learning Objectives')
                elif section == 'MAIN-CONTENT-AREA' and '## ' in content:
                    # Add before the first content section (second-level heading)
                    second_heading_match = re.search(r'## (?!Learning Objectives|Introduction).+?\n', content)
                    if second_heading_match:
                        pos = second_heading_match.start()
                        content = content[:pos] + section_marker + '\n\n' + content[pos:]
                elif section == 'KEY-TAKEAWAYS' and '## ' in content:
                    # Add towards the end, before any references
                    if '## References' in content:
                        content = content.replace('## References', section_marker + '\n\n## Key Takeaways\n\n## References')
                    else:
                        content += f"\n\n{section_marker}\n\n## Key Takeaways\n\n"
        
        # Use just the filename without path for the image assets reference
        md_filename_without_ext = metadata.get('unit_id', 'UNI0001') + '_' + metadata.get('unit_title_id', '')
        img_assets_dir = f"./{md_filename_without_ext}-img-assets"
        
        # Process image references based on extraction results
        content = self._process_image_references(content, img_assets_dir, image_extraction_results)
        
        # Ensure proper spacing around section markers
        content = re.sub(r'(\n*)(<!--.*?-->)(\n*)', r'\n\n\2\n\n', content)
        
        # Clean up excess whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        logger.info("Completed markdown post-processing")
        return content
    
    def _process_image_references(self, content, img_assets_dir, image_extraction_results=None):
        """
        Process image references in the markdown content.
        
        Args:
            content: Markdown content with image references
            img_assets_dir: Path to image assets directory
            image_extraction_results: Results from image extraction
            
        Returns:
            Updated markdown content with fixed image references
        """
        # If we have extraction results, update image references to match extracted files
        if image_extraction_results and image_extraction_results.get('images'):
            extracted_images = image_extraction_results.get('images', [])[:]  # Create a copy
            problematic_images = {f"{img.get('page')}-{img.get('index')}": img 
                                 for img in image_extraction_results.get('problematic_images', [])}
            
            # Find image references in the markdown
            img_pattern = r'!\[(.*?)\]\((.*?)(?:\.(?:png|jpg|jpeg|gif))?\)'
            
            def replace_image(match):
                alt_text = match.group(1)
                orig_path = match.group(2)
                
                # Extract page/fig info from original path if possible
                page_fig_match = re.search(r'(?:page|fig)?[-_]?(\d+)', orig_path)
                page_num = int(page_fig_match.group(1)) if page_fig_match else None
                
                # Check if this image is in the problematic list
                if page_num and f"{page_num}-1" in problematic_images:
                    # This is a problematic image - add a warning comment
                    img_issue = problematic_images[f"{page_num}-1"]
                    issue_type = img_issue.get('issue_type', 'unknown')
                    warning = f"\n<!-- WARNING: Image extraction issue: {issue_type} -->\n"
                    
                    # Use a placeholder or fallback image
                    if issue_type == ImageIssueType.BLANK.value:
                        return f"{warning}![{alt_text} (Extraction Issue: Blank Image)]({img_assets_dir}/placeholder-blank.png)"
                    elif issue_type == ImageIssueType.CORRUPT.value:
                        return f"{warning}![{alt_text} (Extraction Issue: Corrupt Image)]({img_assets_dir}/placeholder-corrupt.png)"
                    else:
                        return f"{warning}![{alt_text} (Extraction Issue: {issue_type})]({img_assets_dir}/placeholder-error.png)"
                
                # Use the next available successfully extracted image
                if extracted_images:
                    img_info = extracted_images.pop(0)
                    return f"![{alt_text}]({img_assets_dir}/{img_info['filename']})"
                else:
                    # Fallback to generic naming
                    return f"![{alt_text}]({img_assets_dir}/fig1-image.png)"
            
            content = re.sub(img_pattern, replace_image, content)
            
            # Add warnings if we couldn't match all extracted images
            if extracted_images:
                unused_count = len(extracted_images)
                logger.warning(f"Found {unused_count} extracted images that weren't referenced in the markdown")
                warning = (f"\n\n<!-- WARNING: There were {unused_count} extracted images "
                          f"that weren't referenced in the markdown content -->\n")
                content += warning
                
        else:
            # Fallback: Fix image references with generic naming
            logger.warning("No extraction results available - using generic image references")
            content = re.sub(
                r'!\[(.*?)\]\((.*?)(?:\.(?:png|jpg|jpeg|gif))?\)',
                r'![\1](' + img_assets_dir + r'/fig1-image.png)',
                content
            )
            
            # Add a warning about missing images
            warning = "\n\n<!-- WARNING: Image extraction failed or no results available - using generic references -->\n"
            content += warning
        
        return content
    
    def generate_frontmatter(self, metadata):
        """Generate YAML frontmatter from metadata."""
        return f"""---
unit-id: {metadata.get('unit_id', 'UNI0001')}
unit-title-id: {metadata.get('unit_title_id', 'unknown')}
unit-title: {metadata.get('unit_title', 'Unknown Title')}
phase: {metadata.get('phase', 'Unknown')}
subject: {metadata.get('subject', 'Unknown')}
parent-module-id: {metadata.get('parent_module_id', 'MOD0001')}
parent-course-id: {metadata.get('parent_course_id', 'COU0001')}
batch-id: {metadata.get('batch_id', 'BAT0001')}
extraction-date: {metadata.get('extraction_date', datetime.now().strftime('%Y-%m-%d'))}
extractor-name: "Automated Extraction"
---"""