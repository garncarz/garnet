# Watershed Segmentation

This directory contains tools for performing watershed segmentation on images and exporting the results as SVG files.

## Overview

Watershed segmentation is a powerful image processing technique that treats the grayscale image as a topographic surface and segments it into distinct regions. This implementation provides both a command-line script and a Jupyter notebook for performing watershed segmentation and exporting results as SVG paths.

## Files

- `watershed_segmentation.py` - Command-line script for watershed segmentation
- `watershed_segmentation.ipynb` - Jupyter notebook with detailed explanations and visualizations
- `segment_scan.jpg` - Sample input image
- `segment_scan_segmented.svg` - Sample output SVG file

## Usage

### Command-Line Script

Basic usage:
```bash
./watershed_segmentation.py segment_scan.jpg
```

This will create `segment_scan_segmented.svg` with all detected segments as separate paths.

#### Options

```bash
./watershed_segmentation.py input_image.jpg --output custom_output.svg --min-area 100
```

- `--output`: Specify custom output SVG path (default: `{input_name}_segmented.svg`)
- `--min-area`: Minimum area threshold in pixels for filtering small segments (default: 50)

#### Examples

```bash
# Basic usage with default settings
./watershed_segmentation.py segment_scan.jpg

# Custom output path
./watershed_segmentation.py segment_scan.jpg --output results/output.svg

# Filter out very small segments
./watershed_segmentation.py segment_scan.jpg --min-area 200
```

### Jupyter Notebook

For a more interactive experience with visualizations of each step:

```bash
jupyter notebook watershed_segmentation.ipynb
```

The notebook includes:
- Step-by-step visualization of the segmentation process
- Intermediate results (distance transform, foreground/background detection)
- Visual comparison of segments detected
- Detailed explanations of each algorithm step

## Algorithm Details

The watershed segmentation pipeline consists of:

1. **Preprocessing**:
   - Bilateral filtering to reduce noise while preserving edges
   - Adaptive thresholding to handle varying illumination
   - Morphological opening to remove small noise

2. **Watershed Segmentation**:
   - Distance transform to identify object centers
   - Marker-based watershed to segment regions
   - Connected components analysis

3. **Contour Extraction**:
   - Extract contours from each segment
   - Simplify contours using Douglas-Peucker algorithm
   - Filter segments by minimum area

4. **SVG Export**:
   - Convert each contour to SVG path format
   - Create separate path elements for each segment
   - Preserve image dimensions in SVG viewBox

## Output Format

The output SVG file contains:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="920" height="1380" viewBox="0 0 920 1380">
  <g id="watershed-segments" fill="none" stroke="#ff0000" stroke-width="2">
    <path id="segment_0" d="M 322.00,179.00 L 318.00,179.00 L ... Z" />
    <path id="segment_1" d="M 447.00,179.00 L 353.00,197.00 L ... Z" />
    ...
  </g>
</svg>
```

Each `<path>` element represents a separate segment and can be:
- Imported into vector graphics software (Inkscape, Adobe Illustrator, GIMP)
- Styled individually with CSS
- Manipulated programmatically

## Requirements

The script requires the following Python packages (already in `requirements.txt`):
- numpy
- opencv-python
- scipy
- scikit-image

## Integration with Garnet

This watershed segmentation tool complements the existing YOLO-based segmentation pipeline in Garnet:

- **YOLO segmentation**: Trained deep learning model for specific object classes
- **Watershed segmentation**: General-purpose algorithm for any image with distinct regions

Both produce SVG outputs that can be imported into GIMP and further processed with the Garnet plugin.

## Troubleshooting

### No segments detected
- Adjust the `--min-area` threshold (try lower values like 20)
- Check that the input image has sufficient contrast
- Verify that objects are not too close together

### Too many small segments
- Increase the `--min-area` threshold
- The default value of 50 pixels works well for most images

### Segments not following object boundaries
- The algorithm works best with images that have clear boundaries
- Try preprocessing the image externally (adjust contrast, sharpen edges)
- For specific object types, consider training a YOLO model instead

## References

- OpenCV Watershed documentation: https://docs.opencv.org/master/d3/db4/tutorial_py_watershed.html
- scikit-image segmentation: https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_watershed.html
