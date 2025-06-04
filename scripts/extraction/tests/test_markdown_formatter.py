# scripts/extraction/tests/test_markdown_formatter.py

"""Test script for the Markdown Formatter module."""

import os
import sys
import argparse
# Import necessary types
from typing import Any, Optional, Dict

# Assuming these modules are siblings or structured appropriately in the project
from scripts.extraction.pdf_reader import PDFReader
from scripts.extraction.markdown_formatter import MarkdownFormatter
from scripts.config import settings

def test_markdown_extraction(pdf_path: Optional[str] = None, output_path: Optional[str] = None) -> bool: # Added type hints
    """Test PDF extraction to markdown format."""
    # Initialize the PDF reader
    reader = PDFReader()

    # Initialize the markdown formatter
    formatter = MarkdownFormatter(reader)

    if not pdf_path:
        # If no specific PDF provided, use the first PDF found in the source directory
        pdf_path = None # Ensure it's None before search
        try:
            for root, _, files in os.walk(settings.PDF_SOURCE_DIR):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        pdf_path = os.path.join(root, file)
                        break
                if pdf_path:
                    break # Stop outer loop once file is found
        except FileNotFoundError:
            print(f"Error: PDF_SOURCE_DIR not found: {settings.PDF_SOURCE_DIR}")
            return False


    if not pdf_path or not os.path.exists(pdf_path):
        print(f"Error: No PDF file found to test.")
        if settings.PDF_SOURCE_DIR and not os.path.exists(settings.PDF_SOURCE_DIR):
             print(f"Please ensure the configured PDF_SOURCE_DIR exists: {settings.PDF_SOURCE_DIR}")
        return False

    print(f"Testing markdown extraction for: {pdf_path}")

    try:
        # Read the PDF
        # Assuming read_pdf_from_path returns a Dict[str, Any]
        pdf_info: Dict[str, Any] = reader.read_pdf_from_path(pdf_path) # Added type hint

        # Extract metadata from the path
        # Assuming extract_metadata_from_path returns a Dict[str, Any]
        metadata: Dict[str, Any] = formatter.extract_metadata_from_path(pdf_path) # Added type hint
        print("\nExtracted metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")

        # Extract and format the content
        print("\nExtracting and formatting content...")
        # Assuming extract_and_format returns a Dict[str, Any]
        result: Dict[str, Any] = formatter.extract_and_format(pdf_info, metadata) # Added type hint

        if result.get('success'): # Use .get() for safety
            print("SUCCESS! Content was extracted and formatted successfully.")

            # Generate output filename if not provided
            if not output_path:
                filename = os.path.basename(pdf_path)
                filename_without_ext = os.path.splitext(filename)[0]
                # Use a dedicated test output directory
                output_dir = os.path.join('test_output', 'markdown_formatter')
                output_path = os.path.join(output_dir, f"{filename_without_ext}.md")
            else:
                 # Ensure output_path is absolute if needed, or just ensure its directory exists
                 output_dir = os.path.dirname(output_path)
                 if not output_dir: # If just a filename was provided
                      output_dir = '.' # Use current directory


            # Ensure the output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save the content to a file
            with open(output_path, 'w', encoding='utf-8') as f:
                # Use .get() for content safety
                f.write(result.get('content', ''))

            print(f"Content saved to: {output_path}")

            # Also save the image extraction report if available
            image_extraction_results = result.get('image_extraction', {})
            report_path = image_extraction_results.get('report_path')
            if report_path and os.path.exists(report_path):
                 print(f"Image extraction report saved to: {report_path}")
            elif image_extraction_results and image_extraction_results.get('report_text'):
                 # If report wasn't saved by extractor, save it here for the test
                 # Determine report path based on the markdown output path
                 md_filename_without_ext = os.path.splitext(os.path.basename(output_path))[0]
                 img_assets_dir_name = f"{md_filename_without_ext}-img-assets"
                 img_assets_folder_for_report = os.path.join(os.path.dirname(output_path), img_assets_dir_name)
                 os.makedirs(img_assets_folder_for_report, exist_ok=True)
                 fallback_report_path = os.path.join(img_assets_folder_for_report, "image_extraction_report.md")

                 try:
                     with open(fallback_report_path, 'w', encoding='utf-8') as f:
                          f.write(image_extraction_results['report_text'])
                     print(f"Image extraction report saved to: {fallback_report_path}")
                 except Exception as report_save_e:
                      print(f"Warning: Failed to save fallback image extraction report: {report_save_e}")

            # Preview the first 500 characters
            content_preview = result.get('content', '')
            preview_length = min(500, len(content_preview))
            print("\nPreview of extracted content:")
            print("-" * 50)
            print(content_preview[:preview_length] + "...")
            print("-" * 50)

            # Log image extraction summary
            img_extracted_count = image_extraction_results.get('extracted_count', 0)
            img_failed_count = image_extraction_results.get('failed_count', 0)
            img_problematic_count = len(image_extraction_results.get('problematic_images', []))

            print(f"\nImage Extraction Summary:")
            print(f"  Successfully extracted: {img_extracted_count}")
            print(f"  Problematic/Failed: {img_failed_count} (Details in report)")
            print(f"  Total problematic images listed: {img_problematic_count}")


            return True
        else:
            print(f"ERROR: Failed to extract content: {result.get('error', 'Unknown error from result')}")
            # Also print image extraction errors if any
            image_extraction_results = result.get('image_extraction', {})
            if image_extraction_results.get('errors'):
                 print("\nImage Extraction Errors/Warnings:")
                 for err in image_extraction_results['errors']:
                      print(f"  - {err}")
            return False

    except Exception as e:
        print(f"ERROR: An unexpected exception occurred: {str(e)}")
        import traceback
        traceback.print_exc() # Print traceback for debugging
        return False

def main() -> None: # Added type hint
    """Main function for the test script."""
    parser = argparse.ArgumentParser(description='Test markdown extraction with Gemini API.')
    parser.add_argument('--pdf', help='Path to a specific PDF file to test')
    parser.add_argument('--output', help='Path to save the output markdown file')
    args = parser.parse_args()

    success = test_markdown_extraction(args.pdf, args.output)

    if success:
        print("\nTest completed successfully.")
        sys.exit(0) # Exit with success code
    else:
        print("\nTest failed.")
        sys.exit(1) # Exit with failure code

if __name__ == "__main__":
    main()