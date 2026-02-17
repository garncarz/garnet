#!/usr/bin/env python3
"""
Watershed Segmentation for Image Processing

This script performs watershed segmentation on an input image and exports
the segmented regions as separate SVG paths.

Usage:
    ./watershed_segmentation.py input_image.jpg [--output output.svg]
"""

import argparse
from pathlib import Path
import numpy as np
import cv2


def load_image(img_path: Path):
    """Load image and convert to grayscale."""
    img = cv2.imread(str(img_path))
    if img is None:
        raise ValueError(f"Could not load image: {img_path}")
    
    # Convert to RGB (OpenCV loads as BGR)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    # Convert to grayscale for processing
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    return img_rgb, gray, img.shape[:2]


def preprocess_image(gray):
    """Preprocess image for watershed segmentation."""
    # Apply bilateral filter to reduce noise while keeping edges sharp
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Apply adaptive thresholding to handle varying illumination
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # Remove small noise with morphological opening
    kernel = np.ones((3, 3), np.uint8)
    opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
    
    return opening


def perform_watershed(binary_img):
    """
    Perform watershed segmentation on binary image.
    
    Returns:
        labels: Array where each unique value represents a different segment
    """
    # Distance transform to find sure foreground
    dist_transform = cv2.distanceTransform(binary_img, cv2.DIST_L2, 5)
    
    # Threshold to get sure foreground
    _, sure_fg = cv2.threshold(dist_transform, 0.3 * dist_transform.max(), 255, 0)
    sure_fg = np.uint8(sure_fg)
    
    # Dilate to get sure background
    kernel = np.ones((3, 3), np.uint8)
    sure_bg = cv2.dilate(binary_img, kernel, iterations=3)
    
    # Find unknown region
    unknown = cv2.subtract(sure_bg, sure_fg)
    
    # Label markers for watershed
    _, markers = cv2.connectedComponents(sure_fg)
    
    # Add 1 to all labels so background is not 0, but 1
    markers = markers + 1
    
    # Mark the unknown region as 0
    markers[unknown == 255] = 0
    
    # Create a 3-channel image for watershed (needs color image)
    img_for_watershed = cv2.merge([binary_img, binary_img, binary_img])
    
    # Apply watershed
    markers = cv2.watershed(img_for_watershed, markers)
    
    return markers


def extract_contours(labels, min_area=50):
    """
    Extract contours from segmented labels.
    
    Args:
        labels: Watershed labels array
        min_area: Minimum area threshold to filter small segments
    
    Returns:
        List of contours (each contour is a list of (x, y) points)
    """
    contours_list = []
    
    # Get unique labels (excluding background -1 and 1)
    unique_labels = np.unique(labels)
    unique_labels = unique_labels[(unique_labels > 1)]
    
    for label in unique_labels:
        # Create binary mask for this label
        mask = np.uint8(labels == label) * 255
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            # Calculate area and filter small regions
            area = cv2.contourArea(contour)
            if area >= min_area:
                # Simplify contour to reduce points
                epsilon = 0.005 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Convert to list of (x, y) tuples
                points = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
                if len(points) >= 3:  # Need at least 3 points for a polygon
                    contours_list.append(points)
    
    return contours_list


def path_d_from_points(pts):
    """
    Convert list of points to SVG path 'd' attribute.
    
    Args:
        pts: List of (x, y) tuples
    
    Returns:
        SVG path string
    """
    if not pts or len(pts) < 3:
        return ""
    
    # Start with Move command
    path_parts = [f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"]
    
    # Add Line commands for remaining points
    for x, y in pts[1:]:
        path_parts.append(f"L {x:.2f},{y:.2f}")
    
    # Close path
    path_parts.append("Z")
    
    return " ".join(path_parts)


def export_svg(contours, width, height, output_path: Path):
    """
    Export contours as SVG file with separate paths for each segment.
    
    Args:
        contours: List of contours (each is a list of (x, y) points)
        width: Image width
        height: Image height
        output_path: Path to save SVG file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        # Write SVG header
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" ')
        f.write(f'width="{width}" height="{height}" ')
        f.write(f'viewBox="0 0 {width} {height}">\n')
        
        # Write group for all segments
        f.write('  <g id="watershed-segments" fill="none" stroke="#ff0000" stroke-width="2">\n')
        
        # Write each contour as a separate path
        for i, contour in enumerate(contours):
            path_d = path_d_from_points(contour)
            if path_d:
                f.write(f'    <path id="segment_{i}" d="{path_d}" />\n')
        
        f.write("  </g>\n")
        f.write("</svg>\n")


def main():
    parser = argparse.ArgumentParser(
        description="Perform watershed segmentation and export to SVG"
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input image file (e.g., segment_scan.jpg)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output SVG file (default: input_name_segmented.svg)"
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=50,
        help="Minimum area threshold for segments (default: 50 pixels)"
    )
    
    args = parser.parse_args()
    
    # Setup paths
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_segmented.svg"
    
    print(f"Loading image: {input_path}")
    img_rgb, gray, (height, width) = load_image(input_path)
    
    print("Preprocessing image...")
    binary = preprocess_image(gray)
    
    print("Performing watershed segmentation...")
    labels = perform_watershed(binary)
    
    print("Extracting contours...")
    contours = extract_contours(labels, min_area=args.min_area)
    
    print(f"Found {len(contours)} segments")
    
    print(f"Exporting SVG to: {output_path}")
    export_svg(contours, width, height, output_path)
    
    print("Done!")
    print(f"\nOutput saved to: {output_path}")
    print(f"Total segments: {len(contours)}")


if __name__ == "__main__":
    main()
