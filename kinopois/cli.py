"""CLI interface for kinopois."""

import json
import shutil
import sys
from pathlib import Path

# On Windows cp1251 terminals some movie titles contain characters outside
# the code page, causing UnicodeEncodeError. Reconfigure stdout to replace
# unencodable characters with '?' instead of crashing.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kinopois import __version__
from kinopois.config import config
from kinopois.download.scraper import KinopoiskScraper
from kinopois.processing.collage import create_collages
from kinopois.processing.marker import mark_posters, PosterMarker
from kinopois.processing.processor import load_clean_movies, load_movies
from kinopois.publishing.autopilot import Autopilot
from kinopois.publishing.db import sync_all_from_csv
from kinopois.publishing.export import (
    build_movie_pin_rows,
    export_movie_pins_csv,
    export_pinterest_csv,
    export_simple_collages_csv,
    export_summary,
)
from kinopois.publishing.pipeline_steps import run_daily_prepare, step_publish
from kinopois.publishing.postgres_queue import (
    db_counts as queue_db_counts,
    get_ready_jobs,
    init_db as init_queue_db,
    mark_failed,
    mark_posted,
    sync_pin_rows,
)
from kinopois.utils import read_csv_dict

console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────


def print_error(message: str, hint: str = "") -> None:
    """Print user-friendly error message."""
    console.print(Panel(f"[red]{message}[/red]", title="[bold red]Error[/bold red]", border_style="red"))
    if hint:
        console.print(f"[dim]{hint}[/dim]")


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[green]+[/green] {message}")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[cyan]i[/cyan] {message}")


def print_step(step: int, total: int, message: str) -> None:
    """Print pipeline step."""
    console.print(f"\n[bold cyan]Step {step}/{total}:[/bold cyan] {message}")


# ── Main group ────────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True, context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(version=__version__, prog_name="kinopois")
@click.option("--api-key", envvar="KINOPOISK_API_KEY", help="Kinopoisk API key (or set KINOPOISK_API_KEY in .env)")
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), help="Data directory (default: ./data)")
@click.pass_context
def main(ctx, api_key, data_dir):
    """Download movie posters from Kinopoisk and create Pinterest-ready pins.

    Quick start:

    \b
      kinopois              Interactive menu
      kinopois pins         Download movies and create Pinterest pins
    """
    ctx.ensure_object(dict)

    if api_key:
        config.kinopoisk_api_key = api_key
    if data_dir:
        config.data_dir = data_dir
        config.posters_dir = data_dir / "posters"
        config.framed_source_posters_dir = data_dir / "posters_clean"
        config.framed_posters_dir = data_dir / "posters_framed"
        config.collages_dir = data_dir / "collages"
        config.cache_dir = data_dir / "cache"
        for d in [config.posters_dir, config.framed_source_posters_dir,
                  config.framed_posters_dir, config.collages_dir, config.cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

    if ctx.invoked_subcommand is None:
        from kinopois.interactive import interactive as run_interactive
        run_interactive()


# ── Download ──────────────────────────────────────────────────────────────────


@main.command()
@click.option("--limit", default=200, help="How many movies to download (default: 200)")
@click.option("--output", type=click.Path(path_type=Path), help="Save movies to file (default: data/cache/movies.csv)")
@click.option("--replace", is_flag=True, help="Replace output CSV instead of append-only mode")
@click.pass_context
def download(ctx, limit, output, replace):
    """Download movie posters from Kinopoisk.

    By default works in append-only mode and skips existing kp_id values.

    \b
      kinopois download --limit 100
      kinopois download --replace    Rebuild movies.csv from scratch
    """
    if not config.kinopoisk_api_key:
        print_error("API key is required", "Set KINOPOISK_API_KEY in .env or pass --api-key")
        raise click.Abort()

    console.print(f"[cyan]Downloading {limit} movies from Kinopoisk...[/cyan]")
    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    output_path = scraper.download_and_save(output_csv=output, limit=limit, append_mode=not replace)
    print_success(f"Downloaded to {output_path}")


# ── Process ───────────────────────────────────────────────────────────────────


@main.command()
@click.option("--input", "input_path", type=click.Path(exists=True, path_type=Path), help="Source CSV file")
@click.option("--output", "output_path", type=click.Path(path_type=Path), help="Output CSV file")
def process(ctx=None, input_path=None, output_path=None):
    """Clean movie data and add primary genre."""
    input_path = input_path or config.cache_dir / "movies.csv"
    output_path = output_path or config.cache_dir / "movies_clean.csv"

    if not input_path.exists():
        print_error(f"File not found: {input_path}", "Run 'kinopois download' first")
        raise click.Abort()

    console.print(f"[cyan]Processing {input_path}...[/cyan]")
    processor = load_movies(input_path)
    processor.clean(output_path)
    print_success(f"Cleaned data saved to {output_path}")


# ── Collage ──────────────────────────────────────────────────────────────────


@main.command()
@click.option("--input", "input_path", type=click.Path(exists=True, path_type=Path), help="Movies CSV file")
@click.option("--output-dir", type=click.Path(path_type=Path), help="Save collages to folder")
@click.option("--watermark", help="Text watermark to add")
@click.option("--max-per-genre", type=int, help="How many collages per genre")
def collage(ctx=None, input_path=None, output_dir=None, watermark=None, max_per_genre=None):
    """Create 2x2 poster collages grouped by genre."""
    input_path = input_path or config.cache_dir / "movies_clean.csv"

    if not input_path.exists():
        print_error(f"File not found: {input_path}", "Run 'kinopois process' first")
        raise click.Abort()

    console.print("[cyan]Creating collages...[/cyan]")
    output_csv = create_collages(
        input_csv=input_path, output_dir=output_dir,
        watermark=watermark, max_per_genre=max_per_genre,
    )
    print_success(f"Collages created: {output_csv}")


# ── Mark ──────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("input_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", type=click.Path(path_type=Path), help="Save to folder (default: overwrite)")
@click.option("--text", help="Watermark text (default: @TopTrailer82Bot)")
@click.option("--position", type=click.Choice(["top", "bottom", "corner"]), default="bottom")
def mark(ctx=None, input_dir=None, output_dir=None, text=None, position="bottom"):
    """Add watermark text to poster images."""
    watermark = text or config.watermark_text
    console.print(f"[cyan]Adding watermark to images in {input_dir}...[/cyan]")
    marked = mark_posters(input_dir=Path(input_dir), text=watermark, position=position, output_dir=output_dir and Path(output_dir))
    print_success(f"Marked {marked} images")


# ── Export (collages) ────────────────────────────────────────────────────────


@main.command()
@click.option("--input", "input_path", type=click.Path(exists=True, path_type=Path), help="Collages CSV file")
@click.option("--format", "fmt", type=click.Choice(["pinterest", "simple", "summary"]), default="pinterest", help="Export format")
@click.option("--output", "output_path", type=click.Path(path_type=Path), help="Save output to file")
def export(ctx=None, input_path=None, fmt="pinterest", output_path=None):
    """Export collage metadata to CSV files."""
    if fmt == "summary":
        collages_csv = input_path or config.cache_dir / "collages.csv"
        movies_csv = config.cache_dir / "movies_clean.csv"
        export_summary(collages_csv, movies_csv, output_path)
    elif fmt == "pinterest":
        export_pinterest_csv(input_path or config.cache_dir / "collages.csv", output_path)
    else:
        export_simple_collages_csv(input_path or config.cache_dir / "collages.csv", output_path)
    print_success("Export complete")


# ── Export movie pins ─────────────────────────────────────────────────────────


@main.command("export-movie-pins")
@click.option("--input", "input_csv", type=click.Path(exists=True, path_type=Path), help="Source CSV file")
@click.option("--output", "output_csv", type=click.Path(path_type=Path), help="Output pins CSV")
@click.option("--limit", default=0, type=int, help="Maximum pins to export (0 = all)")
def export_movie_pins_cmd(input_csv=None, output_csv=None, limit=0):
    """Export movie posters as Pinterest pins CSV."""
    input_path = input_csv or config.cache_dir / "movies_clean.csv"
    if not input_path.exists():
        print_error(f"File not found: {input_path}", "Run 'kinopois process' first")
        raise click.Abort()

    output_path = export_movie_pins_csv(input_csv=input_path, output_csv=output_csv, limit=limit or None)
    print_success(f"Pins exported to {output_path}")


# ── Pins (main pipeline) ─────────────────────────────────────────────────────


@main.command()
@click.option("--limit", default=200, type=int, help="How many movies to download")
@click.option("--skip-download", is_flag=True, help="Skip downloading (use existing movies.csv)")
@click.option("--skip-process", is_flag=True, help="Skip processing (use existing movies_clean.csv)")
@click.option("--sync-queue", is_flag=True, help="Also sync to Postgres queue")
@click.pass_context
def pins(ctx, limit, skip_download, skip_process, sync_queue):
    """Download movies and create Pinterest-ready pins.

    This is the main command for the pin pipeline:
    1. Download movie posters from Kinopoisk
    2. Clean data and add genres
    3. Export to pins.csv

    \b
      kinopois pins                          Download 200 movies and create pins
      kinopois pins --limit 100              Download only 100 movies
      kinopois pins --skip-download          Create pins from existing data
      kinopois pins --sync-queue             Also sync to Postgres queue
    """
    if not config.kinopoisk_api_key and not skip_download:
        print_error("API key is required", "Set KINOPOISK_API_KEY in .env or pass --api-key")
        raise click.Abort()

    console.print("[bold cyan]Creating Pinterest pins...[/bold cyan]")

    if not skip_download:
        print_step(1, 3, f"Download movies from Kinopoisk ({limit} max)")
        ctx.invoke(download, limit=limit)
    else:
        print_step(1, 3, "Download (skipped - using existing data)")

    if not skip_process:
        print_step(2, 3, "Clean data and add genres")
        ctx.invoke(process)
    else:
        print_step(2, 3, "Process (skipped)")

    print_step(3, 3, "Export poster pins to CSV")
    ctx.invoke(export_movie_pins_cmd)

    if sync_queue:
        console.print("\n[cyan]Syncing to Postgres queue...[/cyan]")
        pins_rows, _ = build_movie_pin_rows(config.cache_dir / "movies_clean.csv")
        inserted = sync_pin_rows(pins_rows)
        counts = queue_db_counts()
        console.print(f"[green]Queue synced, inserted: {inserted}[/green]")
        console.print(f"[cyan]Queue counts:[/cyan] {counts}")

    console.print(f"\n[green]+ Done![/green] Pins saved to: {config.cache_dir / 'pins.csv'}")


# ── Run base pipeline (production) ───────────────────────────────────────────


@main.command("run-base-pipeline")
@click.option("--limit", default=200, type=int, help="Download limit for this run")
@click.option("--publish", default=0, type=int, help="Publish N ready jobs after prepare")
def run_base_pipeline_cmd(limit, publish):
    """Run base modular pipeline: download -> process -> upload -> queue."""
    stats = run_daily_prepare(max(1, int(limit)))
    print_success(f"Prepare complete: {stats}")
    if publish > 0:
        pub = step_publish(limit=publish)
        print_success(f"Publish complete: {pub}")


# ── Clean ─────────────────────────────────────────────────────────────────────


@main.command()
@click.option("--cache", is_flag=True, help="Remove CSV files (movies.csv, pins.csv, etc.)")
@click.option("--collages", is_flag=True, help="Remove collage images")
@click.option("--posters", is_flag=True, help="Remove downloaded poster images")
@click.option("--all", "clean_all", is_flag=True, help="Remove all generated data")
def clean(ctx=None, cache=False, collages=False, posters=False, clean_all=False):
    """Remove generated data to start fresh."""
    targets = []
    if clean_all:
        targets.extend([config.cache_dir, config.collages_dir, config.posters_dir])
    else:
        if cache:
            targets.append(config.cache_dir)
        if collages:
            targets.append(config.collages_dir)
        if posters:
            targets.append(config.posters_dir)

    if not targets:
        console.print("[yellow]Specify what to clean:[/yellow]")
        console.print("  --cache      Remove CSV files (movies.csv, pins.csv)")
        console.print("  --collages   Remove collage images")
        console.print("  --posters    Remove poster images")
        console.print("  --all        Remove everything")
        return

    for target in targets:
        if target.exists():
            shutil.rmtree(target)
            console.print(f"[cyan]Removed: {target}[/cyan]")
    print_success("Clean complete")


# ── Info ──────────────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def info(ctx):
    """Show project status and file counts."""
    table = Table(title="Kinopois Status", show_header=False)
    table.add_column("Item", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Version", __version__)
    table.add_row("Data directory", str(config.data_dir))
    table.add_row("API key", "Set" if config.kinopoisk_api_key else "[yellow]Not set[/yellow]")
    console.print(table)
    console.print("")

    posters_count = len(list(config.posters_dir.glob("*.jpg"))) if config.posters_dir.exists() else 0
    collages_count = len(list(config.collages_dir.glob("*.jpg"))) if config.collages_dir.exists() else 0

    table2 = Table(title="Files", show_header=True)
    table2.add_column("Type", style="cyan")
    table2.add_column("Count", style="white")
    table2.add_column("Location", style="dim")
    table2.add_row("Posters", str(posters_count), str(config.posters_dir))
    table2.add_row("Collages", str(collages_count), str(config.collages_dir))

    if config.cache_dir.exists():
        for csv_file in ["movies.csv", "movies_clean.csv", "collages.csv", "pins.csv"]:
            path = config.cache_dir / csv_file
            if path.exists():
                size_kb = path.stat().st_size // 1024
                table2.add_row(csv_file, f"{size_kb} KB", str(path))
    console.print(table2)


# ── Database commands ─────────────────────────────────────────────────────────


@main.command("db-init")
def db_init_cmd():
    """Initialize Postgres publish queue schema."""
    init_queue_db()
    console.print("[green]Queue DB initialized[/green]")


@main.command("db-sync-all")
def db_sync_all_cmd():
    """Sync all CSV artifacts into SQLite cache and Postgres publish queue."""
    out = sync_all_from_csv(config.cache_dir)
    pins_csv = config.cache_dir / "pins.csv"
    inserted = 0
    if pins_csv.exists():
        rows = read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding)
        inserted = sync_pin_rows(rows)
    counts = queue_db_counts()
    console.print(f"[green]Cache synced: {out}, queue inserted: {inserted}[/green]")
    console.print(f"[cyan]Queue counts:[/cyan] {counts}")


@main.command("db-stats")
def db_stats_cmd():
    """Show current Postgres queue counts."""
    counts = queue_db_counts()
    console.print(f"[cyan]Queue counts:[/cyan] {counts}")


# ── Queue commands ────────────────────────────────────────────────────────────


@main.command("queue-ready")
@click.option("--limit", default=20, type=int, help="How many ready jobs to show")
def queue_ready_cmd(limit):
    """Print ready jobs as JSON (for n8n Execute Command node)."""
    rows = get_ready_jobs(limit=limit)
    click.echo(json.dumps(rows, ensure_ascii=False))


@main.command("queue-posted")
@click.option("--job-id", required=True, type=int, help="Queue job id")
@click.option("--pin-id", required=True, help="Pinterest pin id")
def queue_posted_cmd(job_id, pin_id):
    """Mark queue job as posted."""
    mark_posted(job_id, pin_id)
    console.print(f"[green]Job {job_id} marked posted[/green]")


@main.command("queue-failed")
@click.option("--job-id", required=True, type=int, help="Queue job id")
@click.option("--error", required=True, help="Error message")
def queue_failed_cmd(job_id, error):
    """Mark queue job as failed."""
    mark_failed(job_id, error)
    console.print(f"[yellow]WARNING: Job {job_id} marked failed[/yellow]")


# ── Autopilot ─────────────────────────────────────────────────────────────────


@main.command("autopilot-once")
def autopilot_once_cmd():
    """Run one autopilot tick (harvest + due post slots)."""
    Autopilot().run_once()
    print_success("Autopilot one-shot run complete")


@main.command("autopilot")
def autopilot_daemon_cmd():
    """Run autonomous scheduler forever."""
    Autopilot().run_forever()


# ── Interactive menu ──────────────────────────────────────────────────────────


@main.command("menu")
@click.pass_context
def interactive_cmd(ctx):
    """Launch interactive menu with keyboard navigation."""
    from kinopois.interactive import interactive as run_interactive
    run_interactive()


if __name__ == "__main__":
    main()