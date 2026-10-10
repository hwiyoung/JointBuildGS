#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utility functions for the result visualization tools.
"""

import os
import numpy as np
from PIL import Image


def save_image(image_array, output_path):
    """
    Save an image array to a file.
    
    Parameters:
        image_array (numpy.ndarray): Image array (values in [0, 1] range)
        output_path (str): Output file path
    """
    # Convert to uint8
    img_uint8 = (image_array * 255).astype(np.uint8)
    img = Image.fromarray(img_uint8)
    img.save(output_path)
    print(f"Image saved to: {output_path}")


def ensure_directory_exists(directory_path):
    """
    Ensure the specified directory exists, creating it if necessary.
    
    Parameters:
        directory_path (str): Path to the directory to ensure
    """
    os.makedirs(directory_path, exist_ok=True)
    print(f"Ensured directory exists: {directory_path}")