"""
Sentinel Gateway — Live Terminal Dashboard
Run: sentinel-dashboard (or python dashboard.py)
"""
 
import json
import os
import time
from datetime import datetime
from pathlib import Path
 
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.columns import Columns
from rich.align import Align
 
# ── Config ─────────────────────────────────────────────────────────────────
LOG_FILE = Path(os.environ.get("SENTINEL_LOG", Path.home() / ".sentinel" / "sentinel.log"))
MAX_ROWS = 12          # max requests shown in table
REFRESH_RATE = 0.5     # seconds between refreshes
 
# ── Pricing (per 1M tokens) ─────────────────────────────────────────────────
PRICING = {
    "claude-opus":    {"input": 15.00, "output": 75.00},
    "claude-sonnet":  {"input":  3.00, "output": 15.00},
    "claude-haiku":   {"input":  0.25, "output":  1.25},
    "default":        {"input":  3.00, "output": 15.00},
}
 
def get_price(model: str, input_tokens: int, output_tokens: int) -> float:
    key = next((k for k in PRICING if k in model.lower()), "default")
    p = PRICING[key]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
 
# ── Log reader ──────────────────────────────────────────────────────────────
def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    # plain text log line — wrap it
                    entries.append({"type": "raw", "message": line,
                                    "timestamp": datetime.now().isoformat()})
    except Exception:
        pass
    return entries
 
# ── Stats calculator ────────────────────────────────────────────────────────
def calc_stats(entries: list[dict]) -> dict:
    requests     = [e for e in entries if e.get("type") == "request"]
    total_cost   = sum(e.get("cost", 0) for e in requests)
    total_input  = sum(e.get("input_tokens", 0) for e in requests)
    total_output = sum(e.get("output_tokens", 0) for e in requests)
    secrets      = sum(e.get("secrets_found", 0) for e in requests)
    blocked      = sum(1 for e in requests if e.get("blocked", False))
    return {
        "total_requests": len(requests),
        "total_cost":     total_cost,
        "total_input":    total_input,
        "total_output":   total_output,
        "secrets_found":  secrets,
        "blocked":        blocked,
        "last_ts":        requests[-1].get("timestamp", "—") if requests else "—",
    }
 
# ── UI builders ─────────────────────────────────────────────────────────────
def make_header() -> Panel:
    now = datetime.now().strftime("%H:%M:%S")
    title = Text()
    title.append("⬡ SENTINEL", style="bold cyan")
    title.append("  LIVE", style="bold red blink")
    title.append(f"   {now}", style="dim white")
    return Panel(Align.center(title), style="cyan", height=3)
 
def make_stat_card(label: str, value: str, color: str = "white") -> Panel:
    content = Align.center(
        Text(value, style=f"bold {color}") 
    )
    return Panel(content, title=f"[dim]{label}[/dim]",
                 border_style=color, height=5)
 
def make_stats_row(stats: dict) -> Columns:
    cost_color    = "red"    if stats["total_cost"] > 5 else \
                    "yellow" if stats["total_cost"] > 1 else "green"
    secret_color  = "red"    if stats["secrets_found"] > 0 else "green"
    blocked_color = "yellow" if stats["blocked"] > 0 else "dim white"
 
    cards = [
        make_stat_card("REQUESTS",      str(stats["total_requests"]),        "cyan"),
        make_stat_card("SESSION COST",  f'${stats["total_cost"]:.4f}',       cost_color),
        make_stat_card("TOKENS IN",     f'{stats["total_input"]:,}',         "blue"),
        make_stat_card("TOKENS OUT",    f'{stats["total_output"]:,}',        "magenta"),
        make_stat_card("SECRETS FOUND", str(stats["secrets_found"]),         secret_color),
        make_stat_card("BLOCKED",       str(stats["blocked"]),               blocked_color),
    ]
    return Columns(cards, equal=True, expand=True)
 
def make_table(entries: list[dict]) -> Panel:
    requests = [e for e in entries if e.get("type") == "request"][-MAX_ROWS:]
    requests.reverse()   # newest first
 
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        row_styles=["", "dim"],
    )
    table.add_column("TIME",     width=10)
    table.add_column("MODEL",    width=16)
    table.add_column("IN",       width=8,  justify="right")
    table.add_column("OUT",      width=8,  justify="right")
    table.add_column("COST",     width=10, justify="right")
    table.add_column("SECRETS",  width=9,  justify="center")
    table.add_column("PROMPT PREVIEW", min_width=20)
 
    for e in requests:
        ts      = e.get("timestamp", "")[-8:]          # HH:MM:SS
        model   = e.get("model", "unknown")
        model   = model.split("-202")[0]                # strip date suffix
        inp     = e.get("input_tokens", 0)
        out     = e.get("output_tokens", 0)
        cost    = e.get("cost", get_price(model, inp, out))
        secrets = e.get("secrets_found", 0)
        preview = e.get("prompt_preview", e.get("message", ""))[:60]
        blocked = e.get("blocked", False)
 
        secret_cell = Text("⚠ " + str(secrets), style="bold red") \
                      if secrets > 0 else Text("✓ 0", style="green")
        cost_cell   = Text(f"${cost:.4f}",
                           style="yellow" if cost > 0.05 else "white")
        model_cell  = Text(model, style="bold magenta" if "opus" in model.lower()
                           else "cyan" if "sonnet" in model.lower() else "white")
        row_style   = "on red" if blocked else ""
 
        table.add_row(ts, model_cell, f"{inp:,}", f"{out:,}",
                      cost_cell, secret_cell, preview,
                      style=row_style)
 
    if not requests:
        table.add_row("—", "—", "—", "—", "—", "—",
                      "[dim italic]Waiting for requests…[/dim italic]")
 
    return Panel(table, title="[bold cyan]INTERCEPTED REQUESTS[/bold cyan]",
                 border_style="cyan")
 
def make_footer(log_path: Path) -> Panel:
    path_text = Text(f"  Watching: {log_path}", style="dim")
    hint_text = Text("  Ctrl+C to exit", style="dim")
    content   = Columns([path_text, hint_text], expand=True)
    return Panel(content, style="dim", height=3)
 
# ── Main layout builder ─────────────────────────────────────────────────────
def build_layout(entries: list[dict], log_path: Path) -> Layout:
    stats  = calc_stats(entries)
    layout = Layout()
 
    layout.split_column(
        Layout(make_header(),          name="header",  size=3),
        Layout(make_stats_row(stats),  name="stats",   size=7),
        Layout(make_table(entries),    name="table"),
        Layout(make_footer(log_path),  name="footer",  size=3),
    )
    return layout
 
# ── Entry point ─────────────────────────────────────────────────────────────
def run():
    console = Console()
    log_path = LOG_FILE
 
    # Auto-detect log path if default doesn't exist
    fallback_paths = [
        Path("sentinel.log"),
        Path.home() / ".sentinel" / "sentinel.log",
        Path("/tmp/sentinel.log"),
    ]
    if not log_path.exists():
        for p in fallback_paths:
            if p.exists():
                log_path = p
                break
 
    console.clear()
    console.print(f"\n[cyan]⬡ Sentinel Dashboard[/cyan] — watching [dim]{log_path}[/dim]\n")
 
    if not log_path.exists():
        console.print(f"[yellow]Log file not found. Start Sentinel first:[/yellow]")
        console.print(f"  [bold]sentinel[/bold]")
        console.print(f"  [bold]export ANTHROPIC_BASE_URL=http://localhost:8080/anthropic[/bold]\n")
        console.print(f"[dim]Will start displaying once requests come in…[/dim]\n")
 
    try:
        with Live(console=console, refresh_per_second=int(1 / REFRESH_RATE),
                  screen=True) as live:
            while True:
                entries = read_log(log_path)
                live.update(build_layout(entries, log_path))
                time.sleep(REFRESH_RATE)
    except KeyboardInterrupt:
        console.clear()
        console.print("\n[cyan]⬡ Sentinel Dashboard stopped.[/cyan]\n")
 
if __name__ == "__main__":
    run()