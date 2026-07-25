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
uv run invoke fetch    # symlink ../cneuromod.all (or clone the remote)
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

Either way, **file content is retrieved on demand** by the analysis steps
(`datalad get`) — the whole superdataset is never downloaded at once.

- **Prefetch a slice (optional).** Passing `--dataset`, `--subject`, and/or
  `--session` (each a comma-separated list) additionally pulls just the small
  text files — MRIQC `*_bold.json` — for that slice, so later steps run offline.
  No `*.nii.gz` is ever retrieved.

  ```bash
  uv run invoke fetch --dataset hcptrt --subject 01 --session 001
  uv run invoke fetch --dataset hcptrt,friends --subject 01,03
  ```

### **Step 3**: Run the full pipeline

```bash
uv run invoke run
```

Runs the analysis in order (`fetch → run-qc-measures → run-notebooks`).
Steps that already produced output are skipped, so re-running only recomputes
what is missing. To force a full rerun:

```bash
uv run invoke clean
uv run invoke run
```

For a fast end-to-end check that exercises the whole pipeline on a single
dataset known to have functional MRIQC data (default `hcptrt`, configurable via
`smoke_dataset` in `invoke.yaml`, overridable with `--dataset`):

```bash
uv run invoke run-smoke                 # strict check on hcptrt
uv run invoke run-smoke --dataset floc  # a different functional dataset
```

Unlike the full `run`, the smoke test is **strict**: it exits non-zero if
nothing is retrieved or extracted, so it genuinely tests the plumbing rather
than quietly producing an empty table.

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
| `fetch`             | Make `cneuromod.all` available; optionally prefetch a `--dataset`/`--subject`/`--session` text-file slice |
| `run-qc-measures`   | Extract per-run MRIQC metrics per dataset; skips datasets already done |
| `run-notebooks`     | Execute notebooks, saving QA figures to `output_data/figures/`     |
| `run`               | Full pipeline (`fetch → run-qc-measures → run-notebooks`)          |
| `run-smoke`         | Strict minimal end-to-end pass on a functional dataset (`--dataset`, default `hcptrt`); fails non-zero if nothing is extracted |
| `clean`             | Remove all computed outputs                                        |
| `clean-qc-measures` | Remove QC-metric tables                                            |
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
- **Smoke test.** `run-smoke` runs a strict minimal end-to-end pass on a known
  functional dataset and fails loudly (non-zero) if nothing is extracted, while
  the full `run` stays tolerant of partly-public data.
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
