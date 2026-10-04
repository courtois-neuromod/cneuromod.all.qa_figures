"""Label scheme for the MNI152NLin2009cAsym combined atlases.

`anat/atlases` (a dataset-root-level subdataset of cneuromod.all, sibling to
`anat/bids`/`anat/smriprep`, installed separately from the per-functional-
dataset `tsnr`/`mriqc` markers — see `analysis/prefetch.py`) ships a combined
cortex+subcortex+cerebellum parcellation in MNI152NLin2009cAsym space. Native
T1w space only has a plain Schaefer2018 cortical parcellation per subject.

Besides a 1 mm group-template volume (`res-01`), it ships one **per-subject
`res-func`** volume for sub-01..sub-06
(`tpl-MNI152NLin2009cAsym_sub-0N_res-func_atlas-...`), already on the functional
runs' grid (97x115x97, identical affine to the `stat-tsnr` maps; verified
2026-10-04). Same label IDs as the template; the labelled mask differs per
subject (consistent with each subject's grey-matter mask). All share one
sibling `.tsv` (`index`, `name` columns, 1178 rows, globally unique labels):

- 1-1000: Schaefer2018 1000-parcel/7-network cortex, `7Networks_{LH,RH}_
  <Network>_<n>` names.
- 1001-1050: Tian S3 (Melbourne) subcortex — richer than putamen/thalamus/
  caudate alone (`PUT-`, `THA-`, `CAU-`, `HIP-`, `lAMY-`/`mAMY-`, `NAc-`,
  `aGP-`/`pGP-` prefixes, each L/R split into subregions).
- 1051-1178: Nettekoven cerebellar cortex parcellation, `Cereb-*` names.

`atlas_tsnr.py` averages each run's tSNR map directly within its subject's
`res-func` atlas — no resampling.
"""

from pathlib import Path

import pandas as pd

ATLAS_SPACE = "MNI152NLin2009cAsym"
ATLAS_SUBDIR = f"tpl-{ATLAS_SPACE}"
ATLAS_DESC = "Schaefer2018TianS3NettekovenAsym_desc-1000Parcels7Networks50Subcort128Cereb"
ATLAS_TSV = f"tpl-{ATLAS_SPACE}_atlas-{ATLAS_DESC}.tsv"
# Scoped tightly to this combined atlas: `anat/atlases` ships many other
# Schaefer/BASC/task-mask files in the same folder that must NOT be pulled.
ATLAS_GLOB = f"{ATLAS_SUBDIR}/tpl-{ATLAS_SPACE}*atlas-{ATLAS_DESC}*"

YEO_NETWORKS = (
    "Vis", "SomMot", "DorsAttn", "SalVentAttn", "Limbic", "Cont", "Default",
)
# "Central/subcortical structures" per the original spec, restricted to these
# three — other Tian S3 structures present in the atlas (pallidum, hippocampus,
# amygdala, nucleus accumbens) are excluded, not silently lumped in.
SUBCORTEX_STRUCTURES = ("PUT", "THA", "CAU")


def classify_region(region_name):
    """Region group for one atlas label name, or None if excluded.

    "cortex_<Network>" for a Schaefer2018 cortical parcel, "cerebellum" for a
    Nettekoven parcel, "subcortex_<structure>" for a Tian S3 parcel whose
    structure is one of SUBCORTEX_STRUCTURES, else None.
    """
    if region_name.startswith("7Networks_"):
        network = region_name.split("_")[2]
        return f"cortex_{network}" if network in YEO_NETWORKS else None
    if region_name.startswith("Cereb-"):
        return "cerebellum"
    structure = region_name.split("-")[0]
    return f"subcortex_{structure}" if structure in SUBCORTEX_STRUCTURES else None


def load_region_table(atlases_dir):
    """Read the combined atlas's (shared) label TSV and add a `group` column.

    `atlases_dir` is the installed `anat/atlases` subdataset root. Returns a
    DataFrame with `label_id`, `region_name`, `group` — rows with group=None
    are excluded parcels, kept here rather than dropped so callers can see
    what was excluded and why.
    """
    tsv_path = Path(atlases_dir) / ATLAS_SUBDIR / ATLAS_TSV
    table = pd.read_csv(tsv_path, sep="\t")
    table = table.rename(columns={"index": "label_id", "name": "region_name"})
    table["group"] = table["region_name"].map(classify_region)
    return table


def subject_atlas_path(atlases_dir, subject):
    """Path to ``subject``'s ``res-func`` atlas volume (``subject`` like "01")."""
    name = f"tpl-{ATLAS_SPACE}_sub-{subject}_res-func_atlas-{ATLAS_DESC}_dseg.nii.gz"
    return Path(atlases_dir) / ATLAS_SUBDIR / name
