"""Interactive CLI menu with keyboard navigation."""

import shutil
from pathlib import Path
from typing import Optional

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kinopois import __version__
from kinopois.config import config
from kinopois.download.scraper import KinopoiskScraper
from kinopois.processing.collage import create_collages
from kinopois.processing.marker import mark_posters, PosterMarker
from kinopois.processing.processor import load_clean_movies, load_movies
from kinopois.publishing.collage_export import (
    export_pinterest_csv,
    export_simple_collages_csv,
    export_summary,
)
from kinopois.publishing.db import sync_all_from_csv
from kinopois.publishing.postgres_queue import (
    db_counts,
    get_ready_jobs,
    init_db,
    mark_failed,
    mark_posted,
    sync_pin_rows,
)
from kinopois.utils import read_csv_dict

console = Console()


def print_header():
    """Print application header."""
    header = Panel.fit(
        "[bold cyan]Kinopoisk Poster Downloader[/bold cyan]\n"
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

    posters_count = len(list(config.posters_dir.glob("*.jpg"))) if config.posters_dir.exists() else 0
    collages_count = len(list(config.collages_dir.glob("*.jpg"))) if config.collages_dir.exists() else 0

    table.add_row("Posters", str(posters_count), str(config.posters_dir))
    table.add_row("Collages", str(collages_count), str(config.collages_dir))

    cache_files = []
    if config.cache_dir.exists():
        for csv_file in ["movies.csv", "movies_clean.csv", "collages.csv", "pins.csv"]:
            if (config.cache_dir / csv_file).exists():
                cache_files.append(csv_file)

    table.add_row("Cache files", str(len(cache_files)), str(config.cache_dir))

    try:
        init_db()
        counts = db_counts()
        table.add_row("Queue ready", str(counts.get("ready", 0)), f"{config.queue_db_host}:{config.queue_db_port}/{config.queue_db_name}")
        table.add_row("Queue posted", str(counts.get("posted", 0)), f"{config.queue_db_host}:{config.queue_db_port}/{config.queue_db_name}")
        table.add_row("Queue failed", str(counts.get("failed", 0)), f"{config.queue_db_host}:{config.queue_db_port}/{config.queue_db_name}")
    except Exception:
        pass

    console.print(table)
    console.print()


def download_menu():
    """Download menu with options."""
    console.print("[bold yellow]Download Posters[/bold yellow]")
    console.print()

    limit = questionary.text(
        "How many movies to download?",
        default="200",
        validate=lambda x: x.isdigit() and int(x) > 0,
    ).ask()

    if not limit:
        return
    limit = int(limit)

    if not config.kinopoisk_api_key:
        console.print("[red]Error: KINOPOISK_API_KEY is not set![/red]")
        if questionary.confirm("Enter API key now?", default=True).ask():
            config.kinopoisk_api_key = questionary.password("API Key:").ask()
        else:
            return

    console.print(f"[cyan]Downloading {limit} movies...[/cyan]")
    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    scraper.download_and_save(limit=limit)
    console.print("[green]+ Download complete![/green]")
    questionary.press_any_key_to_continue().ask()


def process_menu():
    """Process menu."""
    console.print("[bold yellow]Process Data[/bold yellow]")
    console.print()

    input_csv = config.cache_dir / "movies.csv"
    output_csv = config.cache_dir / "movies_clean.csv"

    if not input_csv.exists():
        console.print(f"[red]Error: {input_csv} not found![/red]")
        console.print("Run 'Download' first to get movie data.")
        questionary.press_any_key_to_continue().ask()
        return

    console.print(f"[dim]Input:  {input_csv}[/dim]")
    console.print(f"[dim]Output: {output_csv}[/dim]")
    console.print()

    processor = load_movies(input_csv)
    processor.clean(output_csv)
    console.print("[green]+ Processing complete![/green]")
    questionary.press_any_key_to_continue().ask()


def collage_menu():
    """Collage creation menu."""
    console.print("[bold yellow]Create Collages[/bold yellow]")
    console.print()

    input_csv = config.cache_dir / "movies_clean.csv"
    if not input_csv.exists():
        console.print(f"[red]Error: {input_csv} not found![/red]")
        console.print("Run 'Process Data' first.")
        questionary.press_any_key_to_continue().ask()
        return

    add_watermark = questionary.confirm("Add watermark?", default=True).ask()
    watermark = ""
    if add_watermark:
        watermark = questionary.text("Watermark text:", default=config.watermark_text).ask() or ""

    limit_genre = questionary.confirm("Limit collages per genre?", default=False).ask()
    max_per_genre = None
    if limit_genre:
        max_str = questionary.text("Maximum per genre:", default="5").ask()
        max_per_genre = int(max_str) if (max_str or "").isdigit() else None

    console.print("[cyan]Creating collages...[/cyan]")
    create_collages(
        input_csv=input_csv,
        watermark=watermark if add_watermark else None,
        max_per_genre=max_per_genre,
    )
    console.print("[green]+ Collages created![/green]")
    questionary.press_any_key_to_continue().ask()


def mark_menu():
    """Mark posters menu."""
    console.print("[bold yellow]Mark Posters[/bold yellow]")
    console.print()

    source = questionary.select(
        "Mark all posters or specific files?",
        choices=[
            questionary.Choice("All posters in data/posters", "all"),
            questionary.Choice("From CSV file", "csv"),
            questionary.Choice("Back", "back"),
        ],
    ).ask()

    if source == "back" or not source:
        return

    watermark = questionary.text("Watermark text:", default=config.watermark_text).ask() or config.watermark_text

    position = questionary.select(
        "Watermark position:",
        choices=[
            questionary.Choice("Bottom", "bottom"),
            questionary.Choice("Top", "top"),
            questionary.Choice("Corner", "corner"),
        ],
    ).ask()

    if source == "all":
        console.print(f"[cyan]Marking posters in {config.posters_dir}...[/cyan]")
        mark_posters(config.posters_dir, watermark, position)
    else:
        csv_path = questionary.path("Path to CSV file:", default=str(config.cache_dir / "movies.csv")).ask()
        console.print("[cyan]Marking from CSV...[/cyan]")
        marker = PosterMarker(text=watermark, position=position)
        marker.mark_from_csv(Path(csv_path))

    console.print("[green]+ Marking complete![/green]")
    questionary.press_any_key_to_continue().ask()


def export_menu():
    """Export menu."""
    console.print("[bold yellow]Export Data[/bold yellow]")
    console.print()

    format_choice = questionary.select(
        "Export format:",
        choices=[
            questionary.Choice("Pinterest CSV (with titles)", "pinterest"),
            questionary.Choice("Simple CSV (genre, file, link)", "simple"),
            questionary.Choice("Summary statistics", "summary"),
            questionary.Choice("Back", "back"),
        ],
    ).ask()

    if format_choice == "back" or not format_choice:
        return

    collages_csv = config.cache_dir / "collages.csv"

    if format_choice == "summary":
        export_summary(collages_csv, config.cache_dir / "movies_clean.csv")
    elif format_choice == "pinterest":
        export_pinterest_csv(collages_csv)
    else:
        export_simple_collages_csv(collages_csv)

    console.print("[green]+ Export complete![/green]")
    questionary.press_any_key_to_continue().ask()


def queue_menu():
    """Local queue menu for Pinterest automation."""
    while True:
        console.print("[bold yellow]Queue / n8n / Pinterest[/bold yellow]")
        console.print()

        action = questionary.select(
            "Queue action:",
            choices=[
                questionary.Choice("Init queue DB", "init"),
                questionary.Choice("Sync ALL CSV -> DB", "sync_all"),
                questionary.Choice("Sync pins.csv -> Postgres", "sync"),
                questionary.Choice("DB stats", "stats"),
                questionary.Choice("Show ready jobs", "ready"),
                questionary.Choice("Mark job posted", "posted"),
                questionary.Choice("Mark job failed", "failed"),
                questionary.Choice("Back", "back"),
            ],
        ).ask()

        if action == "back" or not action:
            return

        if action == "init":
            init_db()
            console.print("[green]+ Queue DB initialized[/green]")

        elif action == "sync_all":
            out = sync_all_from_csv(config.cache_dir)
            console.print(f"[green]+ Synced ALL CSV -> DB: {out}[/green]")

        elif action == "sync":
            pins_csv = config.cache_dir / "pins.csv"
            if not pins_csv.exists():
                console.print(f"[red]Error: {pins_csv} not found. Run Export first.[/red]")
            else:
                inserted = sync_pin_rows(read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding))
                console.print(f"[green]+ Synced queue to Postgres. Inserted: {inserted}[/green]")

        elif action == "stats":
            console.print(f"[cyan]Queue counts:[/cyan] {db_counts()}")

        elif action == "ready":
            limit_str = questionary.text("Limit:", default="20").ask()
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
            job_id = questionary.text("Job ID:").ask()
            pin_id = questionary.text("Pinterest pin ID:").ask()
            if (job_id or "").isdigit() and pin_id:
                mark_posted(int(job_id), pin_id)
                console.print(f"[green]+ Job {job_id} marked posted[/green]")
            else:
                console.print("[red]Invalid job id or pin id[/red]")

        elif action == "failed":
            job_id = questionary.text("Job ID:").ask()
            err = questionary.text("Error message:", default="Pinterest API error").ask()
            if (job_id or "").isdigit():
                mark_failed(int(job_id), err or "unknown error")
                console.print(f"[yellow]Job {job_id} marked failed[/yellow]")
            else:
                console.print("[red]Invalid job id[/red]")

        console.print()
        questionary.press_any_key_to_continue().ask()


def clean_menu():
    """Clean menu."""
    console.print("[bold yellow]Clean Data[/bold yellow]")
    console.print()

    choices = questionary.checkbox(
        "What to clean?",
        choices=[
            questionary.Choice("Cache (CSV files)", "cache"),
            questionary.Choice("Collages", "collages"),
            questionary.Choice("All data", "all"),
        ],
        validate=lambda x: len(x) > 0,
    ).ask()

    if not choices:
        return

    confirm = questionary.confirm(
        f"This will delete: {', '.join(choices)}. Continue?",
        default=False,
    ).ask()

    if not confirm:
        console.print("[yellow]Cancelled.[/yellow]")
        questionary.press_any_key_to_continue().ask()
        return

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

    console.print("[green]+ Clean complete![/green]")
    questionary.press_any_key_to_continue().ask()


def settings_menu():
    """Settings menu."""
    console.print("[bold yellow]Settings[/bold yellow]")
    console.print()

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

    action = questionary.select(
        "What to change?",
        choices=[
            questionary.Choice("API Key", "api"),
            questionary.Choice("Watermark text", "watermark"),
            questionary.Choice("Max collages per genre", "max_genre"),
            questionary.Choice("Back", "back"),
        ],
    ).ask()

    if action == "back" or not action:
        return
    elif action == "api":
        new_key = questionary.password("Enter new API Key:").ask()
        if new_key:
            config.kinopoisk_api_key = new_key
            console.print("[green]+ API Key updated![/green]")
    elif action == "watermark":
        new_text = questionary.text("Enter watermark text:", default=config.watermark_text).ask()
        config.watermark_text = new_text
        console.print("[green]+ Watermark updated![/green]")
    elif action == "max_genre":
        new_max = questionary.text(
            "Max collages per genre (empty for unlimited):",
            default=str(config.collage_max_per_genre or ""),
        ).ask()
        config.collage_max_per_genre = int(new_max) if (new_max or "").isdigit() else None
        console.print("[green]+ Setting updated![/green]")

    console.print()
    questionary.press_any_key_to_continue().ask()


def interactive():
    """Run interactive CLI."""
    try:
        while True:
            print_header()
            print_status()

            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Separator(),
                    questionary.Choice("Download posters", "download"),
                    questionary.Choice("Process data", "process"),
                    questionary.Choice("Create collages", "collage"),
                    questionary.Choice("Mark posters", "mark"),
                    questionary.Choice("Export data", "export"),
                    questionary.Choice("Queue / n8n / Pinterest", "queue"),
                    questionary.Choice("Clean data", "clean"),
                    questionary.Choice("Settings", "settings"),
                    questionary.Separator(),
                    questionary.Choice("Exit", "exit"),
                ],
            ).ask()

            if choice == "exit" or not choice:
                console.print("[cyan]Goodbye![/cyan]")
                break
            elif choice == "download":
                download_menu()
            elif choice == "process":
                process_menu()
            elif choice == "collage":
                collage_menu()
            elif choice == "mark":
                mark_menu()
            elif choice == "export":
                export_menu()
            elif choice == "queue":
                queue_menu()
            elif choice == "clean":
                clean_menu()
            elif choice == "settings":
                settings_menu()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")