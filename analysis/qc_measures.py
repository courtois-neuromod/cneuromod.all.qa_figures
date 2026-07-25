"""Extract per-run QC metrics from MRIQC BOLD reports in cneuromod.all.

MRIQC writes one small JSON of image-quality metrics (IQMs) per functional run.
We read only those JSONs — never the preprocessed ``.nii.gz`` — so the data
footprint stays tiny. One tidy TSV per dataset is written to
``output_data/qc_measures/{dataset}.tsv``, one row per run.
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from bids.layout import parse_file_entities

from analysis.datalad_utils import datalad_get

# Curated MRIQC BOLD IQMs to surface (missing keys become NaN). See
# https://mriqc.readthedocs.io/ for the full list of image-quality metrics.
IQM_KEYS = [
    "fd_mean", "fd_num", "fd_perc",   # motion
    "tsnr", "snr",                     # signal-to-noise
    "gsr_x", "gsr_y",                  # ghost-to-signal
    "dvars_std", "dvars_vstd",         # temporal derivative variance
    "aor", "aqi", "gcor", "size_t",    # artifacts / n volumes
]


def _task_grouped(task):
    """Strip a trailing run/segment index so e.g. 'life1'/'life2' group as 'life'."""
    if not task:
        return task
    return re.sub(r"\d+[abcd]?$", "", task)


def _row_from_json(path, dataset):
    """One tidy row (entities + IQMs) from a single MRIQC BOLD JSON, or None."""
    if not path.is_file():  # broken annex symlink → content not retrieved
        return None
    try:
        with open(path) as handle:
            iqms = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    entities = parse_file_entities(str(path))
    task = entities.get("task")
    row = {
        "dataset": dataset,
        "subject": entities.get("subject"),
        "session": entities.get("session"),
        "task": task,
        "run": entities.get("run"),
        "task_grouped": _task_grouped(task),
    }
    row.update({key: iqms.get(key, np.nan) for key in IQM_KEYS})
    return row


def extract_qc_measures(dataset, cneuromod_dir, output_dir, smoke=False):
    """Write one QC-metrics TSV for ``dataset``; return the output path."""
    root = Path(cneuromod_dir)
    mriqc_dir = root / dataset / "mriqc"

    # The mriqc submodule is initialized by the caller (run_qc_measures task)
    # before we glob it. Here we only fetch the small per-run JSONs — no
    # preprocessed image content is ever retrieved.
    json_files = sorted(mriqc_dir.rglob("*_bold.json"))
    if not json_files:
        print(f"⚠️  {dataset}: no *_bold.json found (mriqc submodule empty or "
              f"not initialized) — writing empty table")
    if smoke:
        json_files = json_files[:1]
    if json_files:
        datalad_get([p.relative_to(root) for p in json_files], root)

    rows = [row for p in json_files if (row := _row_from_json(p, dataset))]
    table = pd.DataFrame(rows)

    output_path = Path(output_dir) / "qc_measures" / f"{dataset}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_path, sep="\t", index=False)
    print(f"✅ {dataset}: {len(table)} run(s) → {output_path}")
    return output_path
