"""Interactive CLI menu with keyboard navigation."""

from pathlib import Path
from typing import Optional

import click
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kinopois import __version__
from kinopois.cli import main as cli_main
from kinopois.collage import create_collages
from kinopois.config import config
from kinopois.export import (
    export_pinterest_csv,
    export_simple_collages_csv,
    export_summary,
)
from kinopois.marker import mark_posters, PosterMarker
from kinopois.processor import load_clean_movies, load_movies
from kinopois.scraper import KinopoiskScraper
from kinopois.db import (
    init_db,
    sync_pins_csv,
    get_ready_jobs,
    mark_posted,
    mark_failed,
    get_conn,
    sync_all_from_csv,
    db_counts,
)

console = Console()


def print_header():
    """Print application header."""
    header = Panel.fit(
        "[bold cyan]🎬 Kinopoisk Poster Downloader[/bold cyan]\n"
        f"[dim]Version {__version__}[/dim]",
        border_style="cyan",
    )
    console.print(header)
    console.print()


def print_status():
    """Print current project status."""
    table = Table(title="Project Status", show_header=True, header_style="bold magenta")
    table.add_column("Resource", style="cyan")
    table.add_column("Count", style="green")
    table.add_column("Path", style="dim")

    # Count files
    posters_count = len(list(config.posters_dir.glob("*.jpg"))) if config.posters_dir.exists() else 0
    collages_count = len(list(config.collages_dir.glob("*.jpg"))) if config.collages_dir.exists() else 0

    table.add_row("Posters", str(posters_count), str(config.posters_dir))
    table.add_row("Collages", str(collages_count), str(config.collages_dir))

    # Cache files
    cache_files = []
    if config.cache_dir.exists():
        for csv_file in ["movies.csv", "movies_clean.csv", "collages.csv", "pins.csv"]:
            if (config.cache_dir / csv_file).exists():
                cache_files.append(csv_file)

    table.add_row("Cache files", str(len(cache_files)), str(config.cache_dir))

    # Queue status (SQLite)
    try:
        init_db()
        with get_conn() as conn:
            ready = conn.execute("SELECT COUNT(*) FROM publish_jobs WHERE status='ready'").fetchone()[0]
            posted = conn.execute("SELECT COUNT(*) FROM publish_jobs WHERE status='posted'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM publish_jobs WHERE status='failed'").fetchone()[0]
        table.add_row("Queue ready", str(ready), str(config.cache_dir / 'kinopois.db'))
        table.add_row("Queue posted", str(posted), str(config.cache_dir / 'kinopois.db'))
        table.add_row("Queue failed", str(failed), str(config.cache_dir / 'kinopois.db'))
    except Exception:
        pass

    console.print(table)
    console.print()


async def download_menu():
    """Download menu with options."""
    console.print("[bold yellow]📥 Download Posters[/bold yellow]")
    console.print()

    limit = await questionary.text(
        "How many movies to download?",
        default="200",
        validate=lambda x: x.isdigit() and int(x) > 0,
    ).ask_async()

    limit = int(limit)

    if not config.kinopoisk_api_key:
        console.print("[red]Error: KINOPOISK_API_KEY is not set![/red]")
        if await questionary.confirm("Enter API key now?", default=True).ask_async():
            config.kinopoisk_api_key = await questionary.password("API Key:").ask_async()
        else:
            return

    console.print(f"[cyan]Downloading {limit} movies...[/cyan]")

    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    scraper.download_and_save(limit=limit)

    console.print("[green]✓ Download complete![/green]")
    await questionary.press_any_key_to_continue().ask_async()


async def process_menu():
    """Process menu."""
    console.print("[bold yellow]🔄 Process Data[/bold yellow]")
    console.print()

    input_csv = config.cache_dir / "movies.csv"
    output_csv = config.cache_dir / "movies_clean.csv"

    if not input_csv.exists():
        console.print(f"[red]Error: {input_csv} not found![/red]")
        console.print("Run 'Download' first to get movie data.")
        await questionary.press_any_key_to_continue().ask_async()
        return

    console.print(f"[dim]Input:  {input_csv}[/dim]")
    console.print(f"[dim]Output: {output_csv}[/dim]")
    console.print()

    processor = load_movies(input_csv)
    processor.clean(output_csv)

    console.print("[green]✓ Processing complete![/green]")
    await questionary.press_any_key_to_continue().ask_async()


async def collage_menu():
    """Collage creation menu."""
    console.print("[bold yellow]🖼️  Create Collages[/bold yellow]")
    console.print()

    input_csv = config.cache_dir / "movies_clean.csv"

    if not input_csv.exists():
        console.print(f"[red]Error: {input_csv} not found![/red]")
        console.print("Run 'Process Data' first.")
        await questionary.press_any_key_to_continue().ask_async()
        return

    # Ask for watermark
    add_watermark = await questionary.confirm("Add watermark?", default=True).ask_async()
    watermark = ""
    if add_watermark:
        watermark = await questionary.text(
            "Watermark text:",
            default=config.watermark_text,
        ).ask_async()

    # Ask for max per genre
    limit_genre = await questionary.confirm("Limit collages per genre?", default=False).ask_async()
    max_per_genre = None
    if limit_genre:
        max_str = await questionary.text("Maximum per genre:", default="5").ask_async()
        max_per_genre = int(max_str) if max_str.isdigit() else None

    console.print("[cyan]Creating collages...[/cyan]")

    create_collages(
        input_csv=input_csv,
        watermark=watermark if add_watermark else None,
        max_per_genre=max_per_genre,
    )

    console.print("[green]✓ Collages created![/green]")
    await questionary.press_any_key_to_continue().ask_async()


async def mark_menu():
    """Mark posters menu."""
    console.print("[bold yellow]✏️  Mark Posters[/bold yellow]")
    console.print()

    # Choose source
    source = await questionary.select(
        "Mark all posters or specific files?",
        choices=[
            questionary.Choice("All posters in data/posters", "all"),
            questionary.Choice("From CSV file", "csv"),
            questionary.Choice("← Back", "back"),
        ],
    ).ask_async()

    if source == "back":
        return

    # Get watermark text
    watermark = await questionary.text(
        "Watermark text:",
        default=config.watermark_text,
    ).ask_async()

    # Get position
    position = await questionary.select(
        "Watermark position:",
        choices=[
            questionary.Choice("Bottom", "bottom"),
            questionary.Choice("Top", "top"),
            questionary.Choice("Corner", "corner"),
        ],
    ).ask_async()

    if source == "all":
        console.print(f"[cyan]Marking posters in {config.posters_dir}...[/cyan]")
        mark_posters(config.posters_dir, watermark, position)
    else:  # csv
        csv_path = await questionary.path(
            "Path to CSV file:",
            default=str(config.cache_dir / "movies.csv"),
        ).ask_async()

        console.print("[cyan]Marking from CSV...[/cyan]")
        marker = PosterMarker(text=watermark, position=position)
        marker.mark_from_csv(Path(csv_path))

    console.print("[green]✓ Marking complete![/green]")
    await questionary.press_any_key_to_continue().ask_async()


async def export_menu():
    """Export menu."""
    console.print("[bold yellow]📤 Export Data[/bold yellow]")
    console.print()

    format_choice = await questionary.select(
        "Export format:",
        choices=[
            questionary.Choice("Pinterest CSV (with titles)", "pinterest"),
            questionary.Choice("Simple CSV (genre, file, link)", "simple"),
            questionary.Choice("Summary statistics", "summary"),
            questionary.Choice("← Back", "back"),
        ],
    ).ask_async()

    if format_choice == "back":
        return

    collages_csv = config.cache_dir / "collages.csv"

    if format_choice == "summary":
        export_summary(collages_csv, config.cache_dir / "movies_clean.csv")
    elif format_choice == "pinterest":
        export_pinterest_csv(collages_csv)
    else:  # simple
        export_simple_collages_csv(collages_csv)

    console.print("[green]✓ Export complete![/green]")
    await questionary.press_any_key_to_continue().ask_async()


async def queue_menu():
    """SQLite queue menu for n8n/Pinterest automation."""
    while True:
        console.print("[bold yellow]🧰 Queue / n8n / Pinterest[/bold yellow]")
        console.print()

        action = await questionary.select(
            "Queue action:",
            choices=[
                questionary.Choice("🗄️ Init DB", "init"),
                questionary.Choice("🔄 Sync ALL CSV -> DB", "sync_all"),
                questionary.Choice("🔄 Sync pins.csv -> queue", "sync"),
                questionary.Choice("📊 DB stats", "stats"),
                questionary.Choice("📋 Show ready jobs", "ready"),
                questionary.Choice("✅ Mark job posted", "posted"),
                questionary.Choice("❌ Mark job failed", "failed"),
                questionary.Choice("← Back", "back"),
            ],
        ).ask_async()

        if action == "back":
            return

        if action == "init":
            path = init_db()
            console.print(f"[green]✓ DB initialized: {path}[/green]")

        elif action == "sync_all":
            out = sync_all_from_csv(config.cache_dir)
            console.print(f"[green]✓ Synced ALL CSV -> DB: {out}[/green]")

        elif action == "sync":
            pins_csv = config.cache_dir / "pins.csv"
            if not pins_csv.exists():
                console.print(f"[red]Error: {pins_csv} not found. Run Export first.[/red]")
            else:
                inserted = sync_pins_csv(pins_csv)
                console.print(f"[green]✓ Synced queue. Inserted: {inserted}[/green]")

        elif action == "stats":
            console.print(f"[cyan]DB counts:[/cyan] {db_counts()}")

        elif action == "ready":
            limit_str = await questionary.text("Limit:", default="20").ask_async()
            limit = int(limit_str) if (limit_str or "").isdigit() else 20
            rows = get_ready_jobs(limit=limit)
            if not rows:
                console.print("[yellow]No ready jobs.[/yellow]")
            else:
                t = Table(title=f"Ready jobs ({len(rows)})", show_header=True, header_style="bold magenta")
                t.add_column("ID", style="cyan")
                t.add_column("Title", style="green")
                t.add_column("Board", style="yellow")
                t.add_column("Image", style="dim")
                for r in rows:
                    t.add_row(str(r.get("id")), r.get("title", "")[:80], r.get("board_id") or r.get("board") or "-", r.get("image_url", "")[:60])
                console.print(t)

        elif action == "posted":
            job_id = await questionary.text("Job ID:").ask_async()
            pin_id = await questionary.text("Pinterest pin ID:").ask_async()
            if (job_id or "").isdigit() and pin_id:
                mark_posted(int(job_id), pin_id)
                console.print(f"[green]✓ Job {job_id} marked posted[/green]")
            else:
                console.print("[red]Invalid job id or pin id[/red]")

        elif action == "failed":
            job_id = await questionary.text("Job ID:").ask_async()
            err = await questionary.text("Error message:", default="Pinterest API error").ask_async()
            if (job_id or "").isdigit():
                mark_failed(int(job_id), err or "unknown error")
                console.print(f"[yellow]⚠ Job {job_id} marked failed[/yellow]")
            else:
                console.print("[red]Invalid job id[/red]")

        console.print()
        await questionary.press_any_key_to_continue().ask_async()


async def clean_menu():
    """Clean menu."""
    console.print("[bold yellow]🗑️  Clean Data[/bold yellow]")
    console.print()

    choices = await questionary.checkbox(
        "What to clean?",
        choices=[
            questionary.Choice("Cache (CSV files)", "cache"),
            questionary.Choice("Collages", "collages"),
            questionary.Choice("All data", "all"),
        ],
        validate=lambda x: len(x) > 0,
    ).ask_async()

    if not choices:
        return

    confirm = await questionary.confirm(
        f"This will delete: {', '.join(choices)}. Continue?",
        default=False,
    ).ask_async()

    if not confirm:
        console.print("[yellow]Cancelled.[/yellow]")
        await questionary.press_any_key_to_continue().ask_async()
        return

    import shutil

    if "all" in choices:
        if config.cache_dir.exists():
            shutil.rmtree(config.cache_dir)
            config.cache_dir.mkdir(parents=True, exist_ok=True)
        if config.collages_dir.exists():
            shutil.rmtree(config.collages_dir)
            config.collages_dir.mkdir(parents=True, exist_ok=True)
    else:
        if "cache" in choices and config.cache_dir.exists():
            shutil.rmtree(config.cache_dir)
            config.cache_dir.mkdir(parents=True, exist_ok=True)
        if "collages" in choices and config.collages_dir.exists():
            shutil.rmtree(config.collages_dir)
            config.collages_dir.mkdir(parents=True, exist_ok=True)

    console.print("[green]✓ Clean complete![/green]")
    await questionary.press_any_key_to_continue().ask_async()


async def settings_menu():
    """Settings menu."""
    console.print("[bold yellow]⚙️  Settings[/bold yellow]")
    console.print()

    # Show current settings
    table = Table(show_header=False)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("API Key", "***" + (config.kinopoisk_api_key[-4:] if config.kinopoisk_api_key else " (not set)"))
    table.add_row("Data Dir", str(config.data_dir))
    table.add_row("Watermark", config.watermark_text)
    table.add_row("Tile Size", f"{config.collage_tile_width}x{config.collage_tile_height}")
    table.add_row("Max per Genre", str(config.collage_max_per_genre or "unlimited"))

    console.print(table)
    console.print()

    action = await questionary.select(
        "What to change?",
        choices=[
            questionary.Choice("API Key", "api"),
            questionary.Choice("Watermark text", "watermark"),
            questionary.Choice("Max collages per genre", "max_genre"),
            questionary.Choice("← Back", "back"),
        ],
    ).ask_async()

    if action == "back":
        return
    elif action == "api":
        new_key = await questionary.password("Enter new API Key:").ask_async()
        if new_key:
            config.kinopoisk_api_key = new_key
            console.print("[green]✓ API Key updated![/green]")
    elif action == "watermark":
        new_text = await questionary.text(
            "Enter watermark text:",
            default=config.watermark_text,
        ).ask_async()
        config.watermark_text = new_text
        console.print("[green]✓ Watermark updated![/green]")
    elif action == "max_genre":
        new_max = await questionary.text(
            "Max collages per genre (empty for unlimited):",
            default=str(config.collage_max_per_genre or ""),
        ).ask_async()
        config.collage_max_per_genre = int(new_max) if new_max.isdigit() else None
        console.print("[green]✓ Setting updated![/green]")

    console.print()
    await questionary.press_any_key_to_continue().ask_async()


async def main_menu():
    """Main interactive menu."""
    while True:
        print_header()
        print_status()

        choice = await questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Separator(),
                questionary.Choice("📥 Download posters", "download"),
                questionary.Choice("🔄 Process data", "process"),
                questionary.Choice("🖼️  Create collages", "collage"),
                questionary.Choice("✏️  Mark posters", "mark"),
                questionary.Choice("📤 Export data", "export"),
                questionary.Choice("🧰 Queue / n8n / Pinterest", "queue"),
                questionary.Choice("🗑️  Clean data", "clean"),
                questionary.Choice("⚙️  Settings", "settings"),
                questionary.Separator(),
                questionary.Choice("❌ Exit", "exit"),
            ],
        ).ask_async()

        if choice == "exit":
            console.print("[cyan]Goodbye! 👋[/cyan]")
            break
        elif choice == "download":
            await download_menu()
        elif choice == "process":
            await process_menu()
        elif choice == "collage":
            await collage_menu()
        elif choice == "mark":
            await mark_menu()
        elif choice == "export":
            await export_menu()
        elif choice == "queue":
            await queue_menu()
        elif choice == "clean":
            await clean_menu()
        elif choice == "settings":
            await settings_menu()


def interactive():
    """Run interactive CLI."""
    import asyncio

    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")


@click.command()
@click.pass_context
def interactive_cmd(ctx):
    """Launch interactive menu mode."""
    interactive()
