"""Retrieve, up front, every small file the cneuromod.all analysis reads.

``invoke fetch`` calls this after making the superdataset available. It installs
each dataset's derivative subdatasets and ``datalad get``s exactly the files the
``run-*`` steps read, so that ``run`` works purely offline — checking presence,
never pulling:

  - MRIQC ``*_bold.json`` and ``*_timeseries.tsv`` (small text metadata), and
  - the per-subject ``stat-avgtsnr`` MNI maps under each ``tsnr`` derivative
    (small ``.nii.gz``, one per subject — the only image content ever fetched).

Passing a dataset/subject/session narrows this to that slice; with no filter it
covers every dataset. No other ``.nii.gz`` (run-level, T1w, fMRIPrep) is
retrieved.
"""

from pathlib import Path

from bids.layout import parse_file_entities

from analysis.datalad_utils import datalad_get
from analysis.datasets import list_datasets
from analysis.tsnr_maps import SUBJECT_AVG_GLOB

# (subdataset marker, [file globs]) to prefetch — the small files the analysis
# steps read: MRIQC text metadata, plus the per-subject avgtsnr MNI maps, the one
# narrow slice of annexed image content the pipeline needs. Everything ``run``
# later reads must be retrieved here, since ``run`` no longer fetches on demand.
_TARGETS = [
    ("mriqc", ["*_bold.json", "*_timeseries.tsv"]),
    ("tsnr", [SUBJECT_AVG_GLOB]),
]


def parse_labels(value):
    """Split a comma-separated flag into a list of labels, or None if absent.

    ``"01, 03"`` → ``["01", "03"]``. ``None`` (flag not passed) stays ``None``,
    meaning "no filter" for that entity.
    """
    if value is None:
        return None
    labels = [label.strip() for label in value.split(",") if label.strip()]
    return labels or None


def _matches(path, subjects, sessions):
    """True if the file's subject/session entities pass the requested filters.

    A ``None`` filter accepts everything for that entity.
    """
    entities = parse_file_entities(str(path))
    if subjects is not None and entities.get("subject") not in subjects:
        return False
    if sessions is not None and entities.get("session") not in sessions:
        return False
    return True


def prefetch_slice(cneuromod_dir, datasets, subjects, sessions, ensure_submodule=None):
    """Fetch the analysis input files for the given dataset/subject/session slice.

    For each ``(marker, patterns)`` in ``_TARGETS`` (MRIQC text, then the avgtsnr
    maps), install the derivative subdataset and ``datalad get`` the matching
    files. ``datasets``/``subjects``/``sessions`` are lists of labels or ``None``
    (no filter); with no dataset filter each marker's own dataset list is used.
    ``ensure_submodule`` is an optional ``(dataset, marker) -> None`` callback the
    caller supplies to initialize each derivative git submodule before it is
    globbed (the invoke task provides it; see ``tasks.py``). Kept as a callback so
    this module stays free of the invoke ``Context``. Best-effort throughout —
    inaccessible content only warns (see ``analysis.datalad_utils``).
    """
    root = Path(cneuromod_dir)

    for marker, patterns in _TARGETS:
        names = datasets or list_datasets(root, marker)
        for dataset in names:
            if ensure_submodule is not None:
                ensure_submodule(dataset, marker)
            counts = []
            for pattern in patterns:
                fetched = _prefetch_target(
                    root, dataset, marker, pattern, subjects, sessions)
                counts.append(f"{fetched} {pattern}")
            print(f"📦 {dataset}/{marker}: prefetched " + ", ".join(counts))


def _prefetch_target(root, dataset, marker, pattern, subjects, sessions):
    """Glob the (already-initialized) marker tree, get matching files. Returns count.

    The ``{dataset}/{marker}`` submodule is initialized by the caller's
    ``ensure_submodule`` callback (see ``prefetch_slice``) before this runs.
    """
    marker_dir = root / dataset / marker
    if not marker_dir.is_dir():
        return 0

    files = [p for p in marker_dir.rglob(pattern) if _matches(p, subjects, sessions)]
    if files:
        datalad_get([p.relative_to(root) for p in files], root)
    # Count files whose content is actually present now — datalad get is
    # best-effort (credentialed remotes may be unreachable), so a matched file
    # can remain a broken annex symlink.
    return sum(1 for p in files if p.is_file())
