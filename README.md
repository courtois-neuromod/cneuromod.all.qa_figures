# CNeuroMod QA Figures

_why don't you have a cup of relaxing jasmine tea?_

This project generates quality-control (QC/QA) figures summarizing data quality
across the [CNeuroMod](https://www.cneuromod.ca/) datasets. It reads from the
`cneuromod.all` Datalad superdataset, computes QA metrics, and renders summary
figures.

It is built on the [`invoke`](https://www.pyinvoke.org/) task runner, with
reusable tasks provided by the [`airoh`](https://pypi.org/project/airoh/)
package. The pipeline goes from a clone of the data to output figures with a few
commands.

---

## ✨ TL;DR

```bash
uv sync
uv run invoke fetch    # symlink/clone cneuromod.all + get MRIQC text files
uv run invoke run      # metrics → figures
```

---

## 🚀 Quick Start

### **Step 1**: Install dependencies

Using [`uv`](https://docs.astral.sh/uv/) (the package manager for this project):

```bash
uv sync
```

This creates a `.venv` and installs all dependencies from `pyproject.toml`,
including the [`datalad`](https://www.datalad.org/) CLI used to retrieve data.

> ⚠️ **git-annex ≥ 10.20230126 is required** on your `PATH`. The `cneuromod.all`
> subdatasets use the annex v10 repository format; an older system `git-annex`
> (e.g. 8.x) makes `datalad get` refuse to fetch content, so image-based steps
> like `run-tsnr-maps` produce empty output and `run --smoke` fails. Install a
> recent one via conda-forge (`conda install -c conda-forge git-annex`) and make
> sure it comes first on `PATH`.

### **Step 2**: Fetch the source data

```bash
uv run invoke fetch
```

The sole data source is the `cneuromod.all` Datalad **superdataset**. `fetch`
makes it available under `source_data/cneuromod.all`:

- **Primary use case — an existing local checkout.** By default `fetch`
  symlinks `../cneuromod.all` (configured via `source:` under `datasets:` in
  `invoke.yaml`). Point it elsewhere with:

  ```bash
  uv run invoke fetch --source /path/to/cneuromod.all
  ```

- **No local checkout?** `fetch` clones the remote superdataset
  (`https://github.com/courtois-neuromod/cneuromod.all`) instead.

Once available, `fetch` then **retrieves the small MRIQC text files the pipeline
reads** — MRIQC `*_bold.json` and `*_timeseries.tsv` — installing each dataset's
`mriqc` subdataset and `datalad get`-ing just those files, so a fresh clone is
ready to `run` offline. It **never** downloads `*.nii.gz` or the large
fMRIPrep/bids content; the whole superdataset is never pulled at once. The
retrieval is tolerant — inaccessible (credentialed) content only warns.

- **Narrow to a slice (optional).** Passing `--dataset`, `--subject`, and/or
  `--session` (each a comma-separated list) restricts the retrieval to that
  slice instead of all datasets:

  ```bash
  uv run invoke fetch --dataset hcptrt --subject 01 --session 001
  uv run invoke fetch --dataset hcptrt,friends --subject 01,03
  ```

### **Step 3**: Run the full pipeline

```bash
uv run invoke run
```

Runs the analysis in order (ensure `cneuromod.all` available → `run-qc-measures`
→ `run-tsnr-maps` → `run-notebooks`). Unlike `fetch`, `run` does **not** bulk-prefetch — it only
makes the superdataset available, then each step `datalad get`s just its own
dataset's files on demand. Run `invoke fetch` first to gather everything up
front; `run` alone still works on a fresh clone. Steps that already produced
output are skipped, so re-running only recomputes what is missing. To force a
full rerun:

```bash
uv run invoke clean
uv run invoke run
```

For a fast end-to-end check that exercises the whole pipeline on a single
dataset known to have functional MRIQC data (default `hcptrt`, configurable via
`smoke_dataset` in `invoke.yaml`, overridable with `--dataset`):

```bash
uv run invoke run --smoke                 # strict check on hcptrt
uv run invoke run --smoke --dataset floc  # a different functional dataset
```

With `--smoke`, `run` becomes **strict**: it exits non-zero if nothing is
retrieved or extracted, so it genuinely tests the plumbing rather than quietly
producing an empty table. You can also scope any run to specific datasets with
`--dataset` (comma-separated), e.g. `uv run invoke run --dataset hcptrt,floc`.

### **Step 4**: Clean

```bash
uv run invoke clean              # remove all computed outputs
uv run invoke clean-qc-measures  # remove one step's outputs
uv run invoke clean-source       # remove the fetched cneuromod.all (symlink)
```

---

## 🧰 Task Overview

The list below should match `invoke --list`.

| Task                | Description                                                        |
| ------------------- | ------------------------------------------------------------------ |
| `fetch`             | Make `cneuromod.all` available, then retrieve the small MRIQC text files (`*_bold.json`, `*_timeseries.tsv`); narrow with `--dataset`/`--subject`/`--session` |
| `run-qc-measures`   | Extract per-run MRIQC metrics per dataset (`--dataset`); skips datasets already done |
| `run-tsnr-maps`     | Assemble average tSNR brain maps per subject and per dataset (`--dataset`); fetches only the small avgtsnr MNI `.nii.gz`; skips datasets already done |
| `run-notebooks`     | Execute notebooks, saving QA figures to `output_data/figures/`     |
| `run`               | Full pipeline (ensure `cneuromod.all` available → `run-qc-measures` → `run-tsnr-maps` → `run-notebooks`); no bulk prefetch — each step gets its own files on demand; scope with `--dataset`, or `--smoke` for a strict minimal end-to-end test (default `hcptrt`, fails non-zero if nothing is extracted) |
| `clean`             | Remove all computed outputs                                        |
| `clean-qc-measures` | Remove QC-metric tables                                            |
| `clean-tsnr-maps`   | Remove tSNR brain-map outputs                                      |
| `clean-figures`     | Remove generated figures and notebook sentinels                   |
| `clean-source`      | Remove all fetched source data                                     |
| `clean-cneuromod`   | Remove the fetched `cneuromod.all` superdataset (symlink or clone) |

Use `invoke --list` or `invoke --help <task>` for full descriptions.

---

## 🧠 Design principles

- **Analysis in code, visualization in notebooks.** Heavy computation lives in
  `analysis/` Python modules run by `invoke` tasks; notebooks only read results
  from `output_data/` and produce figures.
- **Idempotent steps.** Each `run-{name}` task skips chunks whose output already
  exists, so `invoke run` can be re-run cheaply while developing a later step.
- **Mirrored clean tasks.** Every `run-{name}` has a matching `clean-{name}`.
- **Smoke test.** `run --smoke` runs a strict minimal end-to-end pass on a known
  functional dataset and fails loudly (non-zero) if nothing is extracted, while
  the plain `run` stays tolerant of partly-public data.
- **Data retrieved on demand.** `cneuromod.all` is huge; only the files each step
  needs are pulled with `datalad get`.

---

## 📁 Folder Structure

| Folder / File  | Description                                                                   |
| -------------- | ---------------------------------------------------------------------------- |
| `analysis/`    | Pure Python analysis logic, called by invoke tasks                           |
| `notebooks/`   | Jupyter notebooks for visualization (one per figure)                         |
| `source_data/` | The `cneuromod.all` superdataset — see [`source_data/CONTENT.md`](source_data/CONTENT.md) |
| `output_data/` | Generated metrics and figures — see [`output_data/CONTENT.md`](output_data/CONTENT.md) |
| `tasks.py`     | Project-specific invoke tasks                                                |
| `invoke.yaml`  | Config: paths and the `cneuromod.all` dataset source                         |

---

## 🧹 Linting

This project uses [`ruff`](https://docs.astral.sh/ruff/). Run it before
committing:

```bash
uv run ruff check .
```

---

### Uncle Airoh

When working in this project, Claude Code responds as **Uncle Airoh**: patient,
warm, and wise. Errors are explained gently, tradeoffs are framed as learning
opportunities, and a calming cup of jasmine tea is always on offer.
