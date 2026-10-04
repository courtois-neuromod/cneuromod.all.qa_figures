"""Extract per-run, per-region tSNR from the per-subject MNI atlases in cneuromod.all.

For every functional run we already have a per-run ``stat-tsnr`` statmap in
``MNI152NLin2009cAsym`` space (the ``tsnr`` derivative). This step averages each
run's tSNR within each parcel of that subject's own ``res-func`` combined atlas
(see ``analysis/atlas_labels.py``) — already on the runs' grid, so nothing is
resampled — via ``scipy.ndimage.mean``, then collapses those parcels to one row
per ``(run, region group)``, the granularity every figure actually shows. Reads
only files already on disk; never calls ``datalad get`` (retrieval is
``invoke fetch``'s job).
"""

from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
from bids.layout import parse_file_entities
from scipy import ndimage

from analysis.atlas_labels import ATLAS_SPACE, load_region_table, subject_atlas_path

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


def _subject_atlas(subject, atlases_dir, cache):
    """Subject's ``res-func`` atlas image, loaded once; None if not on disk."""
    if subject not in cache:
        path = subject_atlas_path(atlases_dir, subject)
        cache[subject] = nib.load(path) if path.is_file() else None
    return cache[subject]


def _run_rows(run_path, dataset, atlas_img, region_table, strict=False):
    """Tidy rows (one per region group) for one run's tSNR map, or None.

    The subject's atlas is already on the run's grid, so observed tSNR values are
    used as-is; a run whose shape or affine differs is skipped (or raises when
    ``strict``). A parcel cropped out of the run's FOV comes back NaN and is
    excluded from ``n_parcels``.
    """
    if not run_path.is_file():  # broken annex symlink → content not retrieved
        return None
    try:
        run_img = nib.load(run_path)
        tsnr_data = np.asarray(run_img.get_fdata(), dtype=float)
    except Exception:
        return None
    if (run_img.shape != atlas_img.shape
            or not np.allclose(run_img.affine, atlas_img.affine, atol=1e-3)):
        message = f"{run_path.name}: grid differs from the subject atlas's"
        if strict:
            raise RuntimeError(message)
        print(f"⚠️  {message} — skipping run")
        return None
    atlas_data = np.asarray(atlas_img.dataobj, dtype=np.int32)
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
    the per-subject ``res-func`` atlases — retrieval is ``invoke fetch``'s job, not this
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

    tables = []
    if run_files:
        region_table = load_region_table(atlases_dir).dropna(subset=["group"])
        atlas_cache = {}
        missing_subjects = set()
        for run_path in run_files:
            subject = parse_file_entities(str(run_path)).get("subject")
            atlas_img = _subject_atlas(subject, atlases_dir, atlas_cache)
            if atlas_img is None:
                missing_subjects.add(subject)
                continue
            rows = _run_rows(run_path, dataset, atlas_img, region_table, strict)
            if rows is not None:
                tables.append(rows)
        if missing_subjects:
            message = (f"{dataset}: no res-func atlas for sub-"
                       f"{', sub-'.join(sorted(missing_subjects))} "
                       f"— run `invoke fetch` first")
            if strict:
                raise RuntimeError(message)
            print(f"⚠️  {message} — those subjects skipped")

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
