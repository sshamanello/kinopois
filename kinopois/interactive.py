"""Interactive CLI menu with keyboard navigation."""

import click
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kinopois import __version__
from kinopois.collage import create_collages
from kinopois.config import config
from kinopois.database import Database
from kinopois.export import export_for_pinterest
from kinopois.marker import mark_posters
from kinopois.scraper import KinopoiskScraper

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
    db_path = config.data_dir / "kinopois.db"

    if not db_path.exists():
        console.print("[yellow]Database not found. Download movies first.[/yellow]\n")
        return

    with Database() as db:
        stats = db.get_stats()

        table = Table(title="Project Status", show_header=True, header_style="bold magenta")
        table.add_column("Resource", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Path", style="dim")

        # Count files
        posters_count = len(list(config.posters_dir.glob("*.jpg"))) if config.posters_dir.exists() else 0
        collages_count = len(list(config.collages_dir.glob("*.jpg"))) if config.collages_dir.exists() else 0

        table.add_row("Movies", str(stats['movies']), str(db_path))
        table.add_row("Collages", str(stats['collages']), str(config.collages_dir))
        table.add_row("Posters", str(posters_count), str(config.posters_dir))

        console.print(table)

        # Show top genres
        if stats['by_genre']:
            console.print()
            console.print("[dim]Top genres:[/dim]")
            for genre, count in list(stats['by_genre'].items())[:5]:
                console.print(f"  [cyan]{genre}:[/cyan] {count} movies")

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
            input("\nPress Enter to continue...")
            return

    console.print(f"[cyan]Downloading {limit} movies...[/cyan]")

    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    scraper.download_and_save(limit=limit)

    console.print("[green]OK Download complete![/green]")
    input("\nPress Enter to continue...")


async def collage_menu():
    """Collage creation menu."""
    console.print("[bold yellow]🖼️  Create Collages[/bold yellow]")
    console.print()

    db_path = config.data_dir / "kinopois.db"
    if not db_path.exists():
        console.print("[red]Error: No database found![/red]")
        console.print("Run 'Download' first.")
        input("\nPress Enter to continue...")
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
        watermark=watermark if add_watermark else None,
        max_per_genre=max_per_genre,
    )

    console.print("[green]OK Collages created![/green]")
    input("\nPress Enter to continue...")


async def mark_menu():
    """Mark posters menu."""
    console.print("[bold yellow]✏️  Mark Posters[/bold yellow]")
    console.print()

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

    console.print(f"[cyan]Marking posters in {config.posters_dir}...[/cyan]")
    mark_posters(config.posters_dir, watermark, position)

    console.print("[green]OK Marking complete![/green]")
    input("\nPress Enter to continue...")


async def export_menu():
    """Export menu."""
    console.print("[bold yellow]📤 Export Data[/bold yellow]")
    console.print()

    format_choice = await questionary.select(
        "Export format:",
        choices=[
            questionary.Choice("Pinterest CSV", "pinterest"),
            questionary.Choice("Summary statistics", "summary"),
            questionary.Choice("← Back", "back"),
        ],
    ).ask_async()

    if format_choice == "back":
        return

    db_path = config.data_dir / "kinopois.db"
    if not db_path.exists():
        console.print("[red]Error: No database found![/red]")
        input("\nPress Enter to continue...")
        return

    with Database() as db:
        if format_choice == "summary":
            stats = db.get_stats()
            console.print("\n[bold]Database Statistics:[/bold]")
            console.print(f"  Movies: {stats['movies']}")
            console.print(f"  Collages: {stats['collages']}")
            if stats['by_genre']:
                console.print("\n  [bold]By Genre:[/bold]")
                for genre, count in list(stats['by_genre'].items())[:10]:
                    console.print(f"    {genre}: {count}")
        elif format_choice == "pinterest":
            export_for_pinterest(db)

    console.print("[green]OK Export complete![/green]")
    input("\nPress Enter to continue...")


async def clean_menu():
    """Clean menu."""
    console.print("[bold yellow]🗑️  Clean Data[/bold yellow]")
    console.print()

    choices = await questionary.checkbox(
        "What to clean?",
        choices=[
            questionary.Choice("Database (kinopois.db)", "db"),
            questionary.Choice("Collages", "collages"),
            questionary.Choice("Posters", "posters"),
            questionary.Choice("All data", "all"),
        ],
        validate=lambda x: len(x) > 0,
    ).ask_async()

    if not choices:
        return

    import shutil

    confirm = await questionary.confirm(
        f"This will delete: {', '.join(choices)}. Continue?",
        default=False,
    ).ask_async()

    if not confirm:
        console.print("[yellow]Cancelled.[/yellow]")
        input("\nPress Enter to continue...")
        return

    if "all" in choices:
        db_path = config.data_dir / "kinopois.db"
        if db_path.exists():
            db_path.unlink()
            console.print(f"[cyan]Removed: {db_path}[/cyan]")
        if config.collages_dir.exists():
            shutil.rmtree(config.collages_dir)
            config.collages_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[cyan]Cleared: {config.collages_dir}[/cyan]")
        if config.posters_dir.exists():
            shutil.rmtree(config.posters_dir)
            config.posters_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[cyan]Cleared: {config.posters_dir}[/cyan]")
    else:
        if "db" in choices:
            db_path = config.data_dir / "kinopois.db"
            if db_path.exists():
                db_path.unlink()
                console.print(f"[cyan]Removed: {db_path}[/cyan]")
        if "collages" in choices and config.collages_dir.exists():
            shutil.rmtree(config.collages_dir)
            config.collages_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[cyan]Cleared: {config.collages_dir}[/cyan]")
        if "posters" in choices and config.posters_dir.exists():
            shutil.rmtree(config.posters_dir)
            config.posters_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[cyan]Cleared: {config.posters_dir}[/cyan]")

    console.print("[green]OK Clean complete![/green]")
    input("\nPress Enter to continue...")


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
            console.print("[green]OK API Key updated![/green]")
    elif action == "watermark":
        new_text = await questionary.text(
            "Enter watermark text:",
            default=config.watermark_text,
        ).ask_async()
        config.watermark_text = new_text
        console.print("[green]OK Watermark updated![/green]")
    elif action == "max_genre":
        new_max = await questionary.text(
            "Max collages per genre (empty for unlimited):",
            default=str(config.collage_max_per_genre or ""),
        ).ask_async()
        config.collage_max_per_genre = int(new_max) if new_max.isdigit() else None
        console.print("[green]OK Setting updated![/green]")

    console.print()
    input("\nPress Enter to continue...")


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
                questionary.Choice("🖼️  Create collages", "collage"),
                questionary.Choice("✏️  Mark posters", "mark"),
                questionary.Choice("📤 Export data", "export"),
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
        elif choice == "collage":
            await collage_menu()
        elif choice == "mark":
            await mark_menu()
        elif choice == "export":
            await export_menu()
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
