# Airoh API Reference

Acquisition tasks (`fetch_data`, `download_data`, `ensure_submodule`) live in
`airoh.acquisition`. General utilities (`clean_folder`, `run_notebooks`,
`ensure_dir_exist`) live in `airoh.utils`.

## fetch_data(c, name, source=None, copy=False)

The preferred way to make a data asset available. For each entry in `files:` it
either **downloads** from the entry's `url` (default) or **symlinks** to
already-present data when a source path is given — avoiding a re-download of data
that already lives on disk. Prefer this over the lower-level `download_data`.

**invoke.yaml entry:**
```yaml
files:
  dataset_name:
    url: https://example.com/data.csv        # download source (optional if `source` given)
    output_file: source_data/data.csv
    # source: /path/to/existing/data.csv      # symlink instead of downloading (optional)
```

**tasks.py call (single asset):**
```python
from airoh.acquisition import fetch_data

@task(help={
    "source": "Path to already-present data to symlink instead of downloading.",
    "copy": "Copy the source data instead of symlinking it.",
})
def fetch(c, source=None, copy=False):
    fetch_data(c, "dataset_name", source=source, copy=copy)
```

- Source resolution: the `source` argument → the entry's `source:` key → the entry's `url`.
- Symlinks handle both files and whole directories.
- Idempotent: a link already pointing at the source is left untouched; a real
  file at `output_file` is never clobbered.

**Usage:**
```bash
invoke fetch                              # download
invoke fetch --source /data/existing.csv  # symlink to existing data
invoke fetch --source /data/existing.csv --copy   # real copy instead
```

**One asset, one `--source`.** The `source` argument is a single path bound to
the single asset named in the call — it is **not** a root directory that gets
joined with each asset's filename. Passing one shared `--source` to several
`fetch_data` calls links every asset to that same path, and does so silently:
each call prints a success line and the task exits 0, leaving several
differently-named symlinks pointing at one file.

**With more than one asset, give each its own `fetch-{name}` task** and let the
umbrella `fetch` route a per-asset `--{name}-source` flag to the matching one:

```yaml
files:
  papers:
    url: https://example.com/papers.tsv
    output_file: source_data/papers.tsv
  atlas:
    url: https://example.com/atlas.nii.gz
    output_file: source_data/atlas.nii.gz
```

```python
@task(help={"source": "Existing 'papers' data to link instead of downloading."})
def fetch_papers(c, source=None, copy=False):
    fetch_data(c, "papers", source=source, copy=copy)

@task(help={"source": "Existing 'atlas' data to link instead of downloading."})
def fetch_atlas(c, source=None, copy=False):
    fetch_data(c, "atlas", source=source, copy=copy)

@task(help={"papers_source": "Source path for the papers asset.",
            "atlas_source":  "Source path for the atlas asset."})
def fetch(c, papers_source=None, atlas_source=None, copy=False):
    fetch_papers(c, source=papers_source, copy=copy)
    fetch_atlas(c, source=atlas_source, copy=copy)
```

```bash
invoke fetch-papers --source /data/papers.tsv   # one asset
invoke fetch --papers-source /data/papers.tsv --atlas-source /data/atlas.nii.gz
```

A per-asset `source:` key in `invoke.yaml` sets the default source for that
asset without any command-line flag.

**Datalad datasets need `datalad.get_data`, not `fetch_data --source`.**
`--source` symlinks or copies a plain file/folder; it does not run `datalad
get`. A symlinked datalad dataset resolves only content that is already present
(un-fetched files are broken symlinks), and `--copy` raises on those un-fetched
files. Use `get_data` from `airoh.datalad` with a `datasets:` entry in
`invoke.yaml` for a datalad dataset, and `ensure_submodule` (below) for a plain
git submodule.

## download_data(c, name)

Lower-level primitive used by `fetch_data`: downloads a file from the entry's
`url` only (no symlink option). Reach for `fetch_data` unless you specifically
want URL-only behavior.

```python
from airoh.acquisition import download_data

download_data(c, "dataset_name")
```

- Skips if the output file already exists and is non-empty (idempotent)
- Uses a `.part` temp file for atomic writes

## ensure_submodule(c, path, recursive=True)

Initializes or updates a git submodule at `path` (a common way to bring in an
external dataset tracked as a submodule). Also in `airoh.acquisition`.

```python
from airoh.acquisition import ensure_submodule

ensure_submodule(c, "source_data/my-dataset")
```

## clean_folder(c, name, pattern=None)

Removes files from a directory identified by an `invoke.yaml` key.

- `name`: key in `invoke.yaml` whose value is a directory path (e.g., `"output_data_dir"`)
- `pattern`: glob pattern (e.g., `"*.png"`, `"subjects/*.csv"`); if `None`, removes the entire folder

```python
from airoh.utils import clean_folder

clean_folder(c, "output_data_dir", "*.csv")   # delete all CSVs in output_data/
clean_folder(c, "source_data_dir", "*.tsv")   # delete all TSVs in source_data/
```

## run_notebooks(c, notebooks_path, figures_base, keys)

Executes all `.ipynb` notebooks found in `notebooks_path`. Skips any notebook whose output directory already exists.

```python
from airoh.utils import run_notebooks as airoh_run_notebooks, ensure_dir_exist

@task
def run_notebooks(c):
    notebooks_dir = Path(c.config.get("notebooks_dir"))
    output_dir = Path(c.config.get("output_data_dir")).resolve()
    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, output_dir, keys=["source_data_dir", "output_data_dir"])
```

The `keys` list controls which `invoke.yaml` paths are passed to notebooks as environment variables (`SOURCE_DATA_DIR`, `OUTPUT_DATA_DIR`).

## ensure_dir_exist(c, name)

Creates the directory referenced by an `invoke.yaml` key if it does not exist.

```python
ensure_dir_exist(c, "output_data_dir")
```

---

## invoke.yaml structure

```yaml
notebooks_dir: notebooks
source_data_dir: source_data
output_data_dir: output_data

files:
  dataset_name:
    url: https://...
    output_file: source_data/filename.ext
```

---

## Chunk-processing task pattern

Use this when a script processes independent items (subjects, samples, files) and should skip already-completed ones:

```python
@task
def process_subjects(c, subjects=None, smoke=False):
    """Process each subject; skip if output exists."""
    from analysis.process import process_subject, list_subjects
    output_dir = Path(c.config.get("output_data_dir"))
    source_dir = Path(c.config.get("source_data_dir"))

    all_subjects = list_subjects(source_dir)
    if smoke:
        all_subjects = all_subjects[:1]
    if subjects:
        all_subjects = subjects.split(",")

    for subj in all_subjects:
        out = output_dir / f"{subj}.csv"
        if out.exists():
            print(f"Skipping {subj} (output exists)")
            continue
        process_subject(subj, source_dir, output_dir)
```

Adapt the "chunk" concept (subjects, files, conditions, etc.) and the output existence check to match the actual data structure.

## run / run-smoke pattern

```python
@task(pre=[fetch, process_subjects, run_notebooks])
def run(c):
    """Full pipeline."""
    print("Pipeline complete.")

@task
def run_smoke(c):
    """Smoke test: minimal end-to-end run."""
    fetch(c)
    process_subjects(c, smoke=True)
    run_notebooks(c)
```

`run_smoke` calls tasks directly (not via `pre=`) so it can pass `smoke=True`.
