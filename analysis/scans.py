"""Aggregate BIDS ``*_scans.tsv`` files into a per-dataset scanning table.

Each BIDS session ships a ``_scans.tsv`` listing every acquired file and its
``acq_time``. We concatenate them, tagging each row with its dataset, subject,
session and (per file) task/run, into ``output_data/scans/{dataset}.tsv`` — the
input to the scanning-timeline figures.
"""

from pathlib import Path

import pandas as pd
from bids.layout import parse_file_entities

from analysis.datalad_utils import datalad_get


def _read_scans(path, dataset):
    """Read one ``_scans.tsv`` into a tidy frame, or None if unreadable."""
    if not path.is_file():  # broken annex symlink → content not retrieved
        return None
    try:
        frame = pd.read_csv(path, sep="\t")
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return None
    if frame.empty:
        return None

    session_entities = parse_file_entities(str(path))
    frame["dataset"] = dataset
    frame["subject"] = session_entities.get("subject")
    frame["session"] = session_entities.get("session")
    if "acq_time" in frame.columns:
        frame["acq_time"] = pd.to_datetime(frame["acq_time"], errors="coerce")
    if "filename" in frame.columns:
        file_entities = frame["filename"].map(lambda name: parse_file_entities(str(name)))
        frame["task"] = file_entities.map(lambda ents: ents.get("task"))
        frame["run"] = file_entities.map(lambda ents: ents.get("run"))
    return frame


def aggregate_scans(dataset, cneuromod_dir, output_dir, smoke=False):
    """Write one aggregated scans TSV for ``dataset``; return the output path."""
    root = Path(cneuromod_dir)
    bids_dir = root / dataset / "bids"

    datalad_get(f"{dataset}/bids", root, recursive=True, get_content=False)
    scans_files = sorted(bids_dir.rglob("*_scans.tsv"))
    if smoke:
        scans_files = scans_files[:1]
    if scans_files:
        datalad_get([p.relative_to(root) for p in scans_files], root)

    frames = [frame for p in scans_files if (frame := _read_scans(p, dataset)) is not None]
    table = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    output_path = Path(output_dir) / "scans" / f"{dataset}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_path, sep="\t", index=False)
    print(f"✅ {dataset}: {len(table)} scan entr(ies) → {output_path}")
    return output_path
