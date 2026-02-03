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
from kinopois.export import export_for_n8n, export_for_pinterest
from kinopois.marker import mark_posters
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
@click.pass_context
def download(ctx, limit):
    """Download movie posters from Kinopoisk to database."""
    if not config.kinopoisk_api_key:
        console.print("[red]Error: KINOPOISK_API_KEY is required[/red]")
        console.print("Set it via --api-key option or KINOPOISK_API_KEY env var")
        raise click.Abort()

    console.print(f"[cyan]Downloading {limit} movies from Kinopoisk...[/cyan]")

    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    count = scraper.download_and_save(limit=limit)

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
@click.pass_context
def collage(ctx, watermark, max_per_genre):
    """Create 2x2 collages from movies in database."""
    console.print("[cyan]Creating collages...[/cyan]")

    count = create_collages(
        watermark=watermark,
        max_per_genre=max_per_genre,
    )

    console.print(f"[green]OK Created {count} collages[/green]")


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

    console.print(f"[green]OK Marked {marked} posters[/green]")


@main.command()
@click.option(
    "--format",
    type=click.Choice(["pinterest", "n8n", "simple", "summary"]),
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
            if stats['by_genre']:
                console.print("\n  [bold]By Genre:[/bold]")
                for genre, count in list(stats['by_genre'].items())[:10]:
                    console.print(f"    {genre}: {count}")
        elif format == "pinterest":
            export_for_pinterest(db, output)
        elif format == "n8n":
            export_for_n8n(db, output)
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
@click.pass_context
def run(ctx, all, limit, skip_download):
    """Run the full workflow or individual steps."""
    if not all:
        console.print("[yellow]Use --all flag to run full pipeline[/yellow]")
        console.print("Or run individual commands: download, collage, export")
        return

    if not config.kinopoisk_api_key and not skip_download:
        console.print("[red]Error: KINOPOISK_API_KEY is required for download[/red]")
        raise click.Abort()

    console.print("[cyan]Starting full pipeline...[/cyan]")

    # Download
    if not skip_download:
        console.print("\n[bold]Step 1: Download[/bold]")
        ctx.invoke(download, limit=limit)

    # Create collages
    console.print("\n[bold]Step 2: Create collages[/bold]")
    ctx.invoke(collage)

    # Export
    console.print("\n[bold]Step 3: Export[/bold]")
    ctx.invoke(export, format="pinterest")

    console.print("\n[green]OK Pipeline complete![/green]")


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
@click.pass_context
def clean(ctx, db, collages, posters, all):
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


if __name__ == "__main__":
    main()
