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
  generic `fetch_data` template task): file content is pulled **on demand** by the
  analysis steps via `datalad get`, never all at once. The new structure nests
  derivatives per dataset: `{dataset}/bids`, `{dataset}/mriqc`, `{dataset}/fmriprep`,
  `{dataset}/tsnr`, … Optionally, `fetch --dataset/--subject/--session` (each a
  comma-separated list) prefetches the same small text files (MRIQC
  `*_bold.json`) for a chosen slice up front — see
  `analysis/prefetch.py`; still never `.nii.gz`.
- **Chunk unit: `dataset`.** Each `run-{name}` task processes one CNeuroMod
  dataset at a time (writing one TSV per dataset), auto-discovering datasets from
  `cneuromod.all` (`analysis/datasets.py`), exposing a `datasets=` selector and a
  `smoke` flag (first dataset only), and skipping datasets whose output exists.
- **`run-smoke` is a real test — strict, not tolerant.** The production pipeline
  (`run`, `run-qc-measures`) is deliberately *tolerant* of partly-public data:
  inaccessible participants only warn, and an empty result writes an empty table.
  `run-smoke` is the opposite: it threads a `strict=True` flag through
  `_ensure_marker_submodule` → `install_subdataset` → `extract_qc_measures`, so a
  failed submodule install or a zero-row extraction **raises** (non-zero exit).
  It runs on a single dataset that genuinely has functional MRIQC data
  (`smoke_dataset` in `invoke.yaml`, default `hcptrt`, overridable with
  `--dataset`) — never blindly the first dataset alphabetically, which is `anat`
  (anatomical-only, no BOLD → empty by nature). In strict mode `run-qc-measures`
  also re-runs a dataset whose TSV already exists, so a stale file can't mask a
  retrieval failure. Note: the per-file content `datalad get` stays best-effort
  even under strict (JSONs may already be on disk while a fresh `get` fails on a
  stale git-annex); the strict gate is the final row count, not the fetch.
- **One analysis path** (in `analysis/`, mirroring `cneuromod_qc`):
  - `run-qc-measures` → `analysis/qc_measures.py`: per-run image-quality metrics
    read **from MRIQC BOLD JSONs only** (`{dataset}/mriqc/**/*_bold.json`) — a
    deliberate choice to avoid installing/fetching the large fMRIPrep derivatives.
    Metrics: `fd_mean`, `tsnr`, `snr`, `gsr_*`, `dvars_*`, `size_t`, … →
    `output_data/qc_measures/{dataset}.tsv`.
- **Derivative folders are nested Datalad subdatasets.** Every `{dataset}/{marker}`
  (`bids`, `mriqc`, `fmriprep`, `tsnr`, …) is a Datalad subdataset nested *inside*
  the per-`{dataset}` subdataset of `cneuromod.all`, present on disk as an empty
  mountpoint until installed. Each `run-{name}` task first installs the subdataset
  it needs via `install_subdataset` (`analysis/datalad_utils.py`), called at the
  **task layer** in `tasks.py` (`_ensure_marker_submodule`). This runs
  `datalad get -n` (no content): datalad installs the intermediate `{dataset}`
  subdataset and the nested `{marker}` in one call — plain `git submodule` cannot
  reach a submodule nested inside another submodule — while leaving large sibling
  subdatasets like `stimuli` alone (non-recursive). Tolerant like `datalad_get`
  (never raises). Then the `analysis/` step globs the installed tree and
  `datalad get`s the small text content. Skipping this install is why a fresh
  checkout would silently produce empty metric tables.
- **Tolerant `datalad get`** (`analysis/datalad_utils.py`): CNeuroMod data is only
  partly public and content lives on credentialed special remotes, so `datalad get`
  can partially fail (e.g. participants without a public-data agreement, or an
  environment without the right auth). The helper only fetches the small text
  files it needs (MRIQC JSONs — never `.nii.gz`), never raises, retries once
  over HTTPS, and lets each step proceed with whatever content is present.
- **Notebook figures live in `output_data/figures/{notebook_stem}/`** (set via
  `figures_dir` in `invoke.yaml`). This folder doubles as airoh's per-notebook
  "already ran" sentinel, so it must NOT collide with a data dir name — keep the
  metric tables under `output_data/qc_measures/`, distinct from the notebook stems.

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

**Testing:** The smoke test (`invoke run-smoke`) is the baseline end-to-end check. Add unit tests in `tests/` using the project's chosen test framework when a function contains non-trivial logic, has edge cases the smoke test won't catch, or is shared across multiple steps. Unit tests are optional for simple glue/orchestration code but encouraged for any pure transformation or computation logic in `analysis/`. The test framework and directory are configured during `init`.

**Template cleanup:** When starting a new project from this template, remove the demo code before adding project-specific work:
- Delete `run_simulation` from `tasks.py` and remove it from the `pre=` chains on `run_notebooks` and `run`
- Delete `analysis/simulation.py` (and the `analysis/` folder if it stays empty)
- Clear or replace `source_data/CONTENT.md` and `output_data/CONTENT.md` with project-specific descriptions
- Update `invoke.yaml` (`files:`, paths) for the new project's data sources

**Adding a new analysis step:** add a function to `analysis/`, add a `run-{name}` task and a matching `clean-{name}` task in `tasks.py`, wire both into the top-level `run` and `clean` tasks via `pre=` chains, and create or extend a notebook in `notebooks/` for visualization.

**Evolving CLAUDE.md:** Keep this file current as the project grows. It should always reflect the actual scope of the project — what it does, what data it uses, and what analysis steps it contains. When adding or removing a task, rename a folder, or change the pipeline structure, update CLAUDE.md in the same commit. Stale guidance here misleads future AI sessions and collaborators alike.

**Keeping README.md current:** README.md is the user-facing documentation for this project. Any structural or workflow change — new tasks, renamed folders, updated commands, new dependencies — must be reflected there in the same commit. The task list in README.md should match `invoke --list` exactly; if a task is added or removed, update README.md accordingly. For data folder contents, point to `source_data/CONTENT.md` and `output_data/CONTENT.md` rather than duplicating their content inline.
