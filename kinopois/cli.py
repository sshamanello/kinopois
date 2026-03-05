"""CLI interface for kinopois."""

import shutil
from pathlib import Path

import click
from rich.console import Console

from kinopois import __version__
from kinopois.collage import create_collages
from kinopois.config import config
from kinopois.export import (
    export_pinterest_csv,
    export_simple_collages_csv,
    export_summary,
)
from kinopois.db import init_db, sync_pins_csv, get_ready_jobs, mark_posted, mark_failed
from kinopois.marker import mark_posters, PosterMarker
from kinopois.processor import load_clean_movies, load_movies
from kinopois.scraper import KinopoiskScraper

console = Console()


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option(
    "--api-key",
    envvar="KINOPOISK_API_KEY",
    help="Kinopoisk.dev API key",
)
@click.option(
    "--data-dir",
    type=click.Path(exists=True, path_type=Path),
    help="Data directory path",
)
@click.pass_context
def main(ctx, api_key, data_dir):
    """Kinopoisk poster downloader and collage creator CLI.

    Download movie posters from Kinopoisk and create beautiful collages.

    Without arguments, launches interactive menu mode.
    """
    ctx.ensure_object(dict)

    # Update config from CLI options
    if api_key:
        config.kinopoisk_api_key = api_key
    if data_dir:
        config.data_dir = data_dir
        config.posters_dir = data_dir / "posters"
        config.collages_dir = data_dir / "collages"
        config.cache_dir = data_dir / "cache"

    # If no subcommand, launch interactive mode
    if ctx.invoked_subcommand is None:
        from kinopois.interactive import interactive as run_interactive
        run_interactive()


@main.command()
@click.option(
    "--limit",
    default=200,
    help="Number of movies to download",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output CSV file path",
)
@click.pass_context
def download(ctx, limit, output):
    """Download movie posters from Kinopoisk."""
    if not config.kinopoisk_api_key:
        console.print("[red]Error: KINOPOISK_API_KEY is required[/red]")
        console.print("Set it via --api-key option or KINOPOISK_API_KEY env var")
        raise click.Abort()

    console.print(f"[cyan]Downloading {limit} movies from Kinopoisk...[/cyan]")

    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    output_path = scraper.download_and_save(output_csv=output, limit=limit)

    console.print(f"[green]✓ Download complete: {output_path}[/green]")


@main.command()
@click.option(
    "--input",
    type=click.Path(exists=True, path_type=Path),
    help="Input CSV file (default: data/cache/movies.csv)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output CSV file (default: data/cache/movies_clean.csv)",
)
@click.pass_context
def process(ctx, input, output):
    """Process movie data: clean and add primary genre."""
    input_path = input or config.cache_dir / "movies.csv"
    output_path = output or config.cache_dir / "movies_clean.csv"

    if not input_path.exists():
        console.print(f"[red]Error: Input file not found: {input_path}[/red]")
        raise click.Abort()

    console.print(f"[cyan]Processing {input_path}...[/cyan]")

    processor = load_movies(input_path)
    processor.clean(output_path)

    console.print(f"[green]✓ Processing complete: {output_path}[/green]")


@main.command()
@click.option(
    "--input",
    type=click.Path(exists=True, path_type=Path),
    help="Input CSV file (default: data/cache/movies_clean.csv)",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Output directory for collages",
)
@click.option(
    "--watermark",
    help="Watermark text to overlay",
)
@click.option(
    "--max-per-genre",
    type=int,
    help="Maximum collages per genre",
)
@click.pass_context
def collage(ctx, input, output_dir, watermark, max_per_genre):
    """Create 2x2 collages from movie posters."""
    input_path = input or config.cache_dir / "movies_clean.csv"

    if not input_path.exists():
        console.print(f"[red]Error: Input file not found: {input_path}[/red]")
        console.print("Run 'kinopois process' first to create movies_clean.csv")
        raise click.Abort()

    console.print("[cyan]Creating collages...[/cyan]")

    output_csv = create_collages(
        input_csv=input_path,
        output_dir=output_dir,
        watermark=watermark,
        max_per_genre=max_per_genre,
    )

    console.print(f"[green]✓ Collages created: {output_csv}[/green]")


@main.command()
@click.argument("input_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Output directory (default: overwrites input)",
)
@click.option(
    "--text",
    help="Watermark text",
)
@click.option(
    "--position",
    type=click.Choice(["top", "bottom", "corner"]),
    default="bottom",
    help="Watermark position",
)
@click.pass_context
def mark(ctx, input_dir, output_dir, text, position):
    """Add watermark to poster images."""
    watermark = text or config.watermark_text

    console.print(f"[cyan]Marking posters in {input_dir}...[/cyan]")
    console.print(f"Watermark: '{watermark}' at {position}")

    marked = mark_posters(
        input_dir=input_dir,
        text=watermark,
        position=position,
        output_dir=output_dir,
    )

    console.print(f"[green]✓ Marked {marked} posters[/green]")


@main.command()
@click.option(
    "--input",
    type=click.Path(exists=True, path_type=Path),
    help="Collages CSV file",
)
@click.option(
    "--format",
    type=click.Choice(["pinterest", "simple", "summary"]),
    default="pinterest",
    help="Export format",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path",
)
@click.pass_context
def export(ctx, input, format, output):
    """Export collages to various formats."""
    if format == "summary":
        # Summary needs both collages and movies
        collages_csv = input or config.cache_dir / "collages.csv"
        movies_csv = config.cache_dir / "movies_clean.csv"
        export_summary(collages_csv, movies_csv, output)
    elif format == "pinterest":
        input_csv = input or config.cache_dir / "collages.csv"
        export_pinterest_csv(input_csv, output)
    else:  # simple
        input_csv = input or config.cache_dir / "collages.csv"
        export_simple_collages_csv(input_csv, output)

    console.print(f"[green]✓ Export complete[/green]")


@main.command()
@click.option(
    "--all",
    is_flag=True,
    help="Run full pipeline: download -> process -> collage -> export",
)
@click.option(
    "--limit",
    default=200,
    help="Number of movies to download",
)
@click.option(
    "--skip-download",
    is_flag=True,
    help="Skip download step (use existing data)",
)
@click.pass_context
def run(ctx, all, limit, skip_download):
    """Run the full workflow or individual steps."""
    if not all:
        console.print("[yellow]Use --all flag to run full pipeline[/yellow]")
        console.print("Or run individual commands: download, process, collage, export")
        return

    if not config.kinopoisk_api_key and not skip_download:
        console.print("[red]Error: KINOPOISK_API_KEY is required for download[/red]")
        raise click.Abort()

    console.print("[cyan]Starting full pipeline...[/cyan]")

    # Download
    if not skip_download:
        console.print("\n[bold]Step 1: Download[/bold]")
        ctx.invoke(download, limit=limit)

    # Process
    console.print("\n[bold]Step 2: Process[/bold]")
    ctx.invoke(process)

    # Create collages
    console.print("\n[bold]Step 3: Create collages[/bold]")
    ctx.invoke(collage)

    # Export
    console.print("\n[bold]Step 4: Export[/bold]")
    ctx.invoke(export, format="pinterest")

    console.print("\n[green]✓ Pipeline complete![/green]")


@main.command()
@click.option(
    "--cache",
    is_flag=True,
    help="Clean cache directory",
)
@click.option(
    "--collages",
    is_flag=True,
    help="Clean collages directory",
)
@click.option(
    "--all",
    is_flag=True,
    help="Clean all generated data",
)
@click.pass_context
def clean(ctx, cache, collages, all):
    """Clean generated data."""
    targets = []

    if all:
        targets.extend([config.cache_dir, config.collages_dir])
    else:
        if cache:
            targets.append(config.cache_dir)
        if collages:
            targets.append(config.collages_dir)

    if not targets:
        console.print("[yellow]Nothing to clean. Use --cache, --collages, or --all[/yellow]")
        return

    for target in targets:
        if target.exists():
            shutil.rmtree(target)
            console.print(f"[cyan]Removed: {target}[/cyan]")

    console.print("[green]✓ Clean complete[/green]")


@main.command()
@click.pass_context
def info(ctx):
    """Show project information and paths."""
    console.print("[bold]Kinopoisk Poster Downloader[/bold]")
    console.print(f"Version: {__version__}")
    console.print("")
    console.print("[bold]Configuration:[/bold]")
    console.print(f"  Data dir:      {config.data_dir}")
    console.print(f"  Posters dir:   {config.posters_dir}")
    console.print(f"  Collages dir:  {config.collages_dir}")
    console.print(f"  Cache dir:     {config.cache_dir}")
    console.print("")
    console.print("[bold]Status:[/bold]")

    # Check directories
    posters_count = len(list(config.posters_dir.glob("*.jpg"))) if config.posters_dir.exists() else 0
    collages_count = len(list(config.collages_dir.glob("*.jpg"))) if config.collages_dir.exists() else 0

    console.print(f"  Posters:       {posters_count} files")
    console.print(f"  Collages:      {collages_count} files")

    # Check cache files
    cache_files = []
    if config.cache_dir.exists():
        for csv_file in ["movies.csv", "movies_clean.csv", "collages.csv", "pins.csv"]:
            path = config.cache_dir / csv_file
            if path.exists():
                cache_files.append(f"  {csv_file}")

    if cache_files:
        console.print("  Cache files:")
        console.print("\n".join(cache_files))
    else:
        console.print("  Cache files:  (none)")


@main.command("db-init")
def db_init_cmd():
    """Initialize SQLite database for publish queue."""
    path = init_db()
    console.print(f"[green]✓ DB initialized: {path}[/green]")


@main.command("queue-sync")
@click.option(
    "--pins-csv",
    type=click.Path(exists=True, path_type=Path),
    help="Pins CSV path (default: data/cache/pins.csv)",
)
def queue_sync_cmd(pins_csv):
    """Import/export pins.csv rows into SQLite queue with dedupe."""
    csv_path = pins_csv or (config.cache_dir / "pins.csv")
    if not csv_path.exists():
        console.print(f"[red]Error: pins csv not found: {csv_path}[/red]")
        raise click.Abort()
    inserted = sync_pins_csv(csv_path)
    console.print(f"[green]✓ Queue synced, inserted: {inserted}[/green]")


@main.command("queue-ready")
@click.option("--limit", default=20, type=int, help="How many ready jobs to show")
def queue_ready_cmd(limit):
    """Print ready jobs as JSON (for n8n Execute Command node)."""
    import json
    rows = get_ready_jobs(limit=limit)
    click.echo(json.dumps(rows, ensure_ascii=False))


@main.command("queue-posted")
@click.option("--job-id", required=True, type=int, help="Queue job id")
@click.option("--pin-id", required=True, help="Pinterest pin id")
def queue_posted_cmd(job_id, pin_id):
    """Mark queue job as posted."""
    mark_posted(job_id, pin_id)
    console.print(f"[green]✓ Job {job_id} marked posted[/green]")


@main.command("queue-failed")
@click.option("--job-id", required=True, type=int, help="Queue job id")
@click.option("--error", required=True, help="Error message")
def queue_failed_cmd(job_id, error):
    """Mark queue job as failed and increment retries."""
    mark_failed(job_id, error)
    console.print(f"[yellow]⚠ Job {job_id} marked failed[/yellow]")


@main.command()
@click.pass_context
def interactive(ctx):
    """Launch interactive menu mode with keyboard navigation."""
    from kinopois.interactive import interactive as run_interactive
    run_interactive()


if __name__ == "__main__":
    main()
