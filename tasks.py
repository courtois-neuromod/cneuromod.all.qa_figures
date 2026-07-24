from pathlib import Path
from invoke import task

@task(help={
    "source": "Path to already-present 'papers' data to symlink instead of downloading.",
    "copy": "Copy the source data instead of symlinking it.",
})
def fetch_papers(c, source=None, copy=False):
    """
    Retrieve the 'papers' asset (download, or symlink/copy existing data).
    """
    from airoh.acquisition import fetch_data
    fetch_data(c, "papers", source=source, copy=copy)

@task(help={
    "papers_source": "Path to existing 'papers' data to symlink instead of downloading.",
    "copy": "Copy source data instead of symlinking it.",
})
def fetch(c, papers_source=None, copy=False):
    """
    Retrieve all data assets. Each asset has its own fetch-{name} task; this
    umbrella task routes a per-asset --{name}-source flag to the matching one.
    """
    fetch_papers(c, source=papers_source, copy=copy)

@task
def run_simulation(c):
    """
    Run a small simulation.
    """
    output_dir = Path(c.config.get("output_data_dir"))
    from analysis.simulation import simulation
    simulation(output_dir)

@task(pre=[run_simulation])
def run_notebooks(c):
    """
    Generate figures from the simulation output using a notebook.
    """
    from airoh.utils import run_notebooks as airoh_run_notebooks, ensure_dir_exist

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    output_dir = Path(c.config.get("output_data_dir")).resolve()
    source_dir = Path(c.config.get("source_data_dir")).resolve()

    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, output_dir, keys=["source_data_dir", "output_data_dir"])

@task(pre=[run_simulation, run_notebooks])
def run(c):
    print("all analyses completed")

@task
def clean(c):
    """
    Clean the output folder.
    """
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "*.png")
    clean_folder(c, "output_data_dir", "*.csv")
