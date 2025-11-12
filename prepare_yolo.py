#!/usr/bin/env python3
import os, shutil, random
from pathlib import Path
import yaml
import argparse

def gather_sources(root: Path):
    items = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        img = d / "image.png"
        lab = d / "image.txt"
        if img.exists() and lab.exists():
            items.append((d.name, img, lab))
    return items

def build(outdir: Path, sources, val_frac=0.2, seed=42):
    img_tr = outdir / "images" / "train"
    img_val = outdir / "images" / "val"
    lab_tr = outdir / "labels" / "train"
    lab_val = outdir / "labels" / "val"
    for p in (img_tr, img_val, lab_tr, lab_val):
        p.mkdir(parents=True, exist_ok=True)

    random.Random(seed).shuffle(sources)
    split = int((1 - val_frac) * len(sources))
    train = sources[:split]
    val = sources[split:]

    def place(batch, img_dst, lab_dst):
        for stem, img, lab in batch:
            shutil.copy2(img, img_dst / f"{stem}.png")
            shutil.copy2(lab, lab_dst / f"{stem}.txt")

    place(train, img_tr, lab_tr)
    place(val, img_val, lab_val)
    return len(train), len(val)

def write_yaml(outdir: Path, class_name: str, class_id: int):
    data = {
        "path": str(outdir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {int(class_id): str(class_name)}
    }
    (outdir / "data.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=".", help="Output dataset root (default: current working directory)")
    ap.add_argument("--class-name", default="rock")
    ap.add_argument("--class-id", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cwd = Path(".").resolve()
    sources = gather_sources(cwd)
    if not sources:
        print("No export dirs found (need image.png + image.txt).")
        return

    outdir = Path(args.outdir or ".")
    n_tr, n_val = build(outdir, sources, args.val_frac, args.seed)
    write_yaml(outdir, args.class_name, args.class_id)
    print(f"Dataset: {outdir.resolve()}")
    print(f"Train: {n_tr}  Val: {n_val}")
    print("Done.")

if __name__ == "__main__":
    main()