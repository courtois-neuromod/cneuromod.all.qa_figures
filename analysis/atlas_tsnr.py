"""Extract per-run, per-region tSNR from the shared MNI atlas in cneuromod.all.

For every functional run we already have a per-run ``stat-tsnr`` statmap in
``MNI152NLin2009cAsym`` space (the ``tsnr`` derivative). This step resamples
each run's map onto the shared combined atlas's grid (see
``analysis/atlas_labels.py``) and averages tSNR within each atlas parcel via
``scipy.ndimage.mean``, then collapses those parcels to one row per
``(run, region group)`` — the granularity every figure actually shows. Reads
only files already on disk; never calls ``datalad get`` (retrieval is
``invoke fetch``'s job).
"""

from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
from bids.layout import parse_file_entities
from nilearn.image import resample_to_img
from scipy import ndimage

from analysis.atlas_labels import ATLAS_SPACE, atlas_nii_path, load_region_table

SPACE = ATLAS_SPACE
RUN_TSNR_GLOB = f"sub-*/ses-*/func/sub-*_ses-*_task-*_space-{SPACE}_stat-tsnr_statmap.nii.gz"


def _collapse_to_groups(parcel_rows):
    """One row per region group, averaging equally over that group's parcels.

    The per-parcel values are dropped here rather than at read time: no figure
    shows an individual parcel, and keeping them made a single dataset's table
    72 MB of git history. ``n_parcels`` counts the parcels that actually
    contributed (``ndimage.mean`` returns NaN for one cropped out of this run's
    FOV), so a consumer can still pool several groups with every parcel weighted
    equally — a plain mean of the group means would not, since the groups hold
    different numbers of parcels.
    """
    return (parcel_rows.groupby("group")["tsnr_mean"]
            .agg(tsnr_mean="mean", n_parcels="count")  # both skip NaN parcels
            .reset_index())


def _run_rows(run_path, dataset, atlas_img, atlas_data, region_table):
    """Tidy rows (one per region group) for one run's tSNR map, or None.

    Resamples the run's tSNR map onto the atlas's grid (nearest-neighbor, to
    preserve observed tSNR values rather than blending them) before averaging
    within each parcel.
    """
    if not run_path.is_file():  # broken annex symlink → content not retrieved
        return None
    try:
        run_img = nib.load(run_path)
        resampled = resample_to_img(run_img, atlas_img, interpolation="nearest")
    except Exception:
        return None
    tsnr_data = resampled.get_fdata()
    with np.errstate(invalid="ignore"):  # NaN for a region cropped out of this run's FOV
        means = ndimage.mean(tsnr_data, labels=atlas_data, index=region_table["label_id"])

    entities = parse_file_entities(str(run_path))
    base = {
        "dataset": dataset,
        "subject": entities.get("subject"),
        "session": entities.get("session"),
        "task": entities.get("task"),
        "run": entities.get("run"),
    }
    parcel_rows = region_table[["region_name", "group"]].copy()
    parcel_rows["tsnr_mean"] = means
    rows = _collapse_to_groups(parcel_rows)
    for key, value in base.items():
        rows[key] = value
    return rows


def extract_region_tsnr(dataset, cneuromod_dir, output_dir, atlases_dir,
                         smoke=False, strict=False):
    """Write one per-run-per-region tSNR TSV for ``dataset``; return the path.

    Reads only the per-run MNI ``stat-tsnr`` maps already present on disk and
    the shared combined atlas — retrieval is ``invoke fetch``'s job, not this
    step's. With ``strict=True`` (used by the smoke test), an empty result is
    a hard failure instead of a quietly-written empty table.
    """
    root = Path(cneuromod_dir)
    tsnr_dir = root / dataset / "tsnr"

    run_files = sorted(tsnr_dir.glob(RUN_TSNR_GLOB))
    if not run_files:
        if strict:
            raise RuntimeError(
                f"{dataset}: no MNI stat-tsnr statmap present under {tsnr_dir} "
                f"— run `invoke fetch` (for this dataset) first"
            )
        print(f"⚠️  {dataset}: no MNI stat-tsnr statmap present "
              f"(run `invoke fetch` first) — writing empty table")
    if smoke:
        run_files = run_files[:1]

    atlas_path = atlas_nii_path(atlases_dir)
    tables = []
    if run_files and not atlas_path.is_file():
        message = (f"{dataset}: combined atlas not present at {atlas_path} "
                    f"— run `invoke fetch` first")
        if strict:
            raise RuntimeError(message)
        print(f"⚠️  {message} — writing empty table")
    elif run_files:
        atlas_img = nib.load(atlas_path)
        atlas_data = atlas_img.get_fdata()
        region_table = load_region_table(atlases_dir).dropna(subset=["group"])
        tables = [rows for p in run_files
                  if (rows := _run_rows(p, dataset, atlas_img, atlas_data,
                                         region_table)) is not None]

    table = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    if strict and table.empty:
        raise RuntimeError(
            f"{dataset}: found {len(run_files)} run map(s) but extracted 0 rows "
            f"(content not present — run `invoke fetch` first)"
        )

    output_path = Path(output_dir) / "tables" / "atlas_tsnr" / f"{dataset}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_path, sep="\t", index=False)
    print(f"✅ {dataset}: {len(run_files)} run(s) → {len(table)} group-row(s) "
          f"→ {output_path}")
    return output_path
