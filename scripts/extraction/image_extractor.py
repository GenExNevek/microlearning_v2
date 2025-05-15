"""Module for extracting images from PDF files."""

import os
import logging
import fitz  # PyMuPDF
from PIL import Image
import io
from ..config import settings

logger = logging.getLogger(__name__)

class ImageExtractor:
    """Handles image extraction from PDF files."""
    
    def __init__(self):
        """Initialize the ImageExtractor with configuration settings."""
        self.config = settings.IMAGE_EXTRACTION_CONFIG
        self.dpi = self.config.get("dpi", 150)
        self.image_format = self.config.get("image_format", "png")
        self.quality = self.config.get("quality", 95)
        self.max_width = self.config.get("max_width", 1920)
        self.max_height = self.config.get("max_height", 1080)
        self.min_width = self.config.get("min_width", 50)
        self.min_height = self.config.get("min_height", 50)
        self.supported_formats = self.config.get("supported_formats", ["png", "jpg", "jpeg"])
    
    def extract_images_from_pdf(self, pdf_path, output_dir):
        """
        Extract all images from a PDF file and save them to the specified directory.
        
        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory where images will be saved
            
        Returns:
            Dictionary containing extraction results
        """
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Track results
        results = {
            'success': True,
            'extracted_count': 0,
            'failed_count': 0,
            'images': [],
            'errors': []
        }
        
        try:
            # Open the PDF
            pdf_document = fitz.open(pdf_path)
            image_counter = 0
            
            # Iterate through all pages
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                
                # Get images list for this page
                image_list = page.get_images(full=True)
                
                for img_index, img in enumerate(image_list):
                    try:
                        # Extract image
                        image_counter += 1
                        extracted_image = self._extract_single_image(
                            pdf_document, 
                            img, 
                            page_num + 1,
                            image_counter
                        )
                        
                        if extracted_image:
                            # Save the image
                            image_filename = f"fig{image_counter}-page{page_num + 1}-img{img_index + 1}.{self.image_format}"
                            image_path = os.path.join(output_dir, image_filename)
                            
                            self._save_image(extracted_image, image_path)
                            
                            results['extracted_count'] += 1
                            results['images'].append({
                                'filename': image_filename,
                                'path': image_path,
                                'page': page_num + 1,
                                'index': img_index + 1
                            })
                            
                            logger.info(f"Extracted image: {image_filename}")
                    
                    except Exception as e:
                        error_msg = f"Failed to extract image {img_index + 1} from page {page_num + 1}: {str(e)}"
                        logger.error(error_msg)
                        results['failed_count'] += 1
                        results['errors'].append(error_msg)
            
            pdf_document.close()
            
        except Exception as e:
            error_msg = f"Failed to process PDF {pdf_path}: {str(e)}"
            logger.error(error_msg)
            results['success'] = False
            results['errors'].append(error_msg)
        
        # Log summary
        logger.info(f"Image extraction complete for {pdf_path}: "
                   f"{results['extracted_count']} extracted, "
                   f"{results['failed_count']} failed")
        
        return results
    
    def _extract_single_image(self, pdf_document, img_info, page_num, image_counter):
        """
        Extract a single image from PDF.
        
        Args:
            pdf_document: PyMuPDF document object
            img_info: Image information tuple
            page_num: Page number (1-indexed)
            image_counter: Global image counter
            
        Returns:
            PIL Image object or None if extraction failed
        """
        # Get the XREF of the image
        xref = img_info[0]
        
        # Extract the image
        pix = fitz.Pixmap(pdf_document, xref)
        
        if pix.n - pix.alpha < 4:  # GRAY or RGB
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:  # CMYK
            pil_image = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
            pil_image = pil_image.convert("RGB")
        
        pix = None  # free memory
        
        # Check minimum size requirements
        if pil_image.width < self.min_width or pil_image.height < self.min_height:
            logger.debug(f"Skipping small image on page {page_num}: "
                        f"{pil_image.width}x{pil_image.height}")
            return None
        
        # Resize if needed while maintaining aspect ratio
        if self.config.get("maintain_aspect_ratio", True):
            pil_image = self._resize_image(pil_image)
        
        return pil_image
    
    def _resize_image(self, image):
        """
        Resize image if it exceeds maximum dimensions while maintaining aspect ratio.
        
        Args:
            image: PIL Image object
            
        Returns:
            Resized PIL Image object
        """
        width, height = image.size
        
        # Calculate scaling factor
        scale_factor = min(
            self.max_width / width if width > self.max_width else 1,
            self.max_height / height if height > self.max_height else 1
        )
        
        if scale_factor < 1:
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")
        
        return image
    
    def _save_image(self, image, path):
        """
        Save PIL Image to file.
        
        Args:
            image: PIL Image object
            path: Output file path
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Save with appropriate quality
        save_kwargs = {}
        if self.image_format.lower() in ['jpg', 'jpeg']:
            save_kwargs['quality'] = self.quality
            save_kwargs['optimize'] = True
        elif self.image_format.lower() == 'png':
            save_kwargs['compress_level'] = 9
        
        image.save(path, format=self.image_format.upper(), **save_kwargs)
        logger.debug(f"Saved image to: {path}")