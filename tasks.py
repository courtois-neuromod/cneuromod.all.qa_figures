from pathlib import Path

from invoke import Exit, task


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _cneuromod_dir(c):
    return Path(c.config.get("datasets", {}).get("cneuromod_all", {})["output_dir"])


def _select_datasets(requested, available, smoke):
    """Resolve which datasets a run task should process."""
    if requested:
        return [name.strip() for name in requested.split(",") if name.strip()]
    if smoke:
        return available[:1]
    return available


def _ensure_marker_submodule(cneuromod_dir, dataset, marker, strict=False):
    """Install the ``{dataset}/{marker}`` Datalad subdataset inside cneuromod.all.

    Each derivative folder of cneuromod.all is a Datalad subdataset nested inside
    the per-``{dataset}`` subdataset, present on disk only as an empty mountpoint
    until installed. We use ``datalad get -n`` (via ``install_subdataset``) rather
    than plain ``git submodule``: datalad installs the intermediate ``{dataset}``
    subdataset and the nested ``{marker}`` in one call — plain git cannot reach a
    submodule nested inside another submodule — while leaving large sibling
    subdatasets like ``stimuli`` alone. Tolerant by default: an inaccessible
    derivative (credentialed remote, no auth) only warns so one dataset never
    aborts the run. With ``strict=True`` (smoke test) a failed install raises.
    """
    from analysis.datalad_utils import install_subdataset

    install_subdataset(
        f"{dataset}/{marker}", Path(cneuromod_dir).resolve(), strict=strict
    )


def _ensure_superdataset_available(c, source=None):
    """Make the cneuromod.all superdataset present under source_data/ (no content).

    Symlinks an existing local checkout (``source`` or the ``source:`` key in
    invoke.yaml, i.e. ../cneuromod.all) or clones the remote when none exists.
    This is the cheap "make available" half of ``fetch`` — no ``datalad get`` of
    file content. Both ``fetch`` (before its bulk prefetch) and ``run`` (which
    then relies on each ``run-*`` step's own on-demand get) call it, so
    reproduction never re-triggers bulk asset gathering.
    """
    cfg = c.config.get("datasets", {}).get("cneuromod_all", {})
    dest = Path(cfg["output_dir"])
    url = cfg.get("url")
    source = source or cfg.get("source")

    if dest.exists() or dest.is_symlink():
        print(f"🫧 cneuromod.all already present at {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source and Path(source).exists():
        target = Path(source).resolve()
        print(f"🔗 Linking existing checkout {target} -> {dest}")
        dest.symlink_to(target, target_is_directory=True)
    else:
        if source:
            print(f"⚠️  Source '{source}' not found — cloning remote instead.")
        print(f"📥 Cloning {url} -> {dest} (content retrieved on demand)")
        c.run(f"datalad clone {url} {dest}")


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
@task(help={
    "source": "Path to an existing local cneuromod.all checkout to use instead "
              "of cloning (defaults to the `source:` key in invoke.yaml, "
              "i.e. ../cneuromod.all).",
    "dataset": "Comma-separated dataset names to restrict the fetch to "
               "(default: all datasets with an mriqc subdataset).",
    "subject": "Comma-separated subject labels (e.g. 01,03) to restrict the "
               "fetch to.",
    "session": "Comma-separated session labels (e.g. 001,002) to restrict the "
               "fetch to.",
})
def fetch(c, source=None, dataset=None, subject=None, session=None):
    """
    Make the cneuromod.all Datalad superdataset available under source_data/,
    then retrieve the small MRIQC text files the analysis steps read.

    First, make the superdataset available: symlink an existing local checkout
    (../cneuromod.all by default), or clone the remote when no local checkout
    exists.

    Then, by default, install every dataset's mriqc subdataset and `datalad get`
    only the small text files the pipeline needs — MRIQC *_bold.json and
    *_timeseries.tsv — so a fresh clone is ready for `run` offline. No *.nii.gz
    is ever retrieved. Pass --dataset/--subject/--session to narrow that
    retrieval to a slice. Tolerant of partly-public data: inaccessible content
    only warns, never aborts (the run steps re-`datalad get` on demand anyway).
    """
    _ensure_superdataset_available(c, source)

    from analysis.prefetch import parse_labels, prefetch_slice
    cneuromod_dir = _cneuromod_dir(c)
    prefetch_slice(
        cneuromod_dir,
        parse_labels(dataset),
        parse_labels(subject),
        parse_labels(session),
        ensure_submodule=lambda ds, marker: _ensure_marker_submodule(
            cneuromod_dir, ds, marker
        ),
    )

    print("✅ fetch complete.")


# --------------------------------------------------------------------------- #
# Analysis steps (chunk = dataset)
# --------------------------------------------------------------------------- #
@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with an "
               "mriqc subdataset).",
    "smoke": "Process only the first dataset (fast end-to-end check).",
    "strict": "Raise on any retrieval/extraction failure instead of warning "
              "(implied by run --smoke; also re-runs datasets whose output exists).",
})
def run_qc_measures(c, dataset=None, smoke=False, strict=False):
    """
    Extract per-run MRIQC QC metrics for each dataset of cneuromod.all.

    Writes one tidy table per dataset to output_data/tables/{dataset}.tsv.
    Datasets whose output already exists are skipped — except in ``strict`` mode,
    where a stale table must not mask a retrieval failure, so it is re-run.
    """
    from analysis.datasets import list_datasets
    from analysis.qc_measures import extract_qc_measures

    cneuromod_dir = _cneuromod_dir(c)
    output_dir = Path(c.config.get("output_data_dir"))
    names = _select_datasets(dataset, list_datasets(cneuromod_dir, "mriqc"), smoke)

    for dataset in names:
        out = output_dir / "tables" / f"{dataset}.tsv"
        if out.exists() and not strict:
            print(f"🫧 Skipping {dataset} qc_measures (output exists)")
            continue
        _ensure_marker_submodule(cneuromod_dir, dataset, "mriqc", strict=strict)
        extract_qc_measures(
            dataset, cneuromod_dir, output_dir, smoke=smoke, strict=strict
        )


# --------------------------------------------------------------------------- #
# Notebooks
# --------------------------------------------------------------------------- #
@task
def run_notebooks(c):
    """
    Generate QA figures from the metric tables in output_data/ using notebooks.
    """
    from airoh.utils import ensure_dir_exist
    from airoh.utils import run_notebooks as airoh_run_notebooks

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    figures_base = Path(c.config.get("figures_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    # Each notebook writes into figures_base/<stem>/, which airoh also treats as
    # the per-notebook "already ran" sentinel — kept separate from the data dir
    # output_data/tables/.
    airoh_run_notebooks(
        c, notebooks_dir, figures_base, keys=["source_data_dir", "output_data_dir"]
    )


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with an "
               "mriqc subdataset). In --smoke mode, defaults to `smoke_dataset` "
               "in invoke.yaml (i.e. hcptrt).",
    "smoke": "Strict minimal end-to-end test on one functional dataset: implies "
             "--strict, re-runs stale TSVs, and asserts non-empty output at the "
             "end (non-zero exit if nothing is extracted). Defaults --dataset to "
             "`smoke_dataset`.",
    "strict": "Raise on any retrieval/extraction failure instead of warning.",
})
def run(c, dataset=None, smoke=False, strict=False):
    """Full pipeline: ensure cneuromod.all available → qc-measures → figures.

    Unlike ``fetch``, ``run`` does NOT bulk-prefetch: it only makes the
    superdataset available, then each ``run-qc-measures`` step installs and
    ``datalad get``s only its own dataset's files on demand. Run ``invoke fetch``
    first to gather all assets up front; ``run`` alone still works on a fresh
    clone via that per-step on-demand retrieval.

    ``--smoke`` turns this into a strict end-to-end test: unlike the tolerant
    production run, it FAILS LOUDLY (non-zero exit) if nothing is retrieved or
    extracted, so it actually tests the plumbing. It runs on a single dataset
    that genuinely has functional MRIQC data (default `smoke_dataset`, i.e.
    hcptrt) — an empty result then unambiguously means retrieval is broken, not
    that the dataset simply has no BOLD runs (e.g. anat).
    """
    strict = strict or smoke
    if smoke and not dataset:
        dataset = c.config.get("smoke_dataset", "hcptrt")

    # Reproduction only ensures the superdataset is *available*; it does NOT
    # re-run fetch's bulk prefetch. Each run-qc-measures step installs and
    # `datalad get`s only its own dataset's files on demand (see qc_measures.py),
    # keeping asset gathering (`fetch`) separate from reproduction (`run`).
    _ensure_superdataset_available(c)
    run_qc_measures(c, dataset=dataset, smoke=smoke, strict=strict)
    run_notebooks(c)

    if not smoke:
        print("all analyses completed")
        return

    import pandas as pd

    output_dir = Path(c.config.get("output_data_dir"))
    targets = [name.strip() for name in dataset.split(",") if name.strip()]
    for target in targets:
        out = output_dir / "tables" / f"{target}.tsv"
        if not out.exists() or pd.read_csv(out, sep="\t").empty:
            raise Exit(
                f"❌ Smoke test FAILED: no QC rows extracted for {target}", code=1
            )
        print(f"✅ Smoke test passed: {target} produced QC rows at {out}")


# --------------------------------------------------------------------------- #
# Clean
# --------------------------------------------------------------------------- #
@task
def clean_qc_measures(c):
    """Remove QC-metric outputs."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "tables/*.tsv")


@task
def clean_figures(c):
    """Remove generated figures and notebook sentinels."""
    from airoh.utils import clean_folder
    clean_folder(c, "figures_dir")


@task(pre=[clean_qc_measures, clean_figures])
def clean(c):
    """Remove all computed outputs."""
    pass


@task
def clean_cneuromod(c):
    """Remove the fetched cneuromod.all superdataset (symlink or clone)."""
    dest = _cneuromod_dir(c)
    if dest.is_symlink():
        dest.unlink()
        print(f"🧹 Removed symlink {dest}")
    elif dest.exists():
        print(f"⚠️  {dest} is a real clone, not a symlink — remove it manually "
              f"if you are sure: rm -rf {dest}")
    else:
        print(f"🫧 Nothing to clean — {dest} is not present")


@task(pre=[clean_cneuromod])
def clean_source(c):
    """Remove all fetched source data."""
    pass
