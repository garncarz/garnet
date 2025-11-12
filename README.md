# Garnet GIMP Plugin + YOLO Segmentation Pipeline

The goal of this project is to be able to find small splinters of garnet rock from microscopic pictures
and to measure their areas.

## Features
- Set scale from selection (stores pixel ↔ micrometer scale).
- Compute path (vector) areas (uses scale if set).
- Export layer + each Path as:
  - image.png (chosen or first layer)
  - mask_*.png (raster masks per Path)
  - image.txt (YOLO polygon segmentation labels derived directly from Paths)
- Dataset assembler (`prepare_yolo.py`) builds YOLO11 segmentation dataset structure.

## Installation (GIMP 3)
1. Ensure GIMP 3 (Flatpak or native) is installed.
2. Place plugin files in:
   ```
   ~/.config/GIMP/3.0/plug-ins/garnet/
   ```
3. Flatpak: grant filesystem access if needed:
   ```
   flatpak override --user org.gimp.GIMP --filesystem=home
   ```
4. Start GIMP. Menu path:
   ```
   Filters → Garnet → (tools)
   ```

## Export (GUI)
1. Open an XCF.
2. Filters → Garnet → Export XCF to PNGs.
3. (Optional) choose output directory (empty = current working directory).
4. (Optional) enter layer name (empty = first layer).
5. Output:
   ```
   image.png
   image.txt         (YOLO polygons)
   mask_0.png ...
   ```

## YOLO Dataset Assembly
From a directory containing multiple exported folders:
```
exports/
  rock1/image.png image.txt mask_0.png ...
  rock2/...
  rock3/...
```
Run:
```
cd exports
python3 prepare_yolo.py --outdir ~/datasets/garnet_yolo --class-name rock --class-id 0 --val-frac 0.2
```
Result:
```
garnet_yolo/
  images/train/*.png
  images/val/*.png
  labels/train/*.txt
  labels/val/*.txt
  data.yaml
```

## Train YOLO11 Segmentation
Install dependencies:
```
pip install ultralytics
```
Train:
```
cd ~/datasets/garnet_yolo
yolo segment train data=data.yaml model=yolo11n-seg.pt epochs=100 imgsz=640
```
Validate (later):
```
yolo segment val model=~/runs/segment/train/weights/best.pt data=data.yaml
```
Predict:
```
yolo segment predict model=~/runs/segment/train/weights/best.pt source=images/val
```

## Label Format
`image.txt` lines:
```
<class_id> x1 y1 x2 y2 ... (normalized polygon vertices, ≥3 points)
```
All Paths exported as class 0 (extend later if needed).

## Troubleshooting
- No menu entry: ensure file is executable and no syntax errors (check GIMP console messages).
- Flatpak cannot read files: add overrides (`flatpak override ...`).
- Very low validation metrics: increase dataset size; ensure multiple val images; raise `imgsz` (e.g. 1024) for many small objects.

## Requirements
- GIMP 3.x (Python plug‑ins enabled)
- Python 3.10+
- For training: `ultralytics`, `torch` (GPU recommended)
