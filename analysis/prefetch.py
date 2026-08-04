"""Retrieve, up front, every small file the cneuromod.all analysis reads.

``invoke fetch`` calls this after making the superdataset available. It installs
each dataset's derivative subdatasets and ``datalad get``s exactly the files the
``run-*`` steps read, so that ``run`` works purely offline — checking presence,
never pulling:

  - MRIQC ``*_bold.json`` and ``*_timeseries.tsv`` (small text metadata),
  - the per-subject ``stat-avgtsnr`` MNI maps under each ``tsnr`` derivative
    (small ``.nii.gz``, one per subject), and
  - the per-run ``stat-tsnr`` MNI maps under each ``tsnr`` derivative (one per
    functional run — read by ``run-atlas-tsnr``).

Passing a dataset/subject/session narrows this to that slice; with no filter it
covers every dataset. Separately, and unconditionally (it is not nested under any
one functional dataset), it also installs the dataset-root-level ``anat/atlases``
subdataset and fetches the single shared combined-atlas volume + label TSV that
``run-atlas-tsnr`` resamples every run's tSNR map onto. No other ``.nii.gz``
(T1w, fMRIPrep) is retrieved.
"""

from pathlib import Path

from airoh.datalad import load_known_failures, prefetch_pattern, save_known_failures
from bids.layout import parse_file_entities

from analysis.atlas_labels import ATLAS_GLOB
from analysis.atlas_tsnr import RUN_TSNR_GLOB
from analysis.datasets import list_datasets
from analysis.tsnr_maps import SUBJECT_AVG_GLOB

# (subdataset marker, [file globs]) to prefetch — the small files the analysis
# steps read: MRIQC text metadata, plus the per-subject avgtsnr MNI maps and the
# per-run tsnr MNI maps, the annexed image content the pipeline needs. Everything
# ``run`` later reads must be retrieved here, since ``run`` no longer fetches on
# demand. ``anat/atlases`` is fetched separately (see ``prefetch_atlases``) since
# it lives at the cneuromod.all root, not nested under a functional dataset.
_TARGETS = [
    ("mriqc", ["*_bold.json", "*_timeseries.tsv"]),
    ("tsnr", [SUBJECT_AVG_GLOB, RUN_TSNR_GLOB]),
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


def prefetch_slice(cneuromod_dir, datasets, subjects, sessions, ensure_submodule=None,
                    skip_inaccessible=False):
    """Fetch the analysis input files for the given dataset/subject/session slice.

    For each ``(marker, patterns)`` in ``_TARGETS`` (MRIQC text, then the avgtsnr
    maps), install the derivative subdataset and ``datalad get`` the matching
    files. ``datasets``/``subjects``/``sessions`` are lists of labels or ``None``
    (no filter); with no dataset filter each marker's own dataset list is used.
    ``ensure_submodule`` is an optional ``(dataset, marker) -> None`` callback the
    caller supplies to initialize each derivative git submodule before it is
    globbed (the invoke task provides it; see ``tasks.py``). Kept as a callback so
    this module stays free of the invoke ``Context``. Best-effort throughout —
    inaccessible content only warns (see ``airoh.datalad``).

    By default every matching-but-missing file is attempted on every call, even
    one that failed last time (some CNeuroMod content lives only on
    credentialed remotes a given environment can never reach, so a file that
    failed once will keep failing — but access can also be granted later, so
    always retrying is the safe default). Files that fail are remembered (see
    ``airoh.datalad.load_known_failures``/``save_known_failures``) regardless.
    Pass ``skip_inaccessible=True`` to skip anything in that cache instead of
    re-attempting it — worthwhile once
    you've confirmed a given file is permanently out of reach and don't want to
    keep paying its retrieval cost (each credentialed-remote attempt costs
    real time, e.g. ~3s per file) on every routine fetch. The cache is
    refreshed either way, so a file that newly succeeds or newly fails updates
    the record for next time, and is saved after every dataset/marker (not
    just once at the end): an unreachable remote can make a single
    ``datalad get`` batch take a very long time, so an interrupted or
    timed-out run must not lose the failures it already discovered.
    """
    root = Path(cneuromod_dir)
    known_failures = load_known_failures(root.parent)
    skip_set = known_failures if skip_inaccessible else set()
    failures = set(known_failures)

    for marker, patterns in _TARGETS:
        names = datasets or list_datasets(root, marker)
        for dataset in names:
            if ensure_submodule is not None:
                ensure_submodule(dataset, marker)
            counts = []
            for pattern in patterns:
                present, fetched, skipped, new_failures, resolved = _prefetch_target(
                    root, dataset, marker, pattern, subjects, sessions, skip_set)
                failures -= resolved
                failures |= new_failures
                note = f"{present} already had, {fetched} newly fetched"
                if skipped:
                    note += f", {skipped} skipped (known inaccessible)"
                counts.append(f"{note} {pattern}")
            print(f"📦 {dataset}/{marker}: " + "; ".join(counts))
            save_known_failures(root.parent, failures)

    prefetch_atlases(root, ensure_submodule=ensure_submodule,
                      skip_inaccessible=skip_inaccessible)


def prefetch_atlases(cneuromod_dir, ensure_submodule=None, skip_inaccessible=False):
    """Install ``anat/atlases`` and fetch the shared combined-atlas volume + TSV.

    ``anat/atlases`` sits at the cneuromod.all root, sibling to the per-dataset
    subdatasets, so it needs its own install/get call rather than fitting the
    per-``(dataset, marker)`` loop in ``prefetch_slice``. It is a single file
    shared by every subject/dataset (see ``analysis.atlas_labels``), so unlike
    the rest of this module there is no subject/session slice to filter by —
    always fetched in full, unconditional on any ``--dataset``/``--subject``
    filter passed to ``invoke fetch``.
    """
    root = Path(cneuromod_dir)
    known_failures = load_known_failures(root.parent)
    skip_set = known_failures if skip_inaccessible else set()

    if ensure_submodule is not None:
        ensure_submodule("anat", "atlases")

    present, fetched, skipped, new_failures, resolved = _prefetch_target(
        root, "anat", "atlases", ATLAS_GLOB, None, None, skip_set)

    failures = (known_failures - resolved) | new_failures
    save_known_failures(root.parent, failures)

    note = f"{present} already had, {fetched} newly fetched"
    if skipped:
        note += f", {skipped} skipped (known inaccessible)"
    print(f"📦 anat/atlases: {note} {ATLAS_GLOB}")


def _prefetch_target(root, dataset, marker, pattern, subjects, sessions, skip_set):
    """Glob the (already-initialized) marker tree, get missing matching files.

    BIDS-specific thin wrapper around ``airoh.datalad.prefetch_pattern``: it
    narrows the generic glob-and-fetch core to this project's subject/session
    filter via ``_matches``. See ``prefetch_pattern`` for the return shape.

    The ``{dataset}/{marker}`` submodule is initialized by the caller's
    ``ensure_submodule`` callback (see ``prefetch_slice``) before this runs.
    """
    return prefetch_pattern(
        root, pattern, subdir=f"{dataset}/{marker}", skip_set=skip_set,
        match=lambda p: _matches(p, subjects, sessions),
    )
