"""Module for file writing and directory management."""

import os
import shutil

class FileWriter:
    """Handles file writing and directory creation."""
    
    @staticmethod
    def ensure_directory(directory_path):
        """Ensure a directory exists, creating it if necessary."""
        if not os.path.exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)
        return directory_path
    
    @staticmethod
    def write_markdown_file(content, file_path):
        """Write markdown content to a file."""
        # Ensure the directory exists
        directory = os.path.dirname(file_path)
        FileWriter.ensure_directory(directory)
        
        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return file_path
    
    @staticmethod
    def create_image_assets_folder(markdown_path):
        """Create an image assets folder corresponding to a markdown file."""
        directory = os.path.dirname(markdown_path)
        filename = os.path.basename(markdown_path)
        filename_without_ext = os.path.splitext(filename)[0]
        
        # Create the image assets folder name
        img_assets_folder = os.path.join(directory, f"{filename_without_ext}-img-assets")
        
        # Ensure the folder exists
        FileWriter.ensure_directory(img_assets_folder)
        
        return img_assets_folder
    
    @staticmethod
    def mirror_directory_structure(source_dir, target_dir, transform_func=None):
        """
        Mirror directory structure from source to target with transformation.
        
        Args:
            source_dir: Source directory path
            target_dir: Target directory path
            transform_func: Function to transform source files to target files
                           Should take (source_path, target_path) and return success boolean
        """
        # Ensure the target directory exists
        FileWriter.ensure_directory(target_dir)
        
        # Track success/failure
        success_count = 0
        failure_count = 0
        failures = []
        
        # Walk through the source directory
        for root, dirs, files in os.walk(source_dir):
            # Calculate the relative path from the source directory
            rel_path = os.path.relpath(root, source_dir)
            
            # Create the corresponding target directory
            target_path = os.path.join(target_dir, rel_path) if rel_path != '.' else target_dir
            FileWriter.ensure_directory(target_path)
            
            # Process each file if a transform function is provided
            if transform_func:
                for file in files:
                    source_file = os.path.join(root, file)
                    target_file = os.path.join(target_path, file)
                    
                    # Apply the transformation function
                    try:
                        result = transform_func(source_file, target_file)
                        if result:
                            success_count += 1
                        else:
                            failure_count += 1
                            failures.append(source_file)
                    except Exception as e:
                        failure_count += 1
                        failures.append(f"{source_file} (Error: {str(e)})")
        
        return {
            'success_count': success_count,
            'failure_count': failure_count,
            'failures': failures
        }