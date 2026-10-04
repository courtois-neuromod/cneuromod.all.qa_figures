"""Constants for the per-subject upstream tSNR average maps in cneuromod.all.

The ``tsnr`` derivative of each dataset ships a **per-subject** average tSNR
statmap in MNI space (``sub-XX_..._space-MNI152NLin2009cAsym_stat-avgtsnr``),
computed upstream from the run-level maps. This is the one image slice
``fetch`` retrieves (see ``analysis/prefetch.py``); the ``tsnr_maps`` notebook
reads it directly from ``source_data`` and renders montages — nothing is
computed or written by this module, and no NIfTI is persisted under
``output_data/``.

Only a few datasets ship the upstream ``stat-avgtsnr`` map (floc, retinotopy,
things, hcptrt at the time of writing). Datasets with only run-level
``stat-tsnr`` maps (friends, …) have none to read, so the notebook falls back to
averaging the run-level maps on disk per subject, in memory.
"""

# The one space we work in: comparable across subjects and datasets (needed to
# average). T1w (native) maps are deliberately ignored.
SPACE = "MNI152NLin2009cAsym"
# Per-subject upstream average map: sub-XX/sub-XX_..._space-<SPACE>_stat-avgtsnr_statmap.nii.gz
SUBJECT_AVG_GLOB = f"sub-*/sub-*_space-{SPACE}_stat-avgtsnr_statmap.nii.gz"
