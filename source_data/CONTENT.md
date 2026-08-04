# Source Data

After `invoke fetch`, this folder contains:

* `cneuromod.all/` — the [CNeuroMod](https://www.cneuromod.ca/) `cneuromod.all`
  Datalad superdataset. It is either a **symlink** to an existing local checkout
  (default: `../cneuromod.all`, set via `source:` in `invoke.yaml` or
  `invoke fetch --source /path`) or a fresh **clone** of
  `https://github.com/courtois-neuromod/cneuromod.all` when no local checkout is
  available.

📝 File **content** inside the superdataset is retrieved selectively, never all
at once — the superdataset is large. `invoke fetch` installs each dataset's
`mriqc` and `tsnr` subdatasets, plus the dataset-root-level `anat/atlases`, and
`datalad get`s only what the pipeline reads: the MRIQC text files
(`*_bold.json`, `*_timeseries.tsv`), the per-subject `stat-avgtsnr` maps, the
per-run `stat-tsnr` maps, and the one shared combined-atlas volume with its
label TSV. Those MNI maps and that atlas are the only image content pulled — T1w
and the large fMRIPrep/bids content are never fetched.

📝 **Retrieval happens in `fetch` only.** No `run-*` step calls `datalad get`, so
`invoke run` is fast and works offline; a dataset whose input was never fetched
makes it warn and skip (or write an empty table), pointing you back at
`invoke fetch`.

📝 `cneuromod.all/` is **ignored by Git** here (see `.gitignore`), since it is an
external dataset with its own version control. `MANIFEST.json` is the exception
that *is* tracked — see below.

* `nilearn/` — the ICBM152 2009 MNI template + whole-brain mask
  (`nilearn.datasets.fetch_icbm152_2009`), used as the anatomical background
  and brain restriction for the tSNR coverage montages in
  `notebooks/tsnr_maps.ipynb`. `invoke fetch` downloads it once; the download
  is cache-aware, so re-running `fetch` is a no-op. Ignored by Git (see
  `.gitignore`).

* `MANIFEST.json` — written by `invoke fetch`: what each declared asset actually
  resolved to, including the **commit of the `cneuromod.all` checkout** behind
  the symlink and whether its working tree was clean. This is the only record of
  which input state a set of results came from when the superdataset is not
  itself pinned as a submodule — and it matters here, because `fetch` advances
  each marker subdataset's pin every time it runs. Git-tracked, unlike the data
  it describes.

📝 CNeuroMod data is only partly public. Some content lives on credentialed
remotes; if you lack access, `fetch` warns per file and continues, and the
affected datasets simply produce empty tables. That is expected behaviour, not a
broken pipeline — check `source_data/.fetch_failures.json` for what could not be
retrieved.
