#!/usr/bin/env python3
"""Garnet - GIMP + YOLO Segmentation Pipeline

Main entrypoint for the Garnet workflow that combines GIMP plugin
functionality with YOLO segmentation for automated analysis of
microscopic images.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional

import click

# Import local modules
import prepare_yolo
import yolo_labels_to_svg
import analyze


@click.group()
def cli():
    """Garnet - GIMP + YOLO Segmentation Pipeline
    
    A tool for detecting and measuring garnet splinters from microscopic images.
    """
    pass


@cli.command()
@click.option('--xcf-dir', default='.', help='Directory containing XCF files (default: current directory)')
def gimp_export(xcf_dir):
    """Export all XCF files to PNG layers and vectors using GIMP plugin.
    
    Calls GIMP's garnet-export-xcf action via Flatpak for all XCF files
    in the specified directory, creating a tree of exported layers and vectors.
    """
    xcf_dir = Path(xcf_dir).resolve()
    xcf_files = list(xcf_dir.glob('*.xcf'))
    
    if not xcf_files:
        click.echo(f"No XCF files found in {xcf_dir}")
        return
    
    click.echo(f"Found {len(xcf_files)} XCF file(s) to export")
    
    for xcf_file in xcf_files:
        click.echo(f"Exporting {xcf_file.name}...")
        
        # Create output directory named after the XCF file (without extension)
        output_dir = xcf_dir / xcf_file.stem
        output_dir.mkdir(exist_ok=True)
        
        # Build GIMP batch command
        batch_script = f'''
import gi
gi.require_version("Gimp","3.0")
from gi.repository import Gimp

img = Gimp.Image.new(1,1,Gimp.ImageBaseType.RGB)

proc = Gimp.get_pdb().lookup_procedure("garnet-export-xcf")
cfg = proc.create_config()
cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
cfg.set_property("image", img)
cfg.set_property("xcf-path", "{xcf_file}")
cfg.set_property("output-dir", "{output_dir}")
cfg.set_property("layer-name", "")
proc.run(cfg)
'''
        
        try:
            subprocess.run([
                'flatpak', 'run', 'org.gimp.GIMP',
                '-i', '--batch-interpreter=python-fu-eval',
                '-b', batch_script,
                '--quit'
            ], check=True, capture_output=True, text=True)
            click.echo(f"  ✓ Exported to {output_dir}")
        except subprocess.CalledProcessError as e:
            click.echo(f"  ✗ Error exporting {xcf_file.name}: {e}", err=True)
            if e.stderr:
                click.echo(f"    {e.stderr}", err=True)


@cli.command()
@click.option('--outdir', default='.', help='Output directory for YOLO dataset (default: current directory)')
@click.option('--class-name', default='rock', help='Class name for segmentation (default: rock)')
@click.option('--class-id', type=int, default=0, help='Class ID (default: 0)')
@click.option('--val-frac', type=float, default=0.2, help='Validation fraction (default: 0.2)')
@click.option('--seed', type=int, default=42, help='Random seed (default: 42)')
def yolo_prepare(outdir, class_name, class_id, val_frac, seed):
    """Prepare YOLO training dataset from exported images.
    
    Scans the current directory for exported image folders (containing image.png
    and image.txt) and creates a YOLO11-seg dataset structure.
    """
    click.echo("Preparing YOLO dataset...")
    
    # Save original sys.argv and replace with our arguments
    original_argv = sys.argv
    sys.argv = [
        'prepare_yolo.py',
        '--outdir', str(outdir),
        '--class-name', class_name,
        '--class-id', str(class_id),
        '--val-frac', str(val_frac),
        '--seed', str(seed)
    ]
    
    try:
        prepare_yolo.main()
        click.echo("✓ YOLO dataset prepared successfully")
    except Exception as e:
        click.echo(f"✗ Error preparing YOLO dataset: {e}", err=True)
        sys.exit(1)
    finally:
        sys.argv = original_argv


@cli.command()
@click.option('--model', default='yolo11n-seg.pt', help='YOLO model to use (default: yolo11n-seg.pt)')
@click.option('--epochs', type=int, default=100, help='Number of training epochs (default: 100)')
@click.option('--imgsz', type=int, default=640, help='Image size for training (default: 640)')
@click.option('--data', default='data.yaml', help='Path to data.yaml (default: data.yaml)')
@click.option('--project', default='.', help='Project directory (default: current directory)')
@click.option('--name', default='train', help='Experiment name (default: train)')
def yolo_train(model, epochs, imgsz, data, project, name):
    """Train YOLO11 segmentation model.
    
    Trains a neural network using the prepared YOLO dataset. The trained model
    is saved as trained.pt in the current directory.
    """
    click.echo(f"Training YOLO model with {epochs} epochs...")
    
    # Construct the yolo command
    cmd = [
        'yolo', 'segment', 'train',
        f'data={data}',
        f'model={model}',
        f'epochs={epochs}',
        f'imgsz={imgsz}',
        f'project={project}',
        f'name={name}'
    ]
    
    try:
        subprocess.run(cmd, check=True)
        
        # Copy the best model to trained.pt in current directory
        weights_path = Path(project) / name / 'weights' / 'best.pt'
        if weights_path.exists():
            import shutil
            shutil.copy2(weights_path, './trained.pt')
            click.echo(f"✓ Training complete. Model saved as ./trained.pt")
        else:
            click.echo(f"⚠ Training complete but best.pt not found at {weights_path}", err=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"✗ Error training model: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--model', default='trained.pt', help='Trained model path (default: trained.pt)')
@click.option('--data', default='data.yaml', help='Path to data.yaml (default: data.yaml)')
def yolo_val(model, data):
    """Validate trained YOLO model.
    
    Runs validation on the trained model using the validation dataset.
    """
    click.echo("Running YOLO validation...")
    
    cmd = [
        'yolo', 'segment', 'val',
        f'model={model}',
        f'data={data}'
    ]
    
    try:
        subprocess.run(cmd, check=True)
        click.echo("✓ Validation complete")
    except subprocess.CalledProcessError as e:
        click.echo(f"✗ Error during validation: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('source')
@click.option('--model', default='trained.pt', help='Trained model path (default: trained.pt)')
@click.option('--project', default='.', help='Project directory (default: current directory)')
def yolo_predict(source, model, project):
    """Run YOLO prediction on a new image.
    
    SOURCE: Path to the input image file (e.g., input123.png)
    
    Creates predictions in a directory named after the input file
    (e.g., ./input123/ for input123.png).
    """
    source_path = Path(source)
    if not source_path.exists():
        click.echo(f"✗ Source file not found: {source}", err=True)
        sys.exit(1)
    
    # Create output directory based on source filename (without extension)
    output_name = source_path.stem
    output_dir = Path(project) / output_name
    
    click.echo(f"Running YOLO prediction on {source}...")
    
    cmd = [
        'yolo', 'segment', 'predict',
        f'model={model}',
        f'source={source}',
        'save=True',
        'save_txt=True',
        f'project={project}',
        f'name={output_name}'
    ]
    
    try:
        subprocess.run(cmd, check=True)
        click.echo(f"✓ Prediction complete. Results in {output_dir}")
    except subprocess.CalledProcessError as e:
        click.echo(f"✗ Error during prediction: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('labels_dir')
@click.option('--images', default=None, help='Images directory (optional, defaults to labels/..)')
@click.option('--out', default=None, help='Output directory for SVG files (default: same as labels)')
@click.option('--tolerance', type=float, default=5.0, help='Simplification tolerance in pixels (default: 5.0)')
def yolo_to_svg(labels_dir, images, out, tolerance):
    """Convert YOLO prediction labels to SVG paths.
    
    LABELS_DIR: Directory containing YOLO label files (*.txt)
    
    Converts predicted YOLO labels to SVG format that can be imported
    into GIMP as paths.
    """
    click.echo(f"Converting YOLO labels to SVG...")
    
    # Use labels_dir as output if not specified
    if out is None:
        out = labels_dir
    
    # Save original sys.argv and replace with our arguments
    original_argv = sys.argv
    args = ['yolo_labels_to_svg.py', '--labels', str(labels_dir), '--out', str(out)]
    if images:
        args.extend(['--images', str(images)])
    args.extend(['--tolerance', str(tolerance)])
    sys.argv = args
    
    try:
        yolo_labels_to_svg.main()
        click.echo("✓ SVG files created successfully")
    except Exception as e:
        click.echo(f"✗ Error converting to SVG: {e}", err=True)
        sys.exit(1)
    finally:
        sys.argv = original_argv


@cli.command()
@click.argument('image_path')
@click.argument('svg_dir')
@click.option('--output', default=None, help='Output XCF path (default: <image_stem>.xcf)')
def gimp_create_xcf(image_path, svg_dir, output):
    """Create XCF file with image layer and SVG paths.
    
    IMAGE_PATH: Input image file
    SVG_DIR: Directory containing SVG files with paths
    
    Creates a new XCF file with the image as a layer and SVG paths imported
    as GIMP paths (not layers).
    """
    image_path = Path(image_path)
    svg_dir = Path(svg_dir)
    
    if not image_path.exists():
        click.echo(f"✗ Image file not found: {image_path}", err=True)
        sys.exit(1)
    
    if output is None:
        output = f"{image_path.stem}.xcf"
    
    output_path = Path(output)
    
    click.echo(f"Creating XCF file {output_path}...")
    
    # Find all SVG files in the directory
    svg_files = list(svg_dir.glob('*.svg'))
    if not svg_files:
        click.echo(f"⚠ Warning: No SVG files found in {svg_dir}")
    
    # Build GIMP batch script to create XCF
    svg_imports = ""
    for svg_file in svg_files:
        # Import each SVG as paths (not as layers)
        svg_imports += f'''
vectors_file = Gio.File.new_for_path("{svg_file}")
Gimp.get_pdb().lookup_procedure("gimp-path-import-from-file").run(
    Gimp.get_pdb().lookup_procedure("gimp-path-import-from-file").create_config().set_property("image", img).set_property("file", vectors_file).set_property("merge", False).set_property("scale", False)
)
'''
    
    batch_script = f'''
import gi
gi.require_version("Gimp","3.0")
from gi.repository import Gimp, Gio

# Load the image
img_file = Gio.File.new_for_path("{image_path}")
img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, img_file)

# Import SVG files as paths
{svg_imports}

# Save as XCF
xcf_file = Gio.File.new_for_path("{output_path.resolve()}")
Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, xcf_file, None)

print("XCF file created: {output_path}")
'''
    
    try:
        result = subprocess.run([
            'flatpak', 'run', 'org.gimp.GIMP',
            '-i', '--batch-interpreter=python-fu-eval',
            '-b', batch_script,
            '--quit'
        ], check=True, capture_output=True, text=True)
        if result.stdout:
            click.echo(result.stdout)
        click.echo(f"✓ XCF file created: {output_path}")
    except subprocess.CalledProcessError as e:
        click.echo(f"✗ Error creating XCF: {e}", err=True)
        if e.stderr:
            click.echo(f"  {e.stderr}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('image_path')
@click.option('--output', default=None, help='Output JSON path (default: <image_stem>.json)')
def get_scale(image_path, output):
    """Extract scale information from image.
    
    IMAGE_PATH: Input image file
    
    Analyzes the image to find scale bar and extract pixel-to-micrometer
    conversion, saving the result as JSON.
    """
    image_path = Path(image_path)
    
    if not image_path.exists():
        click.echo(f"✗ Image file not found: {image_path}", err=True)
        sys.exit(1)
    
    if output is None:
        output = f"{image_path.stem}.json"
    
    output_path = Path(output)
    
    click.echo(f"Analyzing scale from {image_path}...")
    
    try:
        import cv2
        img = cv2.imread(str(image_path))
        um_per_pixel = analyze.get_scale_info(img)
        
        # Calculate pixels per micrometer
        pixels_per_micrometer = 1.0 / um_per_pixel if um_per_pixel > 0 else 0
        
        # Create scale data matching garnet.py's save_scale format
        scale_data = {
            'pixels': 100,  # Reference value
            'micrometers': 100 * um_per_pixel,
            'pixels_per_micrometer': pixels_per_micrometer
        }
        
        with open(output_path, 'w') as f:
            json.dump(scale_data, f, indent=2)
        
        click.echo(f"✓ Scale info saved to {output_path}")
        click.echo(f"  Scale: {um_per_pixel:.4f} µm/pixel ({pixels_per_micrometer:.2f} pixels/µm)")
    except ValueError as e:
        click.echo(f"✗ Error getting scale: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('xcf_path')
@click.option('--export-png', is_flag=True, help='Also export final PNG from GIMP')
def gimp_compute_areas(xcf_path, export_png):
    """Compute areas for paths in XCF file using GIMP plugin.
    
    XCF_PATH: Path to the XCF file
    
    Calls GIMP's garnet-paths-areas action to compute and visualize
    areas of all paths in the XCF file.
    """
    xcf_path = Path(xcf_path)
    
    if not xcf_path.exists():
        click.echo(f"✗ XCF file not found: {xcf_path}", err=True)
        sys.exit(1)
    
    click.echo(f"Computing areas for {xcf_path}...")
    
    # Build GIMP batch script
    export_step = ""
    if export_png:
        png_path = xcf_path.with_suffix('.png')
        export_step = f'''
# Export as PNG
png_file = Gio.File.new_for_path("{png_path}")
Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, png_file, None)
print("Exported PNG: {png_path}")
'''
    
    batch_script = f'''
import gi
gi.require_version("Gimp","3.0")
from gi.repository import Gimp, Gio

# Load the XCF
xcf_file = Gio.File.new_for_path("{xcf_path}")
img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, xcf_file)

# Run garnet-paths-areas procedure
proc = Gimp.get_pdb().lookup_procedure("garnet-paths-areas")
cfg = proc.create_config()
cfg.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
cfg.set_property("image", img)
result = proc.run(cfg)

# Save the XCF with computed areas
Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, xcf_file, None)
print("XCF updated with area computations")

{export_step}
'''
    
    try:
        result = subprocess.run([
            'flatpak', 'run', 'org.gimp.GIMP',
            '-i', '--batch-interpreter=python-fu-eval',
            '-b', batch_script,
            '--quit'
        ], check=True, capture_output=True, text=True)
        if result.stdout:
            click.echo(result.stdout)
        click.echo(f"✓ Areas computed and XCF updated")
    except subprocess.CalledProcessError as e:
        click.echo(f"✗ Error computing areas: {e}", err=True)
        if e.stderr:
            click.echo(f"  {e.stderr}", err=True)
        sys.exit(1)


# Metacommands

@cli.command()
@click.option('--model', default='yolo11n-seg.pt', help='YOLO model to use (default: yolo11n-seg.pt)')
@click.option('--epochs', type=int, default=100, help='Number of training epochs (default: 100)')
@click.option('--imgsz', type=int, default=640, help='Image size for training (default: 640)')
@click.option('--class-name', default='rock', help='Class name for segmentation (default: rock)')
@click.option('--val-frac', type=float, default=0.2, help='Validation fraction (default: 0.2)')
def train(model, epochs, imgsz, class_name, val_frac):
    """Complete training workflow: export + prepare + train.
    
    Runs the complete training pipeline:
    1. Export XCF files to images and labels
    2. Prepare YOLO dataset
    3. Train YOLO model
    """
    click.echo("=" * 60)
    click.echo("GARNET TRAINING WORKFLOW")
    click.echo("=" * 60)
    
    # Step 1: Export XCF files
    click.echo("\n[1/3] Exporting XCF files...")
    ctx = click.get_current_context()
    ctx.invoke(gimp_export, xcf_dir='.')
    
    # Step 2: Prepare YOLO dataset
    click.echo("\n[2/3] Preparing YOLO dataset...")
    ctx.invoke(yolo_prepare, outdir='.', class_name=class_name, class_id=0, 
               val_frac=val_frac, seed=42)
    
    # Step 3: Train model
    click.echo("\n[3/3] Training YOLO model...")
    ctx.invoke(yolo_train, model=model, epochs=epochs, imgsz=imgsz, 
               data='data.yaml', project='.', name='train')
    
    click.echo("\n" + "=" * 60)
    click.echo("✓ TRAINING WORKFLOW COMPLETE")
    click.echo("=" * 60)


@cli.command()
@click.argument('source')
@click.option('--model', default='trained.pt', help='Trained model path (default: trained.pt)')
@click.option('--export-png', is_flag=True, help='Also export final PNG from GIMP')
def predict(source, model, export_png):
    """Complete prediction workflow for a new image.
    
    SOURCE: Path to the input image file
    
    Runs the complete prediction pipeline:
    1. Run YOLO prediction
    2. Convert predictions to SVG
    3. Create XCF with image and paths
    4. Extract scale information
    5. Compute areas in GIMP
    """
    source_path = Path(source)
    if not source_path.exists():
        click.echo(f"✗ Source file not found: {source}", err=True)
        sys.exit(1)
    
    output_name = source_path.stem
    output_dir = Path('.') / output_name
    
    click.echo("=" * 60)
    click.echo(f"GARNET PREDICTION WORKFLOW: {source}")
    click.echo("=" * 60)
    
    ctx = click.get_current_context()
    
    # Step 1: YOLO prediction
    click.echo("\n[1/5] Running YOLO prediction...")
    ctx.invoke(yolo_predict, source=str(source), model=model, project='.')
    
    # Find the labels directory created by YOLO
    labels_dir = output_dir / 'labels'
    if not labels_dir.exists():
        click.echo(f"✗ Labels directory not found: {labels_dir}", err=True)
        sys.exit(1)
    
    # Step 2: Convert to SVG
    click.echo("\n[2/5] Converting predictions to SVG...")
    ctx.invoke(yolo_to_svg, labels_dir=str(labels_dir), images=str(source_path.parent),
               out=str(output_dir), tolerance=5.0)
    
    # Step 3: Create XCF
    click.echo("\n[3/5] Creating XCF file...")
    xcf_output = f"{output_name}.xcf"
    ctx.invoke(gimp_create_xcf, image_path=str(source), svg_dir=str(output_dir),
               output=xcf_output)
    
    # Step 4: Get scale
    click.echo("\n[4/5] Extracting scale information...")
    json_output = f"{output_name}.json"
    try:
        ctx.invoke(get_scale, image_path=str(source), output=json_output)
    except Exception as e:
        click.echo(f"⚠ Warning: Could not extract scale automatically: {e}")
        click.echo("  You may need to set scale manually in GIMP")
    
    # Step 5: Compute areas
    click.echo("\n[5/5] Computing areas...")
    ctx.invoke(gimp_compute_areas, xcf_path=xcf_output, export_png=export_png)
    
    click.echo("\n" + "=" * 60)
    click.echo("✓ PREDICTION WORKFLOW COMPLETE")
    click.echo("=" * 60)
    click.echo(f"\nResults:")
    click.echo(f"  - Predictions: {output_dir}")
    click.echo(f"  - XCF file: {xcf_output}")
    click.echo(f"  - Scale info: {json_output}")
    if export_png:
        click.echo(f"  - Final PNG: {output_name}.png")


if __name__ == '__main__':
    cli()
