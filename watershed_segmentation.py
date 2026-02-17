#!/usr/bin/env python3
"""
Watershed Segmentation for Garnet Rocks

This script performs watershed segmentation using OTSU thresholding and distance
transform to detect internal segments within garnet rocks. Based on the proven
approach that works best for this type of imagery.

Usage:
    ./watershed_segmentation.py input_image.jpg [--output output.svg]
"""

import argparse
from pathlib import Path
import numpy as np
import cv2
from skimage import color


def perform_watershed(img_path: Path):
    """
    Perform watershed segmentation using the proven OTSU + distance transform approach.
    
    This is the approach that has been validated to work best for garnet segmentation.
    
    Returns:
        img_bgr: Original image with boundaries marked
        markers: Watershed segmentation labels
        img_color: Color-coded segmentation result
    """
    # Load image
    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        raise ValueError(f"Could not load image: {img_path}")
    
    # Convert to grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # OTSU thresholding - automatically finds optimal threshold
    ret1, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Morphological opening to remove small noise (5 iterations is key)
    kernel = np.ones((3, 3), np.uint8)
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=5)
    
    # Sure background area - dilate to expand boundaries
    sure_bg = cv2.dilate(opening, kernel, iterations=2)
    
    # Sure foreground area using distance transform
    # This is the key step - distance from boundaries
    dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 3)
    
    # Threshold at 5% of max distance (lower = more segments, key parameter!)
    # 0.05 works well for detecting internal fractures
    ret2, sure_fg = cv2.threshold(dist_transform, 0.05 * dist_transform.max(), 255, 0)
    sure_fg = np.uint8(sure_fg)
    
    # Unknown region = background - foreground
    unknown = cv2.subtract(sure_bg, sure_fg)
    
    # Label markers using connected components
    ret3, markers = cv2.connectedComponents(sure_fg)
    
    # Add 10 to all labels so background is not 0
    # This ensures watershed doesn't treat background as unknown
    markers = markers + 10
    
    # Mark unknown region as 0
    markers[unknown == 255] = 0
    
    # Apply watershed on the ORIGINAL COLOR image (important!)
    markers = cv2.watershed(img_bgr, markers)
    
    # Mark boundaries in yellow
    img_bgr[markers == -1] = [0, 255, 255]
    
    # Create color-coded result
    img_color = color.label2rgb(markers, bg_label=0)
    
    print(f"  Found {len(np.unique(markers)) - 2} segments (excluding background and boundaries)")
    print(f"  Distance transform max: {dist_transform.max():.2f}")
    print(f"  Threshold used: {0.05 * dist_transform.max():.2f}")
    
    return img_bgr, markers, img_color


def extract_contours(markers, min_area=50):
    """
    Extract contours from watershed markers.
    
    Args:
        markers: Watershed labels array
        min_area: Minimum area threshold to filter small segments
    
    Returns:
        List of contours (each contour is a list of (x, y) points)
    """
    contours_list = []
    
    # Get unique labels (excluding background 10 and boundary -1)
    unique_labels = np.unique(markers)
    unique_labels = unique_labels[(unique_labels > 10) & (unique_labels != -1)]
    
    print(f"  Extracting contours for {len(unique_labels)} segments")
    
    for label in unique_labels:
        # Create binary mask for this segment
        mask = np.uint8(markers == label) * 255
        
        # Find contours for this segment
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            # Calculate area and filter small regions
            area = cv2.contourArea(contour)
            if area >= min_area:
                # Simplify contour to reduce points
                # Using 0.01 for more aggressive simplification to reduce SVG size
                epsilon = 0.01 * cv2.arcLength(contour, True)
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
        description="Perform watershed segmentation using proven OTSU + distance transform approach"
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
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Distance transform threshold (default: 0.05, lower = more segments)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save debug visualization images"
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
    
    # Perform watershed segmentation
    print("Performing watershed segmentation (OTSU + distance transform)...")
    img_with_boundaries, markers, img_color = perform_watershed(input_path)
    
    # Get image dimensions
    height, width = markers.shape
    
    if args.debug:
        # Save debug visualizations
        debug_dir = input_path.parent / f"{input_path.stem}_debug"
        debug_dir.mkdir(exist_ok=True)
        
        # Save boundaries
        cv2.imwrite(str(debug_dir / "01_boundaries.png"), img_with_boundaries)
        
        # Save color-coded segments
        img_color_bgr = (img_color * 255).astype(np.uint8)
        img_color_bgr = cv2.cvtColor(img_color_bgr, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(debug_dir / "02_color_segments.png"), img_color_bgr)
        
        # Save markers visualization
        markers_vis = np.uint8((markers - markers.min()) / (markers.max() - markers.min()) * 255)
        cv2.imwrite(str(debug_dir / "03_markers.png"), markers_vis)
        
        print(f"Debug images saved to: {debug_dir}")
        print(f"  - 01_boundaries.png: Image with watershed boundaries in yellow")
        print(f"  - 02_color_segments.png: Color-coded segments")
        print(f"  - 03_markers.png: Watershed markers visualization")
    
    print("Extracting contours...")
    contours = extract_contours(markers, min_area=args.min_area)
    
    print(f"Found {len(contours)} distinct segments (after area filtering)")
    
    print(f"Exporting SVG to: {output_path}")
    export_svg(contours, width, height, output_path)
    
    print("Done!")
    print(f"\nOutput saved to: {output_path}")
    print(f"Total segments exported: {len(contours)}")


if __name__ == "__main__":
    main()
