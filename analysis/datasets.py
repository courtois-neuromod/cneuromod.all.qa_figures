"""Discover which datasets inside the cneuromod.all superdataset to process."""

from pathlib import Path


def list_datasets(cneuromod_dir, marker):
    """Return sorted dataset names holding a `marker` subdataset.

    A "dataset" is a top-level directory of the cneuromod.all superdataset
    (e.g. ``hcptrt``, ``friends``). ``marker`` is the derivative subdataset that
    must be present for the step to have anything to do — ``"mriqc"`` for the QC
    metrics. The marker directory only has to exist (it may be an un-installed
    Datalad mountpoint); content is fetched on demand by the analysis step.
    """
    cneuromod_dir = Path(cneuromod_dir)
    names = []
    for child in sorted(cneuromod_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / marker).is_dir():
            names.append(child.name)
    return names
