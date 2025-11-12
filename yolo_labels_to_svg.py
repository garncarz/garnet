#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image

def parse_yolo_seg_line(line, w, h):
    parts = line.strip().split()
    if len(parts) < 7:  # cls + at least 3 points (6 nums)
        return None, []
    cls = int(float(parts[0]))
    nums = [float(x) for x in parts[1:]]
    if len(nums) % 2 != 0:
        return None, []
    pts = []
    for i in range(0, len(nums), 2):
        x = nums[i] * w
        y = nums[i + 1] * h
        pts.append((x, y))
    return cls, pts

def path_d_from_points(pts):
    # SVG path: M x0,y0 L x1,y1 ... Z
    if not pts:
        return ""
    segs = [f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"]
    for x, y in pts[1:]:
        segs.append(f"L {x:.2f},{y:.2f}")
    segs.append("Z")
    return " ".join(segs)

def labels_to_svg(img_path: Path, lbl_path: Path, out_path: Path):
    with Image.open(img_path) as im:
        w, h = im.size

    paths = []
    classes = []
    for line in lbl_path.read_text().splitlines():
        cls, pts = parse_yolo_seg_line(line, w, h)
        if cls is None or len(pts) < 3:
            continue
        d = path_d_from_points(pts)
        if d:
            paths.append(d)
            classes.append(cls)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n')
        f.write('  <g id="yolo-paths" fill="none" stroke="#ff0000" stroke-width="1">\n')
        for i, d in enumerate(paths):
            cls = classes[i]
            f.write(f'    <path id="cls{cls}_{i}" d="{d}" />\n')
        f.write("  </g>\n</svg>\n")

def find_image_for_stem(stem, search_dirs):
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
    for d in search_dirs:
        for ext in exts:
            p = d / f"{stem}{ext}"
            if p.exists():
                return p
    return None

def main():
    ap = argparse.ArgumentParser(description="Convert YOLO seg labels to SVG Paths (importable as GIMP Paths)")
    ap.add_argument("--labels", default="", help="Dir with labels/*.txt (default: CWD)")
    ap.add_argument("--images", default="", help="Dir with images (optional; defaults to labels/..)")
    ap.add_argument("--out", default="", help="Output dir for SVGs (default: CWD)")
    args = ap.parse_args()

    lbl_dir = Path(args.labels) if args.labels else Path.cwd()
    out_dir = Path(args.out) if args.out else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    search_dirs = []
    if args.images:
        search_dirs.append(Path(args.images))
    parent = lbl_dir.parent
    if parent not in search_dirs:
        search_dirs.append(parent)

    any_labels = False
    for lbl in sorted(lbl_dir.glob("*.txt")):
        any_labels = True
        stem = lbl.stem
        img = find_image_for_stem(stem, search_dirs)
        if not img:
            print(f"Skip {lbl} (no matching image in: {', '.join(str(d) for d in search_dirs)})")
            continue
        out_svg = out_dir / f"{stem}.svg"
        labels_to_svg(img, lbl, out_svg)
        print(f"Wrote {out_svg}")
    if not any_labels:
        print(f"No label files (*.txt) found in {lbl_dir}")

if __name__ == "__main__":
    main()