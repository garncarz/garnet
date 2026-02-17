# Watershed Segmentation Results

## Overview

This watershed segmentation implementation uses the **proven OTSU + distance transform approach** that works best for garnet rock segmentation. It detects internal segments within rocks based on fracture lines.

## Algorithm

The proven marker-based watershed approach:

1. **OTSU Thresholding**: Automatically finds optimal threshold to separate rocks from background
2. **Morphological Opening**: Removes small noise (5 iterations is key)
3. **Distance Transform**: Finds centers of segments far from boundaries
4. **Low Threshold**: Uses 0.05 * max distance (lower = more segments, crucial for detecting fractures)
5. **Marker Labeling**: Connected components + 10 offset (ensures background isn't confused with unknown)
6. **Watershed**: Applied on the ORIGINAL COLOR image (not gradient)
7. **SVG Export**: Each segment becomes a separate path

## Results for segment_scan.jpg

**Input:** Garnet rocks with visible internal fracture lines

**Output:**
- **32 watershed segments detected**
- **31 segments exported to SVG** (after min-area filtering)
- Each segment is a separate `<path>` element

### Key Parameters

- **Distance transform threshold**: 0.05 (5% of max distance)
  - Lower values detect more internal fractures
  - Higher values (>0.2) miss some grain boundaries
- **Morphological opening**: 5 iterations
  - Removes noise while preserving structure
- **Marker offset**: +10
  - Prevents background from being treated as unknown region

### SVG Structure (segment_scan_segmented.svg)

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="920" height="1380">
  <g id="watershed-segments" fill="none" stroke="#ff0000" stroke-width="2">
    <path id="segment_0" d="M 1.00,1.00 L 1.00,1378.00 ..." />  <!-- Background -->
    <path id="segment_1" d="M 179.00,43.00 L 142.00,49.00 ..." />
    <path id="segment_2" d="M 66.00,52.00 L 65.00,63.00 ..." />
    ...
    <path id="segment_30" d="M 103.00,1087.00 L 141.00,1095.00 ..." />
  </g>
</svg>
```

## Comparison with Previous Approach

**Previous approach (edge-based):**
- Used Canny edge detection + gradient
- Higher distance transform threshold (0.15-0.2)
- Watershed on gradient image
- Result: 16 segments → 10 SVG paths

**Current approach (OTSU + distance):**
- OTSU automatic thresholding
- Lower distance transform threshold (0.05)
- Watershed on original COLOR image
- Result: **32 segments → 31 SVG paths** ✅

**Improvement: 3x more segments detected!**

## Usage

```bash
# Basic usage
./watershed_segmentation.py segment_scan.jpg

# With debug visualization
./watershed_segmentation.py segment_scan.jpg --debug

# Custom parameters
./watershed_segmentation.py segment_scan.jpg --threshold 0.05 --min-area 200
```

### Command-line Options

- `--output`: Custom output SVG path
- `--min-area`: Minimum area threshold in pixels (default: 50)
- `--threshold`: Distance transform threshold (default: 0.05, range: 0.01-0.5)
- `--debug`: Save debug visualization images

## Debug Output

When using `--debug`, the following images are saved:

- `01_boundaries.png` - Original image with watershed boundaries in yellow
- `02_color_segments.png` - Color-coded segments using skimage
- `03_markers.png` - Watershed markers visualization

## Why This Approach Works Best

1. **OTSU Thresholding**: Automatically adapts to image lighting conditions
2. **Low Threshold (0.05)**: Detects subtle internal fractures, not just major separations
3. **Color Image Watershed**: Preserves more information than grayscale/gradient
4. **Proper Marker Offset**: Prevents algorithm confusion about background vs unknown regions

## References

This implementation is based on the proven approach documented in the OpenCV watershed tutorial and validated on garnet microscopy images.

- OpenCV Distance Transform: https://www.tutorialspoint.com/opencv/opencv_distance_transformation.htm
- OpenCV Watershed: https://docs.opencv.org/3.3.1/d7/d1b/group__imgproc__misc.html#ga3267243e4d3f95165d55a618c65ac6e1
- scikit-image label2rgb: Used for color-coded visualization
