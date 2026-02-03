"""CLI interface for kinopois."""

import shutil
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from kinopois import __version__
from kinopois.collage import create_collages
from kinopois.config import config
from kinopois.database import Database
from kinopois.export import export_for_n8n, export_for_n8n_json, export_for_pinterest
from kinopois.logger import get_logger
from kinopois.marker import mark_posters
from kinopois.scraper import KinopoiskScraper

console = Console()
logger = get_logger()


def validate_configuration() -> tuple[bool, list[str]]:
    """Validate application configuration.

    Returns:
        Tuple of (is_valid, list of errors).
    """
    errors = []

    # Check API key if available
    if not config.kinopoisk_api_key:
        errors.append("KINOPOISK_API_KEY is not set")

    # Check directories are writable
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        test_file = config.data_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        errors.append(f"Data directory is not writable: {e}")

    # Check disk space (at least 100 MB)
    try:
        import shutil
        stat = shutil.disk_usage(config.data_dir)
        free_mb = stat.free / (1024 * 1024)
        if free_mb < 100:
            errors.append(f"Low disk space: {free_mb:.1f} MB free (recommended: 100 MB+)")
    except Exception:
        pass

    return len(errors) == 0, errors


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
    "--resume",
    is_flag=True,
    help="Resume from previous progress",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be downloaded without actually downloading",
)
@click.pass_context
def download(ctx, limit, resume, dry_run):
    """Download movie posters from Kinopoisk to database."""
    if not config.kinopoisk_api_key:
        console.print("[red]Error: KINOPOISK_API_KEY is required[/red]")
        console.print("Set it via --api-key option or KINOPOISK_API_KEY env var")
        raise click.Abort()

    # Validate configuration
    is_valid, errors = validate_configuration()
    if not is_valid:
        console.print("[red]Configuration errors:[/red]")
        for error in errors:
            console.print(f"  - {error}")
        if not config.kinopoisk_api_key:
            console.print("\n[yellow]Warning: API key not set, but continuing anyway...[/yellow]")

    if dry_run:
        console.print(f"[yellow][DRY RUN] Would download {limit} movies from Kinopoisk...[/yellow]")
        console.print(f"[yellow]Resume: {resume}[/yellow]")
        return

    console.print(f"[cyan]Downloading {limit} movies from Kinopoisk...[/cyan]")

    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    count = scraper.download_and_save(limit=limit, resume=resume)

    console.print(f"[green]OK Downloaded {count} movies to database[/green]")


@main.command()
@click.option(
    "--watermark",
    help="Watermark text to overlay",
)
@click.option(
    "--max-per-genre",
    type=int,
    help="Maximum collages per genre",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be created without actually creating files",
)
@click.pass_context
def collage(ctx, watermark, max_per_genre, dry_run):
    """Create 2x2 collages from movies in database."""
    if dry_run:
        console.print("[yellow][DRY RUN] Simulating collage creation...[/yellow]")

    console.print("[cyan]Creating collages...[/cyan]")

    count = create_collages(
        watermark=watermark,
        max_per_genre=max_per_genre,
        dry_run=dry_run,
    )

    console.print(f"[green]OK {'[DRY RUN] Would create' if dry_run else 'Created'} {count} collages[/green]")


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
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be marked without actually marking",
)
@click.pass_context
def mark(ctx, input_dir, output_dir, text, position, dry_run):
    """Add watermark to poster images."""
    if dry_run:
        watermark = text or config.watermark_text
        console.print(f"[yellow][DRY RUN] Would mark posters in {input_dir}[/yellow]")
        console.print(f"Watermark: '{watermark}' at {position}")
        console.print(f"Output: {output_dir or input_dir}")
        return

    watermark = text or config.watermark_text

    console.print(f"[cyan]Marking posters in {input_dir}...[/cyan]")
    console.print(f"Watermark: '{watermark}' at {position}")

    marked = mark_posters(
        input_dir=input_dir,
        text=watermark,
        position=position,
        output_dir=output_dir,
    )

    console.print(f"[green]OK Marked {marked} posters[/green]")


@main.command()
@click.option(
    "--format",
    type=click.Choice(["pinterest", "n8n", "n8n-json", "simple", "summary"]),
    default="pinterest",
    help="Export format",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path",
)
@click.pass_context
def export(ctx, format, output):
    """Export collages from database to various formats."""
    console.print(f"[cyan]Exporting collages as {format}...[/cyan]")

    with Database() as db:
        if format == "summary":
            stats = db.get_stats()
            console.print("\n[bold]Database Statistics:[/bold]")
            console.print(f"  Movies: {stats['movies']}")
            console.print(f"  Collages: {stats['collages']}")
            if stats.get('total_collages_size_bytes'):
                from kinopois.collage import format_file_size
                size_str = format_file_size(stats['total_collages_size_bytes'])
                console.print(f"  Total collages size: {size_str}")
            if stats['by_genre']:
                console.print("\n  [bold]By Genre:[/bold]")
                for genre, count in list(stats['by_genre'].items())[:10]:
                    console.print(f"    {genre}: {count}")
        elif format == "pinterest":
            export_for_pinterest(db, output)
        elif format == "n8n":
            export_for_n8n(db, output)
        elif format == "n8n-json":
            export_for_n8n_json(db, output)
        else:  # simple
            collages = db.get_collages()
            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write("genre;collage_file;link\n")
                    for c in collages:
                        f.write(f"{c.genre};{c.collage_file};{config.bot_url}\n")
                console.print(f"[green]OK Exported {len(collages)} collages to {output}[/green]")
            else:
                console.print("[yellow]Please specify --output path for simple format[/yellow]")

    console.print("[green]OK Export complete[/green]")


@main.command()
@click.option(
    "--all",
    is_flag=True,
    help="Run full pipeline: download -> collage -> export",
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
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without actually doing it",
)
@click.pass_context
def run(ctx, all, limit, skip_download, dry_run):
    """Run the full workflow or individual steps."""
    if not all:
        console.print("[yellow]Use --all flag to run full pipeline[/yellow]")
        console.print("Or run individual commands: download, collage, export")
        return

    if not config.kinopoisk_api_key and not skip_download and not dry_run:
        console.print("[red]Error: KINOPOISK_API_KEY is required for download[/red]")
        raise click.Abort()

    if dry_run:
        console.print("[yellow][DRY RUN] Simulating full pipeline...[/yellow]")

    console.print("[cyan]Starting full pipeline...[/cyan]")

    # Download
    if not skip_download:
        console.print("\n[bold]Step 1: Download[/bold]")
        ctx.invoke(download, limit=limit, dry_run=dry_run)

    # Create collages
    console.print("\n[bold]Step 2: Create collages[/bold]")
    ctx.invoke(collage, dry_run=dry_run)

    # Export
    console.print("\n[bold]Step 3: Export[/bold]")
    ctx.invoke(export, format="n8n-json")

    console.print(f"\n[green]OK {'[DRY RUN] Pipeline simulated' if dry_run else 'Pipeline complete'}![/green]")


@main.command()
@click.option(
    "--db",
    is_flag=True,
    help="Clean database",
)
@click.option(
    "--collages",
    is_flag=True,
    help="Clean collages directory",
)
@click.option(
    "--posters",
    is_flag=True,
    help="Clean posters directory",
)
@click.option(
    "--all",
    is_flag=True,
    help="Clean all generated data",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be cleaned without actually cleaning",
)
@click.pass_context
def clean(ctx, db, collages, posters, all, dry_run):
    """Clean generated data."""
    targets = []

    if all:
        if (config.data_dir / "kinopois.db").exists():
            targets.append("db")
        targets.extend(["collages", "posters"])
    else:
        if db:
            targets.append("db")
        if collages:
            targets.append("collages")
        if posters:
            targets.append("posters")

    if not targets:
        console.print("[yellow]Nothing to clean. Use --db, --collages, --posters, or --all[/yellow]")
        return

    if dry_run:
        console.print("[yellow][DRY RUN] Would clean the following:[/yellow]")
        for target in targets:
            console.print(f"  - {target}")
        return

    for target in targets:
        if target == "db":
            db_path = config.data_dir / "kinopois.db"
            if db_path.exists():
                db_path.unlink()
                console.print(f"[cyan]Removed: {db_path}[/cyan]")
        elif target == "collages":
            if config.collages_dir.exists():
                shutil.rmtree(config.collages_dir)
                config.collages_dir.mkdir(parents=True, exist_ok=True)
                console.print(f"[cyan]Cleared: {config.collages_dir}[/cyan]")
        elif target == "posters":
            if config.posters_dir.exists():
                shutil.rmtree(config.posters_dir)
                config.posters_dir.mkdir(parents=True, exist_ok=True)
                console.print(f"[cyan]Cleared: {config.posters_dir}[/cyan]")

    console.print("[green]OK Clean complete[/green]")


@main.command()
@click.pass_context
def info(ctx):
    """Show project information and database statistics."""
    console.print(f"[bold cyan]Kinopoisk Poster Downloader[/bold cyan]")
    console.print(f"Version: {__version__}")
    console.print("")

    # Configuration
    console.print("[bold]Configuration:[/bold]")
    console.print(f"  Data dir:      {config.data_dir}")
    console.print(f"  Posters dir:   {config.posters_dir}")
    console.print(f"  Collages dir:  {config.collages_dir}")
    console.print(f"  Database:      {config.data_dir / 'kinopois.db'}")
    console.print(f"  Log file:      {config.data_dir / 'kinopois.log'}")
    console.print("")

    # File counts
    posters_count = len(list(config.posters_dir.glob("*.jpg"))) if config.posters_dir.exists() else 0
    collages_count = len(list(config.collages_dir.glob("*.jpg"))) if config.collages_dir.exists() else 0

    console.print("[bold]Files:[/bold]")
    console.print(f"  Posters:       {posters_count} files")
    console.print(f"  Collages:      {collages_count} files")
    console.print("")

    # Database stats
    db_path = config.data_dir / "kinopois.db"
    if db_path.exists():
        with Database() as db:
            stats = db.get_stats()
            console.print("[bold]Database:[/bold]")
            console.print(f"  Movies:       {stats['movies']}")
            console.print(f"  Collages:      {stats['collages']}")

            if stats['by_genre']:
                console.print("")
                console.print("  [bold]Movies by genre:[/bold]")
                for genre, count in list(stats['by_genre'].items())[:5]:
                    console.print(f"    {genre}: {count}")
                if len(stats['by_genre']) > 5:
                    console.print(f"    ... and {len(stats['by_genre']) - 5} more")
    else:
        console.print("[yellow]Database not found. Run 'download' first.[/yellow]")


@main.command()
@click.pass_context
def status(ctx):
    """Show current status with statistics and recommendations."""
    console.print(f"[bold cyan]Kinopoisk Status[/bold cyan]")
    console.print("")

    # Configuration validation
    is_valid, errors = validate_configuration()
    console.print("[bold]Configuration:[/bold]")
    if is_valid:
        console.print("  [green]✓[/green] Configuration is valid")
    else:
        console.print("  [red]✗[/red] Configuration has errors:")
        for error in errors:
            console.print(f"    [red]•[/red] {error}")
    console.print("")

    # Database stats
    db_path = config.data_dir / "kinopois.db"
    if db_path.exists():
        with Database() as db:
            stats = db.get_stats()

            console.print("[bold]Database Statistics:[/bold]")
            console.print(f"  Movies:       {stats['movies']}")
            console.print(f"  Collages:      {stats['collages']}")

            if stats.get('total_collages_size_bytes'):
                from kinopois.collage import format_file_size
                size_str = format_file_size(stats['total_collages_size_bytes'])
                console.print(f"  Total size:    {size_str}")

            # Movies by genre
            if stats['by_genre']:
                console.print("")
                console.print("  [bold]Movies by Genre:[/bold]")
                for genre, count in list(stats['by_genre'].items())[:8]:
                    # Show progress bar
                    bar_length = int(count / 5)  # Scale: 20 chars = 100 movies
                    bar = "█" * min(bar_length, 20)
                    console.print(f"    {genre:15} {count:3} [{bar:20}]")
                if len(stats['by_genre']) > 8:
                    console.print(f"    ... and {len(stats['by_genre']) - 8} more")

            # Recommendations
            console.print("")
            console.print("[bold]Recommendations:[/bold]")
            recommendations = db.get_recommendations()
            if recommendations:
                for i, rec in enumerate(recommendations[:5], 1):
                    console.print(f"  {i}. {rec}")
                if len(recommendations) > 5:
                    console.print(f"  ... and {len(recommendations) - 5} more")
            else:
                console.print("  [green]✓[/green] Everything looks good!")

    else:
        console.print("[yellow]Database not found.[/yellow]")
        console.print("")
        console.print("[bold]Recommended Actions:[/bold]")
        console.print("  1. Set KINOPOISK_API_KEY environment variable")
        console.print("  2. Run: kinopois download --limit 200")

    # Logger stats
    log_stats = logger.get_stats()
    if log_stats.get("last_operation"):
        console.print("")
        console.print("[bold]Last Operation:[/bold]")
        console.print(f"  Operation:    {log_stats['last_operation']}")
        if log_stats.get("last_update"):
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(log_stats['last_update'])
                console.print(f"  Time:         {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            except:
                pass

    # Recent errors
    console.print("")
    console.print("[bold]Recent Activity:[/bold]")
    recent_errors = logger.get_recent_errors(5)
    if recent_errors:
        console.print(f"  [yellow]Recent errors ({len(recent_errors)}):[/yellow]")
        for error in recent_errors[-3:]:
            # Extract just the message part
            if "| ERROR     |" in error:
                msg = error.split("| ERROR     |")[-1].strip()
                console.print(f"    • {msg[:80]}...")
    else:
        console.print("  [green]✓[/green] No recent errors")

    console.print("")


if __name__ == "__main__":
    main()
