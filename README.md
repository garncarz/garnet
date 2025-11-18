# Garnet - GIMP + YOLO Segmentation Pipeline

Automated detection and measurement of garnet splinters from microscopic images using GIMP and YOLO11 segmentation.

## Overview

Garnet combines GIMP's vector path capabilities with YOLO11 deep learning to:
1. **Train** a segmentation model from manually labeled XCF files
2. **Predict** and measure garnet splinters in new microscopic images
3. **Measure** areas automatically with pixel-to-micrometer scale extraction

## Quick Start

### Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install GIMP 3 (Flatpak recommended):**
   ```bash
   flatpak install flathub org.gimp.GIMP
   flatpak override --user org.gimp.GIMP --filesystem=home
   ```

3. **Install GIMP plugin:**
   ```bash
   mkdir -p ~/.config/GIMP/3.0/plug-ins/garnet/
   cp garnet.py ~/.config/GIMP/3.0/plug-ins/garnet/
   chmod +x ~/.config/GIMP/3.0/plug-ins/garnet/garnet.py
   ```

### Training Workflow

Train a model from labeled XCF files in your project directory:

```bash
# Train from XCF files with labeled paths
./app.py train --epochs 100

# Or run steps individually:
./app.py gimp-export          # Export XCF → images + labels
./app.py yolo-prepare         # Prepare YOLO dataset
./app.py yolo-train           # Train model → trained.pt
```

**Training project structure:**
```
project/
├── sample1.xcf              # XCF files with manually drawn paths
├── sample2.xcf
├── sample1/                 # Auto-created: exported data
│   ├── image.png
│   ├── image.txt            # YOLO labels from paths
│   └── mask_*.png
├── images/                  # Auto-created: YOLO dataset
│   ├── train/*.png
│   └── val/*.png
├── labels/
│   ├── train/*.txt
│   └── val/*.txt
├── data.yaml
└── trained.pt              # Final trained model
```

### Prediction Workflow

Analyze a new microscopic image:

```bash
# Complete prediction pipeline
./app.py predict input123.png --export-png

# Or run steps individually:
./app.py yolo-predict input123.png        # Predict → input123/
./app.py yolo-to-svg input123/labels/     # Convert to SVG
./app.py gimp-create-xcf input123.png input123/  # Create XCF
./app.py get-scale input123.png           # Extract scale → input123.json
./app.py gimp-compute-areas input123.xcf  # Measure areas
```

**Prediction output structure:**
```
./
├── input123.png            # Original input
├── input123/               # YOLO predictions
│   ├── labels/*.txt        # YOLO label files
│   └── *.svg               # SVG paths (from labels)
├── input123.xcf            # XCF with image + predicted paths
├── input123.json           # Scale information
└── input123.png            # Final annotated image (if --export-png)
```

## Available Commands

### Individual Commands

- `gimp-export` - Export XCF files to images and YOLO labels
- `yolo-prepare` - Assemble YOLO dataset from exported images
- `yolo-train` - Train YOLO11 segmentation model
- `yolo-val` - Validate trained model
- `yolo-predict` - Run prediction on new image
- `yolo-to-svg` - Convert YOLO labels to SVG paths
- `gimp-create-xcf` - Create XCF from image + SVG paths
- `get-scale` - Extract scale from image (OCR scale bar)
- `gimp-compute-areas` - Compute and visualize path areas

### Metacommands

- `train` - Complete training workflow (export + prepare + train)
- `predict` - Complete prediction workflow (predict + svg + xcf + scale + areas)

## GIMP Plugin Features

When using GIMP interactively (`Filters → Garnet`):

- **Set Scale from Selection** - Define pixel ↔ micrometer conversion
- **Export XCF to PNGs** - Export layers and paths to images/labels
- **Compute Path Areas** - Measure and visualize path areas with colored overlays

## Label Format

YOLO segmentation labels (`image.txt`):
```
<class_id> x1 y1 x2 y2 ... (normalized polygon vertices, ≥3 points)
```

All objects use class 0 by default (extend if needed for multiple classes).

## Requirements

- Python 3.10+
- GIMP 3.x (with Python plug-ins enabled)
- For training: GPU recommended (CPU training is slow)

See `requirements.txt` for Python dependencies.

## Troubleshooting

- **No GIMP menu entry:** Ensure plugin is executable and in correct directory
- **Flatpak permission errors:** Run `flatpak override --user org.gimp.GIMP --filesystem=home`
- **Low validation metrics:** Increase dataset size, ensure diverse validation images, try larger `--imgsz` (e.g., 1024)
- **Scale extraction fails:** Scale bar must be visible and readable; set manually in GIMP if needed

