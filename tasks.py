from pathlib import Path

from invoke import Exit, task


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _cneuromod_dir(c):
    return Path(c.config.get("datasets", {}).get("cneuromod_all", {})["output_dir"])


def _nilearn_dir(c):
    return Path(c.config.get("datasets", {}).get("nilearn", {})["output_dir"])


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

    When the marker is already installed, this no longer leaves it silently
    pinned at its original commit: ``install_subdataset`` runs a lightweight
    ``datalad update --merge`` to advance it to latest upstream (tree/metadata
    only, no content), so newly-added upstream files surface on a repeat
    ``fetch`` without a full reinstall.
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
@task
def fetch_mni152(c):
    """Fetch (or reuse the cached) ICBM152 2009 MNI template and brain mask
    used by the tSNR coverage montages (anatomical background + brain
    restriction)."""
    from analysis.mni152 import fetch_mni152_templates

    nilearn_dir = _nilearn_dir(c)
    nilearn_dir.mkdir(parents=True, exist_ok=True)
    t1_path, mask_path = fetch_mni152_templates(nilearn_dir)
    print(f"🧠 MNI152 template available at {t1_path} (brain mask: {mask_path})")


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
    "skip_inaccessible": "Skip files that failed on a previous fetch instead "
                         "of re-attempting them (default: always retry, since "
                         "access can be granted later).",
})
def fetch(c, source=None, dataset=None, subject=None, session=None, skip_inaccessible=False):
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
    Files that fail are remembered (source_data/.fetch_failures.json); by
    default every fetch still retries them (access can be granted later), but
    pass --skip-inaccessible once you know a file is permanently out of reach
    and don't want to keep paying its retrieval cost on every routine fetch.

    Also fetches (or reuses the cached) ICBM152 2009c MNI template used as the
    anatomical background for the tSNR coverage montages (see `fetch-mni152`).
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
        skip_inaccessible=skip_inaccessible,
    )

    fetch_mni152(c)

    print("✅ fetch complete.")


# --------------------------------------------------------------------------- #
# Analysis steps (chunk = dataset)
# --------------------------------------------------------------------------- #
@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with an "
               "mriqc subdataset).",
    "smoke": "Process only the first dataset (fast end-to-end check).",
    "strict": "Raise on missing input or empty extraction instead of warning "
              "(implied by run --smoke; also re-runs datasets whose output exists).",
})
def run_qc_measures(c, dataset=None, smoke=False, strict=False):
    """
    Extract per-run MRIQC QC metrics for each dataset of cneuromod.all.

    Reads only the MRIQC files already present on disk — retrieval is
    ``invoke fetch``'s job, so this step never calls ``datalad get``. Writes one
    tidy table per dataset to output_data/tables/{dataset}.tsv. Datasets whose
    output already exists are skipped — except in ``strict`` mode, where a stale
    table must not mask missing input, so it is re-run.
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
        extract_qc_measures(
            dataset, cneuromod_dir, output_dir, smoke=smoke, strict=strict
        )


@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with a "
               "tsnr subdataset).",
    "smoke": "Process only the first dataset, and only its first run (fast "
             "end-to-end check).",
    "strict": "Raise on missing input or empty extraction instead of warning "
              "(implied by run --smoke; also re-runs datasets whose output exists).",
})
def run_atlas_tsnr(c, dataset=None, smoke=False, strict=False):
    """
    Extract per-run, per-region tSNR for each dataset of cneuromod.all.

    Resamples each functional run's MNI ``stat-tsnr`` statmap onto the shared
    combined atlas (``anat/atlases``) and averages tSNR within each parcel.
    Reads only files already present on disk — retrieval is ``invoke fetch``'s
    job, so this step never calls ``datalad get``. Writes one tidy table per
    dataset to output_data/tables/atlas_tsnr/{dataset}.tsv. Datasets whose output
    already exists are skipped — except in ``strict`` mode, where a stale table
    must not mask missing input, so it is re-run.
    """
    from analysis.atlas_tsnr import extract_region_tsnr
    from analysis.datasets import list_datasets

    cneuromod_dir = _cneuromod_dir(c)
    atlases_dir = cneuromod_dir / "anat" / "atlases"
    output_dir = Path(c.config.get("output_data_dir"))
    names = _select_datasets(dataset, list_datasets(cneuromod_dir, "tsnr"), smoke)

    for dataset in names:
        out = output_dir / "tables" / "atlas_tsnr" / f"{dataset}.tsv"
        if out.exists() and not strict:
            print(f"🫧 Skipping {dataset} atlas_tsnr (output exists)")
            continue
        extract_region_tsnr(
            dataset, cneuromod_dir, output_dir, atlases_dir,
            smoke=smoke, strict=strict,
        )


# --------------------------------------------------------------------------- #
# Composed figure
# --------------------------------------------------------------------------- #
def _figure_paths(c):
    """``(svg, png, panel_sizes_json)`` for the hand-authored montage."""
    svg = Path(c.config.get("figure_svg", "output_data/qa_figure.svg"))
    png = Path(c.config.get("figure_png", "output_data/qa_figure.png"))
    panel_sizes = Path(c.config.get("figures_dir")) / "panel_sizes.json"
    return svg, png, panel_sizes


@task
def run_figure_layout(c):
    """Export the montage's panel geometry to figures/panel_sizes.json.

    Read by the notebooks (see notebooks/figure_style.py) so every placed panel
    renders at exactly the physical size the montage allocates it. Always
    re-run, never skipped: it is cheap, and a box resized in Inkscape must take
    effect on the very next `invoke run`.
    """
    from analysis.figure_layout import write_panel_sizes

    svg, _, panel_sizes = _figure_paths(c)
    write_panel_sizes(svg, panel_sizes)


@task
def export_figure(c):
    """Render the hand-authored montage to output_data/qa_figure.png with Inkscape.

    Tolerant, like the rest of this pipeline: Inkscape is an optional external
    dependency needed only to recompose the final figure, never to reproduce a
    panel, so a missing binary (or a failed export) warns and returns rather
    than failing the run. Skipped when the PNG is already newer than the SVG and
    every panel it links.
    """
    import shutil
    import subprocess

    from analysis.figure_layout import read_panel_sizes

    svg, png, _ = _figure_paths(c)
    dpi = c.config.get("figure_export_dpi", 300)
    if not svg.is_file():
        print(f"⚠️  No montage at {svg} — nothing to export")
        return
    if shutil.which("inkscape") is None:
        print("⚠️  Inkscape not found on PATH — skipping the figure export. "
              f"Install it (https://inkscape.org/release/), or open {svg} and "
              "export the PNG from the GUI.")
        return

    # The montage links its panels by relative path, so the sources to compare
    # against are the SVG itself plus every panel it places.
    figures_dir = Path(c.config.get("figures_dir"))
    sources = [svg] + [figures_dir / name for name in read_panel_sizes(svg)]
    newest_source = max((p.stat().st_mtime for p in sources if p.is_file()), default=0)
    if png.is_file() and png.stat().st_mtime >= newest_source:
        print(f"⏭️  {png} is up to date")
        return

    result = subprocess.run(
        ["inkscape", "--export-type=png", f"--export-filename={png}",
         f"--export-dpi={dpi}", str(svg)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"⚠️  Inkscape export failed ({result.stderr.strip()}) — open {svg} "
              "and export the PNG from the GUI instead.")
        return
    print(f"🖼️  Exported {png} at {dpi} dpi")


# --------------------------------------------------------------------------- #
# Notebooks
# --------------------------------------------------------------------------- #
@task(pre=[run_figure_layout])
def run_notebooks(c):
    """
    Generate QA figures from the metric tables in output_data/ using notebooks.

    `run-figure-layout` runs first because the notebooks size every placed panel
    from the geometry it writes — and `clean-figures` wipes that file along with
    the figures dir it lives in. (`run` calls both explicitly, in the same
    order; this `pre=` only covers invoking `run-notebooks` on its own.)
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
               "in invoke.yaml (i.e. floc).",
    "smoke": "Strict minimal end-to-end test on one functional dataset: implies "
             "--strict, re-runs stale TSVs, and asserts non-empty output at the "
             "end (non-zero exit if nothing is extracted). Defaults --dataset to "
             "`smoke_dataset`.",
    "strict": "Raise on any retrieval/extraction failure instead of warning.",
})
def run(c, dataset=None, smoke=False, strict=False):
    """Full pipeline: check inputs present → qc-measures → figures.

    ``run`` does NOT pull data: it reads only the files ``invoke fetch`` already
    retrieved, and no step calls ``datalad get``. A tolerant production run warns
    and skips (or writes an empty table) for any dataset whose input is not
    present; a ``--strict`` run raises instead. **Run ``invoke fetch`` first.**

    ``--smoke`` turns this into a strict end-to-end test. Because it must exercise
    the whole plumbing (including retrieval), it is the ONE mode that fetches: it
    ``fetch``es its single dataset, runs, and then FAILS LOUDLY (non-zero exit) if
    nothing was extracted. It runs on a dataset that has both functional MRIQC
    data and an upstream avgtsnr map (default `smoke_dataset`, i.e. floc), so an
    empty result unambiguously means the plumbing is broken, not that the dataset
    simply has no BOLD runs (e.g. anat).
    """
    strict = strict or smoke
    if smoke and not dataset:
        dataset = c.config.get("smoke_dataset", "floc")

    if smoke:
        # Smoke is a self-contained end-to-end test, so it fetches its one
        # dataset before running. Every other path is fetch-free: `run` only
        # checks presence, keeping asset gathering (`fetch`) separate from
        # reproduction (`run`). Do NOT add a fetch(c) call to the non-smoke path.
        fetch(c, dataset=dataset)
    else:
        _ensure_superdataset_available(c)
    run_qc_measures(c, dataset=dataset, smoke=smoke, strict=strict)
    run_atlas_tsnr(c, dataset=dataset, smoke=smoke, strict=strict)
    # Panel geometry has to be on disk before the notebooks size their figures
    # against it; the export then recomposes the montage from the fresh panels.
    run_figure_layout(c)
    run_notebooks(c)
    export_figure(c)

    if not smoke:
        print("all analyses completed")
        return

    import pandas as pd

    from analysis.tsnr_maps import SUBJECT_AVG_GLOB

    output_dir = Path(c.config.get("output_data_dir"))
    cneuromod_dir = _cneuromod_dir(c)
    targets = [name.strip() for name in dataset.split(",") if name.strip()]
    for target in targets:
        out = output_dir / "tables" / f"{target}.tsv"
        if not out.exists() or pd.read_csv(out, sep="\t").empty:
            raise Exit(
                f"❌ Smoke test FAILED: no QC rows extracted for {target}", code=1
            )
        avgtsnr_maps = list((cneuromod_dir / target / "tsnr").glob(SUBJECT_AVG_GLOB))
        if not any(path.is_file() for path in avgtsnr_maps):
            raise Exit(
                f"❌ Smoke test FAILED: no avgtsnr map fetched for {target}", code=1
            )
        atlas_out = output_dir / "tables" / "atlas_tsnr" / f"{target}.tsv"
        if not atlas_out.exists() or pd.read_csv(atlas_out, sep="\t").empty:
            raise Exit(
                f"❌ Smoke test FAILED: no atlas_tsnr rows extracted for {target}",
                code=1,
            )
        print(f"✅ Smoke test passed: {target} produced QC rows at {out}, "
              f"has an avgtsnr map fetched under {cneuromod_dir / target / 'tsnr'}, "
              f"and produced atlas_tsnr rows at {atlas_out}")


# --------------------------------------------------------------------------- #
# Clean
# --------------------------------------------------------------------------- #
@task
def clean_qc_measures(c):
    """Remove QC-metric outputs."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "tables/*.tsv")


@task
def clean_atlas_tsnr(c):
    """Remove per-region atlas-tSNR outputs."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "tables/atlas_tsnr/*.tsv")


@task
def clean_figures(c):
    """Remove generated figures and notebook sentinels."""
    from airoh.utils import clean_folder
    clean_folder(c, "figures_dir")


@task
def clean_figure(c):
    """Remove the composed montage PNG and its panel geometry.

    Never the SVG: that one is hand-authored in Inkscape and is a pipeline
    *source*, despite living in output_data/ (its relative image links resolve
    from there).
    """
    _, png, panel_sizes = _figure_paths(c)
    for path in (png, panel_sizes):
        if path.is_file():
            path.unlink()
            print(f"🧹 Removed {path}")


@task(pre=[clean_qc_measures, clean_atlas_tsnr, clean_figures, clean_figure])
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
