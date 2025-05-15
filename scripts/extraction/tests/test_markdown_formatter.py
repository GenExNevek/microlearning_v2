"""Test script for the Markdown Formatter module."""

import os
import sys
import argparse
from scripts.extraction.pdf_reader import PDFReader
from scripts.extraction.markdown_formatter import MarkdownFormatter
from scripts.config import settings

def test_markdown_extraction(pdf_path=None, output_path=None):
    """Test PDF extraction to markdown format."""
    # Initialize the PDF reader
    reader = PDFReader()
    
    # Initialize the markdown formatter
    formatter = MarkdownFormatter(reader)
    
    if not pdf_path:
        # If no specific PDF provided, use the first PDF found in the source directory
        for root, _, files in os.walk(settings.PDF_SOURCE_DIR):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_path = os.path.join(root, file)
                    break
            if pdf_path:
                break
    
    if not pdf_path or not os.path.exists(pdf_path):
        print(f"Error: No PDF file found to test.")
        return False
        
    print(f"Testing markdown extraction for: {pdf_path}")
    
    try:
        # Read the PDF
        pdf_info = reader.read_pdf_from_path(pdf_path)
        
        # Extract metadata from the path
        metadata = formatter.extract_metadata_from_path(pdf_path)
        print("\nExtracted metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")
        
        # Extract and format the content
        print("\nExtracting and formatting content...")
        result = formatter.extract_and_format(pdf_info, metadata)
        
        if result['success']:
            print("SUCCESS! Content was extracted and formatted successfully.")
            
            # Generate output filename if not provided
            if not output_path:
                filename = os.path.basename(pdf_path)
                filename_without_ext = os.path.splitext(filename)[0]
                output_path = os.path.join('output', f"{filename_without_ext}.md")
            
            # Ensure the output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save the content to a file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result['content'])
            
            print(f"Content saved to: {output_path}")
            
            # Preview the first 500 characters
            preview_length = min(500, len(result['content']))
            print("\nPreview of extracted content:")
            print("-" * 50)
            print(result['content'][:preview_length] + "...")
            print("-" * 50)
            
            return True
        else:
            print(f"ERROR: Failed to extract content: {result['error']}")
            return False
            
    except Exception as e:
        print(f"ERROR: An exception occurred: {str(e)}")
        return False

def main():
    """Main function for the test script."""
    parser = argparse.ArgumentParser(description='Test markdown extraction with Gemini API.')
    parser.add_argument('--pdf', help='Path to a specific PDF file to test')
    parser.add_argument('--output', help='Path to save the output markdown file')
    args = parser.parse_args()
    
    success = test_markdown_extraction(args.pdf, args.output)
    
    if success:
        print("\nTest completed successfully.")
    else:
        print("\nTest failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()