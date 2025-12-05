#!/usr/bin/env bash
#PBS -N garnet_segmentation
#PBS -l select=1:ncpus=1:ngpus=1:mem=32gb:scratch_local=10gb
#PBS -l walltime=24:00:00
# ^^^ select = number of machines, walltime = max time

# As a preparation, run this on the frontend:
# module add python
# python -m venv .venv
# source .venv/bin/activate
# pip install -r requirements.txt

export SRC_DIR=/storage/brno2/home/$(whoami)/git/garnet
export VENV_DIR=$SRC_DIR/.venv
export DATA_DIR=$SRC_DIR/data

module add python
source $VENV_DIR/bin/activate

echo "$PBS_JOBID is running on node `hostname -f` in a scratch directory $SCRATCHDIR" >> $SRC_DIR/jobs_info.txt

test -n "$SCRATCHDIR" || { echo >&2 "Variable SCRATCHDIR is not set"; exit 1; }

rsync -av \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.log' \
    --exclude='garnet_segmentation.e*' \
    --exclude='garnet_segmentation.o*' \
    --exclude='*.zip' \
    $DATA_DIR/ $SCRATCHDIR/ || { echo >&2 "Error while copying input files (code $?)"; exit 2; }

cd $SCRATCHDIR

$SRC_DIR/app.py yolo-train --model=yolo11x-seg.pt --epochs=300 --imgsz=1280 || { echo >&2 "Training erred (code $?)"; exit 5; }

rsync -av $SCRATCHDIR/ $DATA_DIR/ || { echo >&2 "Result files copying failed (code $?)"; exit 6; }
clean_scratch
