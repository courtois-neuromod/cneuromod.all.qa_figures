"""Extract per-run QC metrics from MRIQC BOLD reports in cneuromod.all.

MRIQC writes one small JSON of image-quality metrics (IQMs) per functional run.
We read only those JSONs — never the preprocessed ``.nii.gz`` — so the data
footprint stays tiny. One tidy TSV per dataset is written to
``output_data/tables/{dataset}.tsv``, one row per run.
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

# Per-run motion-outlier proportions computed from the MRIQC *_timeseries.tsv
# ``framewise_displacement`` column: fraction of volumes whose FD (mm) exceeds
# each threshold. Named ``fd_prop_*`` (proportions in 0–1) to stay distinct from
# MRIQC's own percentage-valued ``fd_perc``.
FD_THRESHOLDS = {"fd_prop_gt02": 0.2, "fd_prop_gt05": 0.5}


def _task_grouped(task):
    """Strip a trailing run/segment index so e.g. 'life1'/'life2' group as 'life'."""
    if not task:
        return task
    return re.sub(r"\d+[abcd]?$", "", task)


def _fd_proportions(bold_json_path):
    """Proportion of volumes with FD over each threshold, from the sibling
    MRIQC ``*_timeseries.tsv``. NaN for each key if the TSV is missing/unreadable.

    Denominator is the total number of volumes (the first ``n/a`` row counts but
    never exceeds a threshold), matching MRIQC's own ``fd_perc`` convention so
    that ``fd_prop_gt02 * 100 ≈ fd_perc`` as a cross-check.
    """
    ts_path = bold_json_path.with_name(
        bold_json_path.name.replace("_bold.json", "_timeseries.tsv"))
    nan_result = {key: np.nan for key in FD_THRESHOLDS}
    if not ts_path.is_file():
        return nan_result
    try:
        fd = pd.read_csv(ts_path, sep="\t")["framewise_displacement"]
    except (OSError, KeyError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return nan_result
    n_volumes = len(fd)
    if n_volumes == 0:
        return nan_result
    return {key: float((fd > thr).sum()) / n_volumes
            for key, thr in FD_THRESHOLDS.items()}


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
    row.update(_fd_proportions(path))
    return row


def extract_qc_measures(dataset, cneuromod_dir, output_dir, smoke=False,
                        strict=False):
    """Write one QC-metrics TSV for ``dataset``; return the output path.

    With ``strict=True`` (used by the smoke test) an empty result is a hard
    failure: it raises ``RuntimeError`` when no ``*_bold.json`` is found or when
    no row could be extracted, instead of quietly writing an empty table.
    """
    root = Path(cneuromod_dir)
    mriqc_dir = root / dataset / "mriqc"

    # The mriqc submodule is initialized by the caller (run_qc_measures task)
    # before we glob it. Here we only fetch the small per-run JSONs — no
    # preprocessed image content is ever retrieved.
    json_files = sorted(mriqc_dir.rglob("*_bold.json"))
    if not json_files:
        if strict:
            raise RuntimeError(
                f"{dataset}: no *_bold.json found under {mriqc_dir} "
                f"(mriqc submodule empty or not initialized)"
            )
        print(f"⚠️  {dataset}: no *_bold.json found (mriqc submodule empty or "
              f"not initialized) — writing empty table")
    if smoke:
        json_files = json_files[:1]
    if json_files:
        # Best-effort even in strict mode: the JSONs may already be present on
        # disk (a fresh `datalad get` can fail on a stale git-annex while the
        # content is readable). The real strict gate is the empty-table check
        # below — what matters is whether we ultimately extract any rows. We also
        # fetch the sibling *_timeseries.tsv (per-volume FD) — plain files on the
        # datasets checked, but this future-proofs any where they are annexed.
        text_files = [p for j in json_files
                      for p in (j, j.with_name(
                          j.name.replace("_bold.json", "_timeseries.tsv")))]
        datalad_get([p.relative_to(root) for p in text_files], root)

    rows = [row for p in json_files if (row := _row_from_json(p, dataset))]
    table = pd.DataFrame(rows)
    if strict and table.empty:
        raise RuntimeError(
            f"{dataset}: found {len(json_files)} JSON(s) but extracted 0 rows "
            f"(content not retrieved or unreadable)"
        )

    output_path = Path(output_dir) / "tables" / f"{dataset}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_path, sep="\t", index=False)
    print(f"✅ {dataset}: {len(table)} run(s) → {output_path}")
    return output_path
