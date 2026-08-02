"""ICBM152 2009 MNI template, cached under source_data/nilearn.

Called by the `fetch-mni152` invoke task to bulk-download the template used
as the background image (T1) and brain restriction (whole-brain mask) for
the tSNR coverage montages (notebooks/tsnr_maps.ipynb) — that notebook
duplicates the same `fetch_icbm152_2009` call locally rather than importing
this module, matching its existing pattern of not importing from
`analysis/` (nbconvert executes notebooks with `notebooks/` as the cwd, so
the `analysis` package is not on `sys.path` there). `fetch_mni152_templates`
is cache-aware — nilearn checks the target dir before downloading — so it is
a cheap no-op once fetched. Unlike `analysis/prefetch.py`'s Datalad wrapper,
this is a plain nilearn download with no symlink/clone semantics.
"""

from pathlib import Path

from nilearn.datasets import fetch_icbm152_2009


def fetch_mni152_templates(data_dir):
    """Fetch (or reuse the cached) ICBM152 2009 T1 template and brain mask.

    Returns ``(t1_path, mask_path)``.
    """
    templates = fetch_icbm152_2009(data_dir=str(data_dir))
    return Path(templates["t1"]), Path(templates["mask"])
