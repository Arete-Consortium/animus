#!/usr/bin/env python3
"""
Animus Learning System Demo

This script demonstrates Animus's ability to learn from interactions
and persist that learning across sessions.

Run with: python examples/learning_demo.py
"""

import sys
import tempfile
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from animus.config import AnimusConfig
from animus.learning import LearningLayer
from animus.memory import MemoryLayer, MemoryType
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_section(title: str):
    """Print a section header."""
    console.print(f"\n[bold cyan]{'=' * 60}[/]")
    console.print(f"[bold cyan]{title}[/]")
    console.print(f"[bold cyan]{'=' * 60}[/]\n")


def main():
    console.print(
        Panel.fit(
            "[bold green]Animus Learning System Demo[/]\n"
            "Demonstrating persistent learning across sessions",
            title="🧠 Animus",
        )
    )

    # Create temporary data directory for demo
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        console.print(f"[dim]Demo data directory: {data_dir}[/]\n")

        # Initialize components
        config = AnimusConfig(data_dir=data_dir)
        config.ensure_dirs()

        memory = MemoryLayer(config.data_dir)
        learning = LearningLayer(memory, config.data_dir)

        # === SESSION 1: Initial Learning ===
        print_section("SESSION 1: Building Memories")

        # Simulate user interactions that create memories
        interactions = [
            ("User prefers concise responses", ["preference", "communication"]),
            ("User works on Python projects frequently", ["work", "programming"]),
            ("User schedules meetings in the morning", ["preference", "schedule"]),
            ("User prefers Python over JavaScript", ["preference", "programming"]),
            ("User's favorite IDE is VS Code", ["preference", "tools"]),
            ("User reviews code before merging PRs", ["work", "programming"]),
            ("User prefers dark mode interfaces", ["preference", "ui"]),
        ]

        console.print("[yellow]Adding memories from user interactions...[/]\n")
        for content, tags in interactions:
            memory.remember(
                content=content,
                memory_type=MemoryType.SEMANTIC,
                tags=tags,
                source="stated",
                confidence=0.9,
            )
            console.print(f"  ✓ Stored: [green]{content}[/]")

        console.print(f"\n[bold]Total memories stored: {len(memory.store.list_all())}[/]")

        # === SESSION 2: Pattern Detection ===
        print_section("SESSION 2: Learning from Patterns")

        console.print("[yellow]Running pattern detection...[/]\n")
        detected = learning.scan_and_learn()

        if detected:
            table = Table(title="Detected Patterns")
            table.add_column("Pattern", style="cyan")
            table.add_column("Category", style="green")
            table.add_column("Confidence", style="yellow")

            for pattern in detected:
                table.add_row(
                    pattern.description[:50] + "..."
                    if len(pattern.description) > 50
                    else pattern.description,
                    pattern.suggested_category.value
                    if hasattr(pattern.suggested_category, "value")
                    else str(pattern.suggested_category),
                    f"{pattern.confidence:.2f}",
                )

            console.print(table)
        else:
            console.print("[dim]No patterns detected (need more data for pattern recognition)[/]")

        # === SESSION 3: Learned Items ===
        print_section("SESSION 3: Active Learnings")

        console.print("[yellow]Reviewing active learned items...[/]\n")
        active = learning.get_active_learnings()

        if active:
            table = Table(title="Active Learnings")
            table.add_column("Learning", style="cyan")
            table.add_column("Category", style="green")
            table.add_column("Confidence", style="yellow")

            for item in active[:5]:  # Show top 5
                table.add_row(
                    item.content[:40] + "..." if len(item.content) > 40 else item.content,
                    item.category.value if hasattr(item.category, "value") else str(item.category),
                    f"{item.confidence:.2f}",
                )

            console.print(table)
        else:
            console.print("[dim]No active learnings yet (patterns need approval first)[/]")

        # === SESSION 4: Guardrails ===
        print_section("SESSION 4: Safety Guardrails")

        console.print("[yellow]Active guardrails:[/]\n")
        guardrails = learning.guardrails.get_all_guardrails()

        table = Table(title="Safety Guardrails")
        table.add_column("Rule", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Immutable", style="yellow")

        for g in guardrails:
            table.add_row(
                g.rule[:40] + "..." if len(g.rule) > 40 else g.rule,
                g.guardrail_type.value,
                "✓" if g.immutable else "✗",
            )

        console.print(table)

        # === SESSION 5: Learning Approval ===
        print_section("SESSION 5: Learning Approval Workflow")

        console.print("[yellow]Checking pending approvals...[/]\n")

        pending_items = learning.get_pending_learnings()
        console.print(f"[bold]Pending approvals: {len(pending_items)}[/]")

        if pending_items:
            console.print("\nItems awaiting approval:")
            for item in pending_items[:3]:
                console.print(
                    f"  • [cyan]{item.content[:50]}...[/]"
                    if len(item.content) > 50
                    else f"  • [cyan]{item.content}[/]"
                )

        # === SESSION 6: Persistence Demo ===
        print_section("SESSION 6: Persistence Across Sessions")

        console.print("[yellow]Saving state...[/]\n")

        # Create a checkpoint
        active_items = learning.get_active_learnings()
        checkpoint = learning.rollback.create_checkpoint("demo_checkpoint", active_items)
        console.print(f"  ✓ Created checkpoint: [cyan]{checkpoint.id[:8]}...[/]")

        # Show what persists
        console.print("\n[bold]What persists between sessions:[/]")
        console.print("  • Memories in the configured supported Core store")
        console.print("  • Learned preferences and patterns")
        console.print("  • User-defined guardrails")
        console.print("  • Pending approval queue")
        console.print("  • Learning transparency logs")
        console.print("  • Rollback checkpoints")

        # === Summary ===
        print_section("SUMMARY")

        stats = learning.get_statistics()
        summary = Table(title="Learning System Statistics")
        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", style="green")

        summary.add_row("Total Memories", str(len(memory.store.list_all())))
        summary.add_row("Active Learnings", str(stats.get("active_learnings", 0)))
        summary.add_row("Pending Approvals", str(stats.get("pending_approvals", 0)))
        summary.add_row("Core Guardrails", str(stats.get("guardrails", {}).get("core", 0)))
        summary.add_row("Checkpoints", str(stats.get("checkpoints", 0)))

        console.print(summary)

        console.print(
            Panel.fit(
                "[bold green]Demo Complete![/]\n\n"
                "Animus learns from your interactions, detects patterns,\n"
                "infers preferences, and persists everything across sessions.\n\n"
                "All learning is transparent, reversible, and respects guardrails.",
                title="✨",
            )
        )


if __name__ == "__main__":
    main()
