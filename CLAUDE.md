# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**CNeuroMod QA Figures** generates quality-control (QC/QA) figures summarizing
data quality across the [CNeuroMod](https://www.cneuromod.ca/) datasets. It reads
from the `cneuromod.all` Datalad superdataset, extracts per-run QC metrics, and
renders summary figures. The logic is adapted from Basile Pinsard's
[`cneuromod_qc`](https://github.com/courtois-neuromod/cneuromod_qc), ported to the
new nested `cneuromod.all` structure and generalized to all functional datasets.

It is built on the [`invoke`](https://www.pyinvoke.org/) task runner (structured
from the `airoh-mini` template). The `airoh` pip package provides reusable invoke
tasks; this repo customizes them via `tasks.py` and `invoke.yaml`. Package
manager: **uv** (Python pinned to 3.12 via `.python-version` for pybids/ptitprince
compatibility). Linter: **ruff** (`uv run ruff check .`). No test framework.

### Project-specific conventions

- **Sole data source: the `cneuromod.all` Datalad superdataset.** The `fetch`
  task in `tasks.py` makes it available under `source_data/cneuromod.all` — by
  default a **symlink** to an existing local checkout (`../cneuromod.all`, set via
  `source:` under `datasets:` in `invoke.yaml`, overridable with
  `invoke fetch --source /path`), or a **clone** of the remote when no local
  checkout exists. This is a deliberate, project-specific `fetch` (not the
  generic `fetch_data` template task). The new structure nests derivatives per
  dataset: `{dataset}/bids`, `{dataset}/mriqc`, `{dataset}/fmriprep`,
  `{dataset}/tsnr`, … After making the superdataset available, `fetch`
  **retrieves every small file the pipeline reads** — installing each dataset's
  `mriqc` and `tsnr` subdatasets and `datalad get`-ing (a) the MRIQC
  `*_bold.json` and `*_timeseries.tsv` text files, and (b) the per-subject
  `sub-*_space-MNI152NLin2009cAsym_stat-avgtsnr_statmap.nii.gz` maps — so a fresh
  clone is fully ready to `run` offline. Those avgtsnr maps are the **only**
  `.nii.gz` it pulls (never run-level, `T1w`, or fMRIPrep content).
  `fetch --dataset/--subject/--session` (each a comma-separated list) narrows this
  retrieval to a chosen slice; with no filter it covers every dataset — see
  `analysis/prefetch.py`. The retrieval is tolerant (inaccessible content only
  warns).
- **Asset gathering (`fetch`) is separate from reproduction (`run`) — and `run`
  NEVER pulls.** This split is load-bearing: `run` reads only what is already on
  disk and **no `run-*` step calls `datalad get` or installs a subdataset**. A
  plain `run` only ensures the superdataset is *available* via
  `_ensure_superdataset_available` (the cheap symlink/clone half of `fetch`), then
  each step globs its dataset's files and processes whatever is present —
  tolerant path warns-and-skips (or writes an empty table) for a dataset whose
  input was never fetched, pointing the user at `invoke fetch`. `invoke fetch` is
  the do-it-once bulk gather; `invoke run` is fast and offline. **Do not
  reintroduce any `datalad get`/`install_subdataset` into the `run-*` steps or a
  `fetch(c)` call into the non-smoke `run` path** — that on-demand re-pulling was
  removed on purpose (it made every `run` slow). The one exception is `run
  --smoke` (see below), which fetches its single dataset to stay a self-contained
  end-to-end test.
- **Chunk unit: `dataset`.** Each `run-{name}` task processes one CNeuroMod
  dataset at a time (writing one TSV per dataset), auto-discovering datasets from
  `cneuromod.all` (`analysis/datasets.py`), exposing a `--dataset` selector
  (comma-separated) and a `smoke` flag (first dataset only), and skipping
  datasets whose output exists. `run` itself also takes `--dataset`, forwarding
  it to `run-qc-measures`.
- **`run --smoke` is a real test — strict, and the one `run` that fetches.** The
  production pipeline (plain `run`, `run-qc-measures`) is deliberately *tolerant*
  of partly-public / not-yet-fetched data: a missing input only warns, and an
  empty result writes an empty table. `run --smoke` is the opposite. To be a
  genuine end-to-end plumbing test it first **`fetch`es its single dataset**
  (retrieval included), then runs `--strict`: `--smoke` implies `--strict`,
  threading `strict=True` into `extract_qc_measures` so a zero-row extraction
  **raises** (non-zero exit), and `run` asserts a non-empty TSV **and** that the
  source `tsnr` derivative has at least one fetched avgtsnr map on disk. It runs
  on a single dataset that both has functional MRIQC data and ships an upstream
  `stat-avgtsnr` map (`smoke_dataset` in `invoke.yaml`, default `floc`, the
  `--dataset` default under `--smoke`) — never blindly the first dataset
  alphabetically, which is `anat` (anatomical-only, no BOLD → empty by nature),
  and **not** `hcptrt` (functional MRIQC but no `avgtsnr`, so there is nothing
  for the tsnr_maps notebook to render). In strict mode `run-qc-measures` also
  re-runs a dataset whose output exists, so a stale file can't mask a missing
  input.
- **Two analysis paths** (in `analysis/`, mirroring `cneuromod_qc`):
  - `run-qc-measures` → `analysis/qc_measures.py`: per-run image-quality metrics
    read **from MRIQC only** (`{dataset}/mriqc/**/*_bold.json` plus the sibling
    `*_timeseries.tsv`) — a deliberate choice to avoid installing/fetching the
    large fMRIPrep derivatives. Metrics: `fd_mean`, `tsnr`, `snr`, `gsr_*`,
    `dvars_*`, `size_t`, … plus `fd_prop_gt02`/`fd_prop_gt05` (proportion of
    volumes with FD > 0.2 / 0.5 mm, computed from the `framewise_displacement`
    column of the MRIQC `*_timeseries.tsv` — *not* the BIDS sidecar, which holds
    no FD data) → `output_data/tables/{dataset}.tsv`.
  - tSNR **brain maps** (`notebooks/tsnr_maps.ipynb`, no `analysis/` step or
    `run-*` task — there is nothing to compute-and-persist, so it lives entirely
    in the notebook). It reads the **upstream per-subject `stat-avgtsnr` map**
    each `{dataset}/tsnr` derivative ships directly from
    `source_data/cneuromod.all/{dataset}/tsnr/` (never recomputed from run-level
    maps, never copied into `output_data/`) and averages subjects **in memory**
    for the dataset-level panel (resampled to a common grid via
    `nilearn.image.resample_to_img`, `np.nanmean`) — nothing is written except
    the rendered PNG montages. A **grand-average panel**
    (`all_datasets_avgtsnr.png`) pools every subject from every light-v1
    dataset into one further mean, each subject weighted equally regardless of
    how many subjects its dataset contributes (not an average-of-dataset-
    averages, which would instead weight each dataset equally). It shares the
    same `robust_vmax` ceiling and the same anchor-cut-coords-on-the-average
    approach as the per-dataset panels. `analysis/tsnr_maps.py` now holds only the
    `SPACE`/`SUBJECT_AVG_GLOB` constants shared between the notebook and
    `analysis/prefetch.py`. Montages are volumetric (nilearn) — *not* a cortical
    surface, which would discard subcortex/cerebellum and smooth the
    ventral/orbitofrontal dropout tSNR QA must show. The `tsnr` scalar column in
    `qc_measures` (an MRIQC IQM) is a different, unrelated thing from these
    voxelwise statmaps.
    - **One fixed set of cut coordinates and color ranges for every panel** —
      every dataset, every subject, the grand average, and every coverage
      panel (`CUT_COORDS`, `TSNR_VMIN`/`TSNR_VMAX`, `COVERAGE_VMIN`/
      `COVERAGE_VMAX` in the notebook). Earlier versions picked slices
      per-dataset via `nilearn.plotting.find_cut_slices` on that dataset's
      average and computed a per-run 98th-percentile `vmax`; both were
      replaced with hard-coded constants so every panel across every dataset
      is sliced and colored identically and stays numerically comparable
      across notebook re-runs, not just within one dataset.
      `CUT_COORDS = (-54, -42, -28.5, -14.5, -0.5, 19.5, 33.5, 47.5, 59.5,
      71.5)` was chosen once by running `find_cut_slices(grand_average,
      direction="z", n_cuts=8)` (which gave the 8 values from -28.5 up) and
      extending it with two fixed inferior slices (-54, -42): `find_cut_slices`
      alone is cortex-heavy and reliably misses the cerebellum (at best it
      grazes its superior edge), so those two are hard-coded in rather than
      left to chance. `TSNR_VMIN`/`TSNR_VMAX` are fixed at `0`/`50` and
      `COVERAGE_VMIN`/`COVERAGE_VMAX` at `0`/`1` (coverage is already a
      fraction) rather than a computed ceiling.
    - **Light v1 — only datasets that ship an upstream `stat-avgtsnr`** (floc,
      retinotopy, things at the time of writing). Datasets with only run-level
      `stat-tsnr` maps (hcptrt, friends, …) are **skipped with a warning** in the
      notebook: computing their subject-average from run-level maps means
      fetching many full-res `.nii.gz` (a large footprint), deliberately
      deferred to a future step.
    - **Scoped `.nii.gz` exception (fetched in `fetch`, read in the notebook).**
      The avgtsnr maps are the *only* image content the pipeline pulls, and that
      pull lives in `fetch`/`analysis/prefetch.py` — the notebook only reads what
      is present. `fetch` globs and `datalad get`s **only**
      `sub-*_space-MNI152NLin2009cAsym_stat-avgtsnr_statmap.nii.gz` (one small map
      per subject) — never run-level, never `T1w`, never fMRIPrep. Do not widen
      this glob (`SUBJECT_AVG_GLOB` in `analysis/tsnr_maps.py`) without cause.
    - **Requires git-annex ≥ 10.20230126** on `PATH` (the cneuromod.all
      subdatasets are annex v10 format). `fetch` is where fresh annexed content
      (the avgtsnr `.nii.gz`) is retrieved, so an old git-annex (e.g. Ubuntu apt's
      8.x) makes that `datalad get` refuse and every map come back empty — and
      then `run --smoke` (which fetches first) fails at the avgtsnr-presence
      assertion. This is now pinned as a project dependency: the `git-annex`
      PyPI package bundles a recent standalone binary into the venv, so `uv run`
      guarantees a v10 on `PATH`. Running outside `uv run` with only an old
      system git-annex is a real environment signal, not a code bug.
    - **Coverage panels** (`{dataset}_coverage.png`, `all_datasets_coverage.png`)
      complement the continuous tSNR panels above with a binary QA signal:
      each subject's map is thresholded at raw `tsnr > 30` (dimensionless
      scale, ~0–150 in practice — a fraction like 0.2/0.3 is meaningless
      here and left the panel showing solid "covered" almost everywhere) before
      averaging, turning "how good is signal" into "fraction of subjects with
      any usable signal at this voxel" — a clearer view of total-dropout
      regions (e.g. ventral/orbitofrontal, ventral putamen) than a dim
      continuous value. **The threshold alone is not enough**: background/
      skull voxels can still clear even a real tSNR threshold from residual
      structure/noise, so the averaged fraction is also zeroed outside the
      **ICBM152 whole-brain mask** (nearest-neighbor resampled to each map's
      grid) before plotting. Computed the same
      light-v1/in-memory/anchor-cut-coords way as the tSNR panels (same
      `dataset_cut_coords`/`grand_average_cut_coords`), but plotted on an
      explicit **ICBM152 2009 MNI template** background (`nilearn.datasets.
      fetch_icbm152_2009` — nilearn's asymmetrical ICBM152 2009 release a,
      *not* the exact `MNI152NLin2009cAsym`/release-c template fMRIPrep uses;
      close enough for a visual coverage overlay, not a claim of voxel-exact
      alignment) rather than `plot_stat_map`'s implicit default, so
      coverage/dropout regions are anatomically legible. The T1 template and
      brain mask are fetched together (one `fetch_icbm152_2009` call) once
      into `source_data/nilearn/` by the new `fetch-mni152` invoke task
      (`analysis/mni152.py`'s `fetch_mni152_templates`, wired into the
      umbrella `fetch`, never re-downloaded by `run`); the notebook
      duplicates the same `fetch_icbm152_2009` call locally rather than
      importing `analysis/mni152.py` (nbconvert runs with `notebooks/` as the
      cwd, so `analysis` is not importable there — the same reason `SPACE`/
      `SUBJECT_AVG_GLOB` are duplicated rather than imported) and skips the
      coverage cells with a warning if the template isn't cached yet.
- **Derivative folders are nested Datalad subdatasets — installed by `fetch`.**
  Every `{dataset}/{marker}` (`bids`, `mriqc`, `fmriprep`, `tsnr`, …) is a Datalad
  subdataset nested *inside* the per-`{dataset}` subdataset of `cneuromod.all`,
  present on disk as an empty mountpoint until installed. **`fetch`** installs the
  ones the pipeline needs (`mriqc`, `tsnr`) via `install_subdataset`
  (`analysis/datalad_utils.py`), called through the `_ensure_marker_submodule`
  callback `prefetch_slice` receives from `tasks.py`. This runs `datalad get -n`
  (no content): datalad installs the intermediate `{dataset}` subdataset and the
  nested `{marker}` in one call — plain `git submodule` cannot reach a submodule
  nested inside another submodule — while leaving large sibling subdatasets like
  `stimuli` alone (non-recursive). Tolerant like `datalad_get` (never raises).
  `run` does **not** install anything: skipping `fetch` is why `run` then warns
  "no … present" and produces empty output for that dataset.
- **Tolerant `datalad get`** (`analysis/datalad_utils.py`): CNeuroMod data is only
  partly public and content lives on credentialed special remotes, so `datalad get`
  can partially fail (e.g. participants without a public-data agreement, or an
  environment without the right auth). Used only by `fetch`/`prefetch` (never by a
  `run-*` step): it fetches the small files the pipeline needs (MRIQC text plus the
  scoped avgtsnr `.nii.gz`), never raises, retries once over HTTPS, and lets the
  gather proceed with whatever content is reachable.
- **`fetch` is incremental — it skips what it already knows about.** A repeat
  `invoke fetch` (the normal way to pick up new upstream assets) must not
  redo work it already did. Three layers of "already have this, skip it"
  checks make this true, all added because the naive version — unconditionally
  re-invoking `datalad` for every dataset/marker/file on every run — made a
  routine "check for new files" fetch take as long as a from-scratch clone:
  - `install_subdataset` (`analysis/datalad_utils.py`) skips the `datalad`
    subprocess entirely once `{dataset}/{marker}/.git` already exists.
  - `_prefetch_target` (`analysis/prefetch.py`) never re-requests a file whose
    content is already on disk (`p.is_file()`).
  - **Known-failed files are remembered** (`analysis/fetch_state.py`,
    `source_data/.fetch_failures.json`, gitignored — local environment state,
    not a pipeline output): some CNeuroMod content lives only on credentialed
    remotes a given environment can never reach (no SSH key, no special-remote
    auth), so a broken-symlink file that failed once will fail identically on
    every future attempt, at a real per-file cost (git-annex trying every
    configured remote, ~3s/file in practice). The cache records failures per
    root-relative path and is refreshed every fetch: a file that newly
    succeeds is dropped from it, a file that newly fails is added. **By
    default every fetch still retries every previously-failed file** — access
    can be granted later, and a silently-stale skip would then hide genuinely
    new content forever, which is a worse failure mode than an occasional slow
    fetch. Pass `invoke fetch --skip-inaccessible` to instead skip anything in
    the cache — worthwhile once you've confirmed a file is permanently out of
    reach (e.g. a dataset like the smoke test's `gamepad` example, whose MRIQC
    content is not accessible in a given environment) and don't want to keep
    paying its retrieval cost on every routine fetch.
- **Notebook figures live in `output_data/figures/{notebook_stem}/`** (set via
  `figures_dir` in `invoke.yaml`). This folder doubles as airoh's per-notebook
  "already ran" sentinel, so it must NOT collide with a data dir name — keep the
  metric tables under `output_data/tables/`, distinct from the notebook stems.
- **`output_data/tables/` and `output_data/figures/` are git-tracked.** Now that
  no step writes NIfTI under `output_data/` (tSNR montages read source_data and
  persist nothing but the PNG), the remaining outputs are small and diffable, so
  `output_data/.gitignore` tracks them instead of ignoring the whole folder. Keep
  a `*.nii.gz` guard line so a stray large binary can never be committed there.

## Persona

Respond as Uncle Airoh: patient, warm, and wise. Assume the user may be new to coding. Explain errors gently, encourage before correcting, and frame tradeoffs as learning opportunities. When things get heated, offer a calming cup of jasmine tea.

## Setup

```bash
# uv (recommended):
uv sync

# pip:
pip install -r requirements.txt

# conda:
conda env create -n airoh_env -f environment.yml && conda activate airoh_env
```

## Common Commands

With `uv`:
```bash
uv run invoke fetch           # Download source data
uv run invoke run             # Full pipeline (project-specific pre= chain)
uv run invoke run-notebooks   # Execute notebooks, save figures to output_data/
uv run invoke clean           # Remove output_data/ contents
uv run invoke --list          # Show all available tasks
```

Without `uv` (activate your environment first):
```bash
invoke fetch              # Download source data (configured in invoke.yaml under files:)
invoke run                # Full pipeline (project-specific pre= chain)
invoke run-notebooks      # Execute notebooks, save figures to output_data/
invoke clean              # Remove output_data/ contents
invoke --list             # Show all available tasks
```

## Architecture

**Always read `tasks.py` first** before proposing or implementing any pipeline change — it is the authoritative source of what tasks exist, how they are wired, and what parameters they accept.

**Execution flow:** `invoke run` triggers the project's analysis pipeline via `pre=` dependencies declared in `tasks.py`. The three permanent tasks — `fetch`, `run`, `clean` — are always present; intermediate steps are project-specific.

**Fetching data — download or symlink:** each data asset in `files:` gets its own `fetch-{name}` task wrapping `airoh.acquisition.fetch_data`, which makes the asset available in one of two ways: **download** from its `url` (default), or **symlink** to already-present data when a source path is given — via `invoke fetch-{name} --source /path` (add `--copy` for a real copy) or a per-asset `source:` key in `invoke.yaml`. The umbrella `fetch` task calls every `fetch-{name}` and exposes a per-asset `--{name}-source` flag that it routes to the matching one. This avoids re-downloading data that already lives on disk (a shared dataset, a sibling repo). Symlinks handle both files and whole directories, and the operation is idempotent. When wiring fetch tasks for a new project, prefer `fetch_data` over the lower-level `download_data`.

**One asset, one `--source`:** `fetch_data`'s `source` is a single path bound to the single asset named in the call — never a root directory joined with each asset's filename. That is why each asset gets its own `fetch-{name}` task with its own `--source`, and the umbrella `fetch` routes named `--{name}-source` flags rather than one shared `--source`. Do **not** forward a single shared `--source` to several `fetch_data` calls: it links every asset to the same path and fails silently, printing a success line per asset and exiting 0.

**Datalad datasets:** `--source` symlinks/copies a plain file or folder and does not run `datalad get`. Symlinking a datalad dataset exposes only content that is already present (un-fetched files are broken symlinks), and `--copy` raises on those un-fetched files. For a datalad dataset use `airoh.datalad.get_data` (configured under a `datasets:` section in `invoke.yaml`), not `fetch_data --source`; use `airoh.acquisition.ensure_submodule` for a plain git submodule.

- `invoke.yaml` — all path and data config (`output_data_dir`, `source_data_dir`, `notebooks_dir`, `files:` for data assets — each with `output_file` plus `url` to download and/or `source` to symlink)
- `tasks.py` — project-specific invoke tasks; imports reusable tasks from `airoh` (`airoh.acquisition` for data fetching, `airoh.utils` for general helpers)
- `analysis/` — pure Python analysis logic, called by tasks in `tasks.py`
- `notebooks/` — Jupyter notebooks executed by `run_notebooks` via `airoh.utils.run_notebooks`; notebooks receive `OUTPUT_DATA_DIR` and `SOURCE_DATA_DIR` as environment variables
- `source_data/CONTENT.md` and `output_data/CONTENT.md` — authoritative docs for what each data folder contains; update these when data assets change, do not duplicate their content elsewhere

**Analysis vs. notebooks:** Heavy computation belongs in `analysis/` Python code, invoked by `run-{name}` tasks, which write results to `output_data/`. Notebooks are for visualization only — they read from `output_data/` and produce figures. This keeps notebooks fast and focused.

**Idempotent tasks:** Each `run-{name}` task must check whether its outputs already exist and skip execution if they do. This means `invoke run` can be called repeatedly during development of a later step — earlier steps are skipped automatically. To force a full rerun, call `invoke clean` first, then `invoke run`.

**Task naming conventions:**
- Fetch tasks are named `fetch-{name}` (e.g. `fetch-papers`), one per data asset; the umbrella `fetch` calls them all and routes a `--{name}-source` flag to each.
- Analysis tasks are named `run-{name}` (e.g. `run-preprocessing`, `run-model`).
- Cleaning tasks mirror them: `clean-{name}` removes only the outputs of the corresponding step.
- The top-level `clean` task calls all `clean-{name}` tasks in sequence.
- The top-level `run` task wires all steps together via `pre=` chains in `tasks.py`.

**Task parameters:** `run-{name}` tasks should expose chunk or subset parameters (e.g. a subject ID, a chunk index) so that individual pieces can be rerun in isolation. They should also support a `smoke` flag for a fast minimal run useful for testing the pipeline end-to-end without running the full analysis.

## Code style

**Module and function size:** Each module in `analysis/` covers a single concern; if a file grows past ~200 lines, consider splitting it. Each function should do one thing — aim for under ~30 lines; longer is a signal to extract a helper.

**Naming:** Prefer self-explanatory names over brevity: `n_subjects` not `n`, `output_path` not `p`, `group_means` not `gm`. Avoid abbreviations unless universally known in the domain (`df` for a DataFrame is fine).

**Linting:** The project linter and its configuration are chosen during `init` and stored in `pyproject.toml`. Run it before committing. Never disable a lint rule without a comment explaining why.

**Testing:** The smoke test (`invoke run --smoke`) is the baseline end-to-end check. Add unit tests in `tests/` using the project's chosen test framework when a function contains non-trivial logic, has edge cases the smoke test won't catch, or is shared across multiple steps. Unit tests are optional for simple glue/orchestration code but encouraged for any pure transformation or computation logic in `analysis/`. The test framework and directory are configured during `init`.

**Template cleanup:** When starting a new project from this template, remove the demo code before adding project-specific work:
- Delete `run_simulation` from `tasks.py` and remove it from the `pre=` chains on `run_notebooks` and `run`
- Delete `analysis/simulation.py` (and the `analysis/` folder if it stays empty)
- Clear or replace `source_data/CONTENT.md` and `output_data/CONTENT.md` with project-specific descriptions
- Update `invoke.yaml` (`files:`, paths) for the new project's data sources

**Adding a new analysis step:** add a function to `analysis/`, add a `run-{name}` task and a matching `clean-{name}` task in `tasks.py`, wire both into the top-level `run` and `clean` tasks via `pre=` chains, and create or extend a notebook in `notebooks/` for visualization.

**Evolving CLAUDE.md:** Keep this file current as the project grows. It should always reflect the actual scope of the project — what it does, what data it uses, and what analysis steps it contains. When adding or removing a task, rename a folder, or change the pipeline structure, update CLAUDE.md in the same commit. Stale guidance here misleads future AI sessions and collaborators alike.

**Keeping README.md current:** README.md is the user-facing documentation for this project. Any structural or workflow change — new tasks, renamed folders, updated commands, new dependencies — must be reflected there in the same commit. The task list in README.md should match `invoke --list` exactly; if a task is added or removed, update README.md accordingly. For data folder contents, point to `source_data/CONTENT.md` and `output_data/CONTENT.md` rather than duplicating their content inline.
