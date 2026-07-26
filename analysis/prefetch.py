"""Retrieve the small MRIQC text files cneuromod.all analysis needs.

``invoke fetch`` calls this after making the superdataset available: it installs
each dataset's mriqc subdataset and ``datalad get``s the small text files the
``run-*`` steps read — MRIQC ``*_bold.json`` and ``*_timeseries.tsv`` — so a
fresh clone is ready to ``run`` offline. Passing a dataset/subject/session
narrows it to that slice; with no filter it covers every dataset. The ``run-*``
steps still ``datalad get`` on demand as a safety net.
No preprocessed ``.nii.gz`` is ever retrieved.
"""

from pathlib import Path

from bids.layout import parse_file_entities

from analysis.datalad_utils import datalad_get
from analysis.datasets import list_datasets

# (subdataset marker, text-file glob) pairs to prefetch — the small metadata
# files the analysis steps read, never the annexed image content.
_TEXT_TARGETS = [("mriqc", "*_bold.json"), ("mriqc", "*_timeseries.tsv")]


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
    """Fetch MRIQC/BIDS text files for the given dataset/subject/session slice.

    ``datasets``/``subjects``/``sessions`` are lists of labels or ``None`` (no
    filter). ``ensure_submodule`` is an optional ``(dataset, marker) -> None``
    callback the caller supplies to initialize each derivative git submodule
    before it is globbed (the invoke task provides it; see ``tasks.py``). Kept as
    a callback so this module stays free of the invoke ``Context``. Best-effort
    throughout — inaccessible content only warns (see ``analysis.datalad_utils``).
    """
    root = Path(cneuromod_dir)
    names = datasets or _all_dataset_names(root)

    for dataset in names:
        counts = []
        for marker, pattern in _TEXT_TARGETS:
            if ensure_submodule is not None:
                ensure_submodule(dataset, marker)
            fetched = _prefetch_target(root, dataset, marker, pattern, subjects, sessions)
            counts.append(f"{fetched} {pattern}")
        print(f"📦 {dataset}: prefetched " + ", ".join(counts))


def _all_dataset_names(root):
    """All datasets exposing an mriqc subdataset (sorted)."""
    return list_datasets(root, "mriqc")


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
