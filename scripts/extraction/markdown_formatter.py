# scripts/extraction/markdown_formatter.py

"""Module for formatting extracted content as markdown."""

import re
import os
import logging
import yaml
from datetime import datetime
from typing import Dict, Optional, Any # Added Dict, Optional, Any
from ..config.extraction_prompt import get_extraction_prompt
from ..config import settings
from .image_extractor import ImageExtractor
from ..utils.image_validation import ImageIssueType

logger = logging.getLogger(__name__)

class MarkdownFormatter:
    """Formats PDF content into structured markdown."""
    
    def __init__(self, pdf_reader):
        """Initialize with a PDFReader instance."""
        self.pdf_reader = pdf_reader
        self.image_extractor = ImageExtractor() 
    
    def extract_metadata_from_path(self, pdf_path: str) -> Dict[str, Any]: # Added type hint
        """Extract metadata from PDF path components."""
        path = pdf_path.replace('\\', '/')
        parts = path.split('/')
        filename = os.path.basename(pdf_path)
        filename_without_ext = os.path.splitext(filename)[0]
        
        course_id = None
        module_id = None
        unit_id = None
        
        for part in reversed(parts):
            if not unit_id and (part.startswith('UNI') or part.startswith('unit')):
                unit_id = part.split('-')[0] if '-' in part else part.split('_')[0]
            elif not module_id and (part.startswith('MOD') or part.startswith('module')):
                module_id = part.split('-')[0] if '-' in part else part.split('_')[0]
            elif not course_id and (part.startswith('CON') or part.startswith('course')):
                course_id = part.split('-')[0] if '-' in part else part.split('_')[0]

        if not unit_id and (filename_without_ext.startswith('UNI') or filename_without_ext.startswith('unit')):
            unit_id = filename_without_ext.split('-')[0] if '-' in filename_without_ext else filename_without_ext.split('_')[0]
        
        unit_title_id = filename_without_ext
        if unit_title_id.startswith('UNI') or unit_title_id.startswith('unit_'):
            match = re.match(r'(?:UNI|unit_)\d*[-_]*(.*)', unit_title_id, re.IGNORECASE)
            if match and match.group(1):
                unit_title_id = match.group(1)
            else:
                unit_title_id = '_'.join(unit_title_id.split('_')[1:]) if '_' in unit_title_id else unit_title_id
        
        phase = None
        path_lower = pdf_path.lower()
        for phase_option in ['AS', 'A2', 'IGCSE', 'GCSE', 'IB', 'A Level']:
            if phase_option.lower().replace(" ", "") in path_lower.replace(" ", ""):
                phase = phase_option
                break
        
        return {
            'unit_id': unit_id or 'UNI0000',
            'unit_title_id': unit_title_id or os.path.splitext(filename)[0],
            'parent_module_id': module_id or 'MOD0000',
            'parent_course_id': course_id or 'COU0000',
            'phase': phase or 'Unknown',
            'batch_id': 'BAT0001',
            'extraction_date': datetime.now().strftime('%Y-%m-%d')
        }
    
    def extract_and_format(self, pdf_info: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: # Added type hints
        """Extract content from PDF and format as markdown."""
        original_pdf_path = pdf_info.get('path') # Store original PDF path for later use if needed

        if not metadata and original_pdf_path:
            metadata = self.extract_metadata_from_path(original_pdf_path)
        elif not metadata: # Fallback if no path and no metadata
             metadata = self.extract_metadata_from_path("unknown_path.pdf") # Create some default metadata
             logger.warning("No PDF path or metadata provided to extract_and_format. Using default metadata.")
        
        image_extraction_results = self._extract_images(pdf_info, metadata)
        
        prompt = get_extraction_prompt(metadata)
        
        try:
            if 'method' not in pdf_info or (pdf_info['method'] == 'direct' and 'data' not in pdf_info) or \
               (pdf_info['method'] == 'file_api' and 'path' not in pdf_info):
                 logger.error(f"pdf_info is missing required keys for method '{pdf_info.get('method')}'. PDF Info: {pdf_info}")
                 return {
                    'success': False,
                    'error': "Invalid pdf_info structure for Gemini call.",
                    'metadata': metadata,
                    'image_extraction': image_extraction_results
                 }

            if pdf_info['method'] == 'direct':
                response = self.pdf_reader._generate_content_direct(
                    pdf_info['data'],
                    prompt
                )
            else:
                response = self.pdf_reader._generate_content_file_api(
                    pdf_info['path'],
                    prompt
                )
            
            markdown_content = response.text
            
            processed_content = self.post_process_markdown(
                markdown_content, 
                metadata, 
                image_extraction_results,
                original_pdf_path # Pass the original PDF path here
            )
            
            return {
                'success': True,
                'content': processed_content,
                'metadata': metadata,
                'image_extraction': image_extraction_results
            }
            
        except Exception as e:
            logger.error(f"Error during Gemini content extraction or markdown processing: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'metadata': metadata,
                'image_extraction': image_extraction_results
            }
    
    def _extract_images(self, pdf_info: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]: # Added type hints
        """
        Extract images from the PDF file using the refactored ImageExtractor.
        Returns the full report dictionary from ImageExtractor.
        """
        pdf_path = pdf_info.get('normalized_path') or pdf_info.get('path')
        
        if not pdf_path:
            logger.warning("No PDF path available for image extraction")
            return {
                'success': False, 
                'errors': ['No PDF path available for image extraction'],
                'extracted_count': 0,
                'failed_count': 0,
                'problematic_images': [],
                'metrics': {},
                'output_dir': None, # Add output_dir key for consistency
                'report_path': None # Add report_path key for consistency
            }
        
        img_assets_dir = self._get_image_assets_dir(pdf_path, metadata)
        
        try:
            results_report = self.image_extractor.extract_images_from_pdf(pdf_path, img_assets_dir)
            
            extracted_count = results_report.get('extracted_count', 0)
            failed_count = results_report.get('failed_count', 0)
            logger.info(f"Image extraction for {pdf_path} completed: {extracted_count} images extracted successfully, {failed_count} failed/problematic.")
            if results_report.get('report_path'):
                logger.info(f"Image extraction report saved to: {results_report['report_path']}")
            # Ensure the report contains the output_dir used, for post_process_markdown
            if 'output_dir' not in results_report:
                results_report['output_dir'] = img_assets_dir
            return results_report
        except Exception as e:
            error_msg = f"Failed to extract images from {pdf_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False, 
                'errors': [error_msg],
                'extracted_count': 0,
                'failed_count': 0,
                'problematic_images': [],
                'metrics': {},
                'output_dir': img_assets_dir, # Still provide the intended output_dir
                'report_path': None
            }
    
    def _get_image_assets_dir(self, pdf_path: str, metadata: Dict[str, Any]) -> str: # Added type hints
        """Determine the image assets directory path."""
        try:
            abs_pdf_source_dir = os.path.abspath(settings.PDF_SOURCE_DIR)
            abs_pdf_path = os.path.abspath(pdf_path)
            
            if abs_pdf_path.startswith(abs_pdf_source_dir):
                 rel_path = os.path.relpath(abs_pdf_path, abs_pdf_source_dir)
            else:
                logger.warning(f"PDF path {pdf_path} is not relative to PDF_SOURCE_DIR {abs_pdf_source_dir}. Using basename for target structure.")
                pdf_parent_dir_name = os.path.basename(os.path.dirname(abs_pdf_path))
                rel_path = os.path.join(pdf_parent_dir_name or "_external", os.path.basename(pdf_path))
        except ValueError:
            rel_path = os.path.basename(pdf_path)
        
        md_rel_base = os.path.splitext(rel_path)[0]
        target_md_dir = os.path.join(settings.MARKDOWN_TARGET_DIR, os.path.dirname(md_rel_base))
        md_filename_without_ext = os.path.basename(md_rel_base)

        img_assets_dir_name = f"{md_filename_without_ext}{settings.IMAGE_ASSETS_SUFFIX}"
        img_assets_dir = os.path.join(target_md_dir, img_assets_dir_name)
        
        os.makedirs(img_assets_dir, exist_ok=True)
        return img_assets_dir
    
    def post_process_markdown(self, 
                              content: str, 
                              metadata: Dict[str, Any], 
                              image_extraction_results: Optional[Dict[str, Any]] = None,
                              original_pdf_path: Optional[str] = None) -> str: # Added original_pdf_path parameter
        """Apply post-processing to the generated markdown."""
        logger.info("Starting markdown post-processing")
        
        markdown_code_pattern = r'```\s*markdown\s*\n'
        has_markdown_marker = bool(re.search(markdown_code_pattern, content))
        
        frontmatter_patterns = [
            r'^---\s+(.*?)\s+---',
            r'```\s*markdown\s*\n---\s+(.*?)\s+---'
        ]
        
        frontmatter_match = None
        for pattern in frontmatter_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                frontmatter_match = match
                break
        
        if frontmatter_match:
            try:
                frontmatter_text = frontmatter_match.group(1)
                extracted_metadata = yaml.safe_load(frontmatter_text) or {}
                
                content = content[frontmatter_match.end():].strip()
                if has_markdown_marker:
                    content = re.sub(r'^```\s*markdown\s*\n', '', content, flags=re.IGNORECASE)
                    content = re.sub(r'\n```\s*$', '', content)

                merged_metadata = metadata.copy()
                if 'unit-title' in extracted_metadata:
                    merged_metadata['unit_title'] = extracted_metadata['unit-title']
                if 'subject' in extracted_metadata:
                    merged_metadata['subject'] = extracted_metadata['subject']
                
                new_frontmatter = self.generate_frontmatter(merged_metadata)
                content = f"{new_frontmatter}\n\n{content.strip()}"
            except Exception as e:
                logger.error(f"Error processing Gemini frontmatter: {e}. Using standard frontmatter.")
                new_frontmatter = self.generate_frontmatter(metadata)
                content = re.sub(r'^---\s+.*?\s+---\s*', '', content, flags=re.DOTALL).strip()
                content = re.sub(r'^```\s*markdown\s*\n', '', content, flags=re.IGNORECASE).strip()
                content = re.sub(r'\n```\s*$', '', content).strip()
                content = f"{new_frontmatter}\n\n{content}"
        else:
            new_frontmatter = self.generate_frontmatter(metadata)
            content = f"{new_frontmatter}\n\n{content.strip()}"
        
        required_sections = [
            'INTRODUCTION', 'LEARNING-OBJECTIVES', 'MAIN-CONTENT-AREA', 'KEY-TAKEAWAYS'
        ]
        for section in required_sections:
            section_marker = f"<!-- SECTION: {section} -->"
            if section_marker not in content:
                if section == 'KEY-TAKEAWAYS':
                    content += f"\n\n{section_marker}\n\n## Key Takeaways\n\n"
                elif section == 'MAIN-CONTENT-AREA' and '## ' in content:
                    content = re.sub(r'(## .+)', f'{section_marker}\n\n\\1', content, 1)
                else:
                    content += f"\n\n{section_marker}\n\n"

        md_filename_without_ext = metadata.get('unit_title_id', 'unknown_unit')
        safe_unit_title_id = re.sub(r'[^\w\-_\.]', '_', md_filename_without_ext)
        img_assets_dir_name = f"{safe_unit_title_id}{settings.IMAGE_ASSETS_SUFFIX}"
        img_assets_relative_path = f"./{img_assets_dir_name}"
        
        actual_img_assets_dir_on_disk = None
        if image_extraction_results:
            # Prefer output_dir from the report, as this is where images were saved.
            actual_img_assets_dir_on_disk = image_extraction_results.get('output_dir')
            if not actual_img_assets_dir_on_disk and image_extraction_results.get('report_path'):
                # Fallback: if report_path is present, its dirname is the output_dir
                actual_img_assets_dir_on_disk = os.path.dirname(image_extraction_results.get('report_path'))
        
        # If still not found, and original_pdf_path is available, reconstruct it.
        # This is the fix for the "pdf_info is not defined" error.
        if not actual_img_assets_dir_on_disk and original_pdf_path:
             logger.warning("Reconstructing actual_img_assets_dir_on_disk using original_pdf_path as it was not in image_extraction_results.")
             actual_img_assets_dir_on_disk = self._get_image_assets_dir(original_pdf_path, metadata)
        elif not actual_img_assets_dir_on_disk:
            logger.error("Could not determine actual_img_assets_dir_on_disk. Image references may be incorrect.")


        content = self._process_image_references(
            content,
            img_assets_relative_path,
            actual_img_assets_dir_on_disk,
            image_extraction_results
        )
        
        content = re.sub(r'(\n*)(<!--.*?-->)(\n*)', r'\n\n\2\n\n', content)
        content = re.sub(r'\n{3,}', '\n\n', content).strip()
        
        logger.info("Completed markdown post-processing")
        return content
    
    # Corrected type hints for _process_image_references
    def _process_image_references(self, 
                                  content: str, 
                                  md_img_assets_path: str, 
                                  disk_img_assets_path: Optional[str], 
                                  image_extraction_results: Optional[Dict[str, Any]]) -> str:
        """
        Process image references in the markdown content.
        
        Args:
            content: Markdown content with image references.
            md_img_assets_path: Relative path to image assets directory for use in markdown (e.g., "./unit-img-assets").
            disk_img_assets_path: Absolute or full path to image assets directory on disk for listing files.
            image_extraction_results: Results from image extraction (the report dictionary).
            
        Returns:
            Updated markdown content with fixed image references.
        """
        logger.debug(f"Processing image references. Markdown assets path: {md_img_assets_path}, Disk assets path: {disk_img_assets_path}")

        if not image_extraction_results or not disk_img_assets_path or not os.path.exists(disk_img_assets_path):
            logger.warning(f"Image extraction results or disk image assets path not available/found ({disk_img_assets_path}). Using generic image references.")
            img_pattern = r'!\[(.*?)\]\((?!https?://)(.*?)\)'
            
            def generic_replace(match):
                alt_text = match.group(1)
                return f"![{alt_text}]({md_img_assets_path}/placeholder-image.png)"

            content = re.sub(img_pattern, generic_replace, content)
            content += "\n\n<!-- WARNING: Image extraction results not fully available or assets directory missing. Image links may be placeholders. -->\n"
            return content

        try:
            saved_image_files = sorted([
                f for f in os.listdir(disk_img_assets_path)
                if os.path.isfile(os.path.join(disk_img_assets_path, f)) and
                   f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) and
                   not f.startswith('placeholder-')
            ])
            logger.debug(f"Found saved image files in {disk_img_assets_path}: {saved_image_files}")
        except FileNotFoundError:
            logger.warning(f"Disk image assets directory not found: {disk_img_assets_path}. Cannot list saved images.")
            saved_image_files = []
        
        available_images_on_disk = saved_image_files[:]
        problematic_images_info = {}
        if image_extraction_results.get('problematic_images'):
            for p_img in image_extraction_results['problematic_images']:
                page = p_img.get('page')
                index_on_page = p_img.get('index_on_page')
                if page is not None and index_on_page is not None:
                    key = f"{page}-{index_on_page + 1}"
                    problematic_images_info[key] = p_img
        logger.debug(f"Problematic images info: {problematic_images_info}")

        img_pattern = r'!\[(.*?)\]\((.*?)\)'
        processed_indices = set()

        def replace_image_smartly(match):
            alt_text = match.group(1)
            original_path_in_md = match.group(2)

            if original_path_in_md.startswith(('http://', 'https://', '/')):
                return match.group(0)

            logger.debug(f"Found MD image: alt='{alt_text}', original_path='{original_path_in_md}'")
            page_num, img_idx_on_page = None, None
            
            fn_match = re.search(r'fig\d*-page(\d+)-img(\d+)\.\w+', original_path_in_md, re.IGNORECASE)
            if fn_match:
                page_num = int(fn_match.group(1))
                img_idx_on_page = int(fn_match.group(2))
                logger.debug(f"Parsed from MD path filename: page={page_num}, idx={img_idx_on_page}")

            if page_num is None:
                alt_text_lower = alt_text.lower()
                m = re.search(r'(?:page\s*(\d+))?[^\d\w]*(?:(?:image|figure|fig|img)\s*(?:(\d+)(?:\.(\d+))?|(\d+)))', alt_text_lower)
                if m:
                    if m.group(1): page_num = int(m.group(1))
                    if m.group(2) and m.group(3):
                        if page_num is None: page_num = int(m.group(2))
                        img_idx_on_page = int(m.group(3))
                    elif m.group(2):
                        if page_num is None: img_idx_on_page = int(m.group(2))
                        else: img_idx_on_page = int(m.group(2))
                    elif m.group(4):
                         img_idx_on_page = int(m.group(4))
                logger.debug(f"Parsed from alt text: page={page_num}, idx={img_idx_on_page}")

            if page_num is not None and img_idx_on_page is not None:
                problem_key = f"{page_num}-{img_idx_on_page}"
                if problem_key in problematic_images_info:
                    issue_info = problematic_images_info[problem_key]
                    issue_type_val = issue_info.get('issue_type', 'unknown_issue')
                    issue_details = issue_info.get('issue', 'Details not available')
                    placeholder_name = "placeholder-error.png"
                    if issue_type_val == ImageIssueType.BLANK.value: placeholder_name = "placeholder-blank.png"
                    elif issue_type_val == ImageIssueType.CORRUPT.value: placeholder_name = "placeholder-corrupt.png"
                    warning_comment = (f"\n<!-- WARNING: Image from Page {page_num}, Index {img_idx_on_page} "
                                       f"had an issue: {issue_type_val}. Details: {issue_details}. "
                                       f"Using placeholder. -->\n")
                    logger.warning(f"Image ref for Page {page_num}, Index {img_idx_on_page} was problematic: {issue_type_val}. Using placeholder.")
                    return f"{warning_comment}![{alt_text} (Issue: {issue_type_val})]({md_img_assets_path}/{placeholder_name})"

            target_saved_image = None
            if page_num is not None and img_idx_on_page is not None:
                for i, disk_img_name in enumerate(available_images_on_disk):
                    if i in processed_indices: continue
                    fn_page_match = re.search(r'-page(\d+)-', disk_img_name, re.IGNORECASE)
                    fn_idx_match = re.search(r'-img(\d+)\.', disk_img_name, re.IGNORECASE)
                    if fn_page_match and fn_idx_match:
                        saved_page = int(fn_page_match.group(1))
                        saved_idx = int(fn_idx_match.group(1))
                        if saved_page == page_num and saved_idx == img_idx_on_page:
                            target_saved_image = disk_img_name
                            processed_indices.add(i)
                            break
            
            if target_saved_image:
                logger.info(f"Matched MD ref (P:{page_num}, I:{img_idx_on_page}) to disk image: {target_saved_image}")
                return f"![{alt_text}]({md_img_assets_path}/{target_saved_image})"
            else:
                for i, disk_img_name in enumerate(available_images_on_disk):
                    if i not in processed_indices:
                        processed_indices.add(i)
                        logger.info(f"Sequentially mapping MD ref '{alt_text}' to disk image: {disk_img_name}")
                        return f"![{alt_text}]({md_img_assets_path}/{disk_img_name})"

            logger.warning(f"No matching or available disk image found for MD ref: '{alt_text}'. Using error placeholder.")
            return f"![{alt_text} (Image Not Found)]({md_img_assets_path}/placeholder-error.png)"

        content = re.sub(img_pattern, replace_image_smartly, content)
        
        unused_disk_images = [img_name for i, img_name in enumerate(available_images_on_disk) if i not in processed_indices]
        if unused_disk_images:
            logger.warning(f"Found {len(unused_disk_images)} extracted images on disk that were not referenced in the markdown: {unused_disk_images}")
            content += (f"\n\n<!-- WARNING: There were {len(unused_disk_images)} extracted images "
                        f"on disk that were not referenced in the markdown content: {', '.join(unused_disk_images)}. "
                        f"These may be extra images or the markdown references might need adjustment. -->\n")
            
        return content

    def generate_frontmatter(self, metadata: Dict[str, Any]) -> str: # Added type hint
        """Generate YAML frontmatter from metadata."""
        return f"""---
unit-id: {metadata.get('unit_id', 'UNI0000')}
unit-title-id: {metadata.get('unit_title_id', 'unknown_title_id')}
unit-title: {metadata.get('unit_title', 'Unknown Title')}
phase: {metadata.get('phase', 'Unknown')}
subject: {metadata.get('subject', 'Unknown Subject')}
parent-module-id: {metadata.get('parent_module_id', 'MOD0000')}
parent-course-id: {metadata.get('parent_course_id', 'COU0000')}
batch-id: {metadata.get('batch_id', 'BAT0001')}
extraction-date: {metadata.get('extraction_date', datetime.now().strftime('%Y-%m-%d'))}
extractor-name: "Automated Extraction"
---"""