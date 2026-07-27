"""Assemble average tSNR brain maps per subject and per dataset from cneuromod.all.

The ``tsnr`` derivative of each dataset already ships a **per-subject** average
tSNR statmap in MNI space (``sub-XX_..._space-MNI152NLin2009cAsym_stat-avgtsnr``),
computed upstream from the run-level maps. We reuse those directly: copy each
subject map into ``output_data/tsnr_maps/{dataset}/`` and average them across
subjects into a single dataset-level map for the QA figure.

Only a few datasets ship the upstream ``stat-avgtsnr`` map (floc, retinotopy,
things at the time of writing). Datasets that have only run-level ``stat-tsnr``
maps (hcptrt, friends, …) are **skipped with a warning** in this first version —
computing their subject-average from the run-level maps would mean fetching many
full-resolution ``.nii.gz`` (a much larger footprint) and is deferred to a future
step.

Unlike the MRIQC step (which never touches image content), this step DOES fetch
``.nii.gz`` — but only the small, narrow slice it needs: the per-subject
``stat-avgtsnr`` maps in ``MNI152NLin2009cAsym`` space, one per subject. It never
pulls run-level, ``T1w``, or fMRIPrep content.
"""

import shutil
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn.image import resample_to_img

# The one space we work in: comparable across subjects and datasets (needed to
# average). T1w (native) maps are deliberately ignored.
SPACE = "MNI152NLin2009cAsym"
# Per-subject upstream average map: sub-XX/sub-XX_..._space-<SPACE>_stat-avgtsnr_statmap.nii.gz
SUBJECT_AVG_GLOB = f"sub-*/sub-*_space-{SPACE}_stat-avgtsnr_statmap.nii.gz"


def _dataset_average(map_paths, reference_path):
    """Mean tSNR image over ``map_paths``, resampled onto ``reference_path``'s grid.

    Maps from different subjects may sit on slightly different grids, so each is
    resampled to the reference (the first map) before averaging. NaNs are ignored
    voxelwise so a subject missing coverage never blanks a voxel for everyone.
    """
    reference = nib.load(str(reference_path))
    stack = []
    for path in map_paths:
        image = nib.load(str(path))
        if image.shape != reference.shape or not np.allclose(image.affine, reference.affine):
            image = resample_to_img(image, reference, copy_header=True)
        stack.append(np.asarray(image.dataobj, dtype=np.float32))
    mean = np.nanmean(np.stack(stack, axis=-1), axis=-1)
    return nib.Nifti1Image(mean, reference.affine, reference.header)


def compute_tsnr_maps(dataset, cneuromod_dir, output_dir, smoke=False, strict=False):
    """Write per-subject + dataset-average tSNR maps for ``dataset``; return the
    dataset-average path.

    Copies each subject's upstream ``stat-avgtsnr`` MNI map into
    ``output_data/tsnr_maps/{dataset}/`` and writes the across-subject mean map
    ``{dataset}_space-<SPACE>_stat-avgtsnr_statmap.nii.gz`` beside them. With
    ``strict=True`` (smoke test) an empty result is a hard failure instead of a
    quiet skip.
    """
    root = Path(cneuromod_dir)
    tsnr_dir = root / dataset / "tsnr"

    # The tsnr submodule is installed by the caller (run_tsnr_maps task) before
    # we glob it. We then fetch ONLY these per-subject avgtsnr MNI maps.
    subject_maps = sorted(tsnr_dir.glob(SUBJECT_AVG_GLOB))
    if not subject_maps:
        if strict:
            raise RuntimeError(
                f"{dataset}: no {SUBJECT_AVG_GLOB} found under {tsnr_dir} "
                f"(tsnr submodule empty or not initialized)"
            )
        print(f"⚠️  {dataset}: no avgtsnr MNI maps found (tsnr submodule empty or "
              f"not initialized) — skipping")
        return None
    if smoke:
        subject_maps = subject_maps[:1]

    # Best-effort even in strict mode: the .nii.gz may already be present while a
    # fresh `datalad get` fails on a stale git-annex. The strict gate is the
    # present-map check below, not the fetch.
    from analysis.datalad_utils import datalad_get
    datalad_get([p.relative_to(root) for p in subject_maps], root)

    dataset_dir = Path(output_dir) / "tsnr_maps" / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)

    present = [p for p in subject_maps if p.is_file()]
    if strict and not present:
        raise RuntimeError(
            f"{dataset}: found {len(subject_maps)} avgtsnr map(s) but none had "
            f"content on disk (datalad get did not retrieve them)"
        )
    for path in present:
        shutil.copy2(path, dataset_dir / path.name)

    dataset_map = _dataset_average(present, present[0])
    output_path = dataset_dir / f"{dataset}_space-{SPACE}_stat-avgtsnr_statmap.nii.gz"
    dataset_map.to_filename(str(output_path))
    print(f"✅ {dataset}: {len(present)} subject map(s) → {output_path}")
    return output_path
