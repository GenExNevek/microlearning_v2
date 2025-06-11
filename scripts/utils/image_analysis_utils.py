import imagehash
from PIL import Image
import cv2
import numpy as np
from skimage import measure
from typing import Tuple, List

def compute_perceptual_hash(pil_image: Image.Image) -> str:
    """
    Computes a perceptual hash (pHash) for an image, which is robust to minor variations.
    """
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    return str(imagehash.phash(pil_image))

def compute_visual_similarity(hash1: str, hash2: str) -> float:
    """
    Calculates visual similarity based on the Hamming distance between two perceptual hashes.
    Returns a score from 0.0 (completely different) to 1.0 (identical).
    """
    if not hash1 or not hash2:
        return 0.0
    h1 = imagehash.hex_to_hash(hash1)
    h2 = imagehash.hex_to_hash(hash2)
    # The division normalizes the distance to a 0-1 similarity score
    return 1.0 - (h1 - h2) / len(h1.hash)**2

def calculate_edge_density(pil_image: Image.Image) -> float:
    """
    Calculates the density of edges in the image.
    High density can suggest diagrams or complex textures.
    """
    if pil_image.mode != 'L':
        pil_image = pil_image.convert('L') # Convert to grayscale
    image_np = np.array(pil_image)
    edges = cv2.Canny(image_np, 100, 200)
    return np.sum(edges > 0) / edges.size

def calculate_color_complexity(pil_image: Image.Image) -> float:
    """
    Calculates the complexity of colors in an image.
    High complexity is common in photographs, while diagrams and icons have low complexity.
    """
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    image_np = np.array(pil_image)
    # Calculate the number of unique colors, normalized by the total number of pixels
    # Reshape the image to be a list of pixels
    pixels = image_np.reshape(-1, 3)
    # Get unique colors and their counts
    unique_colors = np.unique(pixels, axis=0)
    return len(unique_colors) / pixels.shape[0]

def is_likely_blank(pil_image: Image.Image, threshold=0.99) -> bool:
    """
    Determines if an image is likely blank or single-colored by checking its standard deviation.
    """
    image_np = np.array(pil_image.convert('L')) # Grayscale for simplicity
    return image_np.std() < 5