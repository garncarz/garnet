#!/usr/bin/env python3
"""
Watershed Segmentation for Image Processing

This script performs TRUE watershed segmentation on an input image, detecting
internal fracture lines within objects and exporting each distinct segment
as a separate SVG path.

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


def detect_edges(gray):
    """
    Detect edges/fracture lines in the image.
    This is crucial for watershed to find internal segments.
    """
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Use Canny edge detection to find fracture lines
    edges = cv2.Canny(blurred, 30, 100)
    
    # Dilate edges slightly to make them more prominent
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    return edges


def perform_watershed(gray, edges):
    """
    Perform TRUE watershed segmentation using marker-based approach.
    
    The strategy:
    1. Detect fracture lines (edges)
    2. Find regions between fractures (segment seeds)
    3. Use watershed to fill from seeds, stopped by fractures
    
    Returns:
        labels: Array where each unique value represents a different segment
    """
    # Step 1: Identify objects (rocks)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Clean up
    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # Step 2: Create elevation map where fractures are peaks
    # Invert the image so dark regions (fractures) become high elevations
    elevation = cv2.bitwise_not(gray)
    
    # Enhance fractures in the elevation map
    # Add edge information
    elevation = cv2.add(elevation, edges)
    
    # Apply only within objects
    elevation = cv2.bitwise_and(elevation, elevation, mask=binary)
    
    # Step 3: Find markers (segment seeds)
    # These are local minima in the elevation map (centers of segments)
    
    # Morphological opening removes peaks/fractures, leaving segment centers
    opened = cv2.morphologyEx(elevation, cv2.MORPH_OPEN, kernel, iterations=3)
    
    # Distance transform on the opened image
    dist = cv2.distanceTransform(opened, cv2.DIST_L2, 5)
    
    # Threshold to find sure foreground markers
    # Lower threshold = more segments
    dist_max = dist.max()
    if dist_max > 0:
        _, markers = cv2.threshold(dist, 0.15 * dist_max, 255, 0)
        markers = np.uint8(markers)
    else:
        markers = np.zeros_like(dist, dtype=np.uint8)
    
    # Label connected components
    n_labels, labels = cv2.connectedComponents(markers)
    
    print(f"  Found {n_labels - 1} initial segment seeds")
    
    if n_labels <= 1:
        # No markers found, return empty
        return np.ones_like(gray, dtype=np.int32)
    
    # Markers need to start from 1 (0 is unknown)
    labels = labels + 1
    
    # Mark background as 0
    labels[binary == 0] = 0
    
    # Step 4: Apply watershed
    elevation_3ch = cv2.cvtColor(elevation, cv2.COLOR_GRAY2BGR)
    labels = cv2.watershed(elevation_3ch, labels)
    
    return labels


def extract_contours(labels, min_area=50):
    """
    Extract contours from watershed-segmented labels.
    Each segment within a rock gets its own contour.
    
    Args:
        labels: Watershed labels array
        min_area: Minimum area threshold to filter small segments
    
    Returns:
        List of contours (each contour is a list of (x, y) points)
    """
    contours_list = []
    
    # Get unique labels (excluding background 1 and boundary -1)
    unique_labels = np.unique(labels)
    unique_labels = unique_labels[(unique_labels > 1)]
    
    print(f"Found {len(unique_labels)} watershed segments")
    
    for label in unique_labels:
        # Create binary mask for this segment
        mask = np.uint8(labels == label) * 255
        
        # Find contours for this segment
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            # Calculate area and filter small regions
            area = cv2.contourArea(contour)
            if area >= min_area:
                # Simplify contour to reduce points
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
        description="Perform TRUE watershed segmentation to detect internal segments within objects"
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
    img_rgb, gray, (height, width) = load_image(input_path)
    
    print("Detecting edges and fracture lines...")
    edges = detect_edges(gray)
    
    print("Performing watershed segmentation...")
    labels = perform_watershed(gray, edges)
    
    if args.debug:
        # Save debug visualizations
        debug_dir = input_path.parent / f"{input_path.stem}_debug"
        debug_dir.mkdir(exist_ok=True)
        
        # Recompute some intermediate values for visualization
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient = np.sqrt(grad_x**2 + grad_y**2)
        gradient = cv2.convertScaleAbs(gradient)
        
        # Save edges
        cv2.imwrite(str(debug_dir / "01_edges.png"), edges)
        
        # Save gradient
        cv2.imwrite(str(debug_dir / "02_gradient.png"), gradient)
        
        # Save labeled regions with different colors
        label_overlay = np.zeros_like(img_rgb)
        unique_labels = np.unique(labels)
        unique_labels = unique_labels[unique_labels > 1]
        
        import matplotlib.pyplot as plt
        if len(unique_labels) > 0:
            colors = plt.cm.rainbow(np.linspace(0, 1, len(unique_labels)))
            
            for idx, label in enumerate(unique_labels):
                mask = labels == label
                label_overlay[mask] = (np.array(colors[idx][:3]) * 255).astype(np.uint8)
        
        # Blend with original
        blended = cv2.addWeighted(img_rgb, 0.4, label_overlay, 0.6, 0)
        cv2.imwrite(str(debug_dir / "03_segments_overlay.png"), cv2.cvtColor(blended, cv2.COLOR_RGB2BGR))
        
        # Save boundaries (watershed lines)
        boundary_img = img_rgb.copy()
        boundary_img[labels == -1] = [255, 0, 0]
        cv2.imwrite(str(debug_dir / "04_boundaries.png"), cv2.cvtColor(boundary_img, cv2.COLOR_RGB2BGR))
        
        # Save just the segments colored
        segment_img = label_overlay.copy()
        cv2.imwrite(str(debug_dir / "05_segments_only.png"), cv2.cvtColor(segment_img, cv2.COLOR_RGB2BGR))
        
        print(f"Debug images saved to: {debug_dir}")
        print(f"  - 01_edges.png: Detected edges/fractures")
        print(f"  - 02_gradient.png: Gradient magnitude")
        print(f"  - 03_segments_overlay.png: Segments overlaid on original")
        print(f"  - 04_boundaries.png: Watershed boundary lines")
        print(f"  - 05_segments_only.png: Just the colored segments")
    
    print("Extracting contours...")
    contours = extract_contours(labels, min_area=args.min_area)
    
    print(f"Found {len(contours)} distinct segments")
    
    print(f"Exporting SVG to: {output_path}")
    export_svg(contours, width, height, output_path)
    
    print("Done!")
    print(f"\nOutput saved to: {output_path}")
    print(f"Total segments: {len(contours)}")


if __name__ == "__main__":
    main()
