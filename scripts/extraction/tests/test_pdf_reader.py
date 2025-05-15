"""Test script for the PDF Reader module."""

import os
import sys
import argparse
from scripts.extraction.pdf_reader import PDFReader
from ..config import settings

def test_pdf_reading(pdf_path=None):
    """Test PDF reading with Gemini API."""
    reader = PDFReader()
    
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
        
    print(f"Testing PDF reading for: {pdf_path}")
    
    try:
        # Read the PDF
        pdf_info = reader.read_pdf_from_path(pdf_path)
        
        # Test if Gemini can process it
        result = reader.test_pdf_reading(pdf_info)
        
        if result['success']:
            print("SUCCESS! Gemini was able to read the PDF.")
            print("\nSummary of PDF content:")
            print("-" * 50)
            print(result['summary'])
            print("-" * 50)
            return True
        else:
            print(f"ERROR: Failed to process the PDF: {result['error']}")
            return False
            
    except Exception as e:
        print(f"ERROR: An exception occurred: {str(e)}")
        return False

def main():
    """Main function for the test script."""
    parser = argparse.ArgumentParser(description='Test PDF reading with Gemini API.')
    parser.add_argument('--pdf', help='Path to a specific PDF file to test')
    args = parser.parse_args()
    
    success = test_pdf_reading(args.pdf)
    
    if success:
        print("\nTest completed successfully.")
    else:
        print("\nTest failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()