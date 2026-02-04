import time
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class IndustrialDashboard:
    """
    Industrial-grade TUI Dashboard for Casino-V3.
    Provides real-time visibility into parallel ingestion and strategy performance.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.start_time = time.time()
        self.console = Console()
        self._lock = Lock()
        self._live: Optional[Live] = None

        # Dashboard State
        self.state = {
            "status": "INITIALIZING",
            "shards": {},  # id: {status, msg_rate, latency}
            "breakers": {},  # name: status
            "pnl": 0.0,
            "trades_count": 0,
            "recent_trades": [],  # List of dicts
            "symbols_perf": {},  # symbol: {pnl, count}
            "audit_trail": [],  # List of most recent decisions
            "logs": [],  # List of strings (last 20)
        }

    def add_log(self, record: str):
        with self._lock:
            self.state["logs"].append(record)
            if len(self.state["logs"]) > 20:
                self.state["logs"].pop(0)

    def update_state(self, key: str, value: any):
        with self._lock:
            if key in self.state:
                self.state[key] = value

    def update_shard(self, shard_id: str, metrics: Dict):
        with self._lock:
            self.state["shards"][shard_id] = metrics

    def update_pnl(self, pnl: float, trades: int, symbols_perf: Dict):
        with self._lock:
            self.state["pnl"] = pnl
            self.state["trades_count"] = trades
            self.state["symbols_perf"] = symbols_perf

    def update_audit(self, decisions: List[Dict]):
        with self._lock:
            self.state["audit_trail"] = decisions[-10:]  # Keep last 10

    def stop(self):
        if self._live:
            self._live.stop()

    def start(self):
        self._live = Live(self._generate_layout(), refresh_per_second=4, screen=True)
        self._live.start()

    def _generate_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(Layout(name="header", size=3), Layout(name="body"), Layout(name="footer", ratio=1))
        layout["body"].split_row(
            Layout(name="left", ratio=1), Layout(name="center", ratio=2), Layout(name="right", ratio=1.5)
        )
        layout["left"].split_column(Layout(name="health"), Layout(name="breakers"))

        # Refresh the content
        layout["header"].update(self._make_header())
        layout["health"].update(self._make_health_table())
        layout["breakers"].update(self._make_breakers_panel())
        layout["center"].update(self._make_pnl_panel())
        layout["right"].update(self._make_audit_panel())
        layout["footer"].update(self._make_log_panel())

        return layout

    def _make_log_panel(self) -> Panel:
        with self._lock:
            # Join logs with newlines
            log_content = "\n".join(self.state["logs"])

        return Panel(
            Text(log_content, style="white"), title="[bold]Live Logs[/bold]", box=box.MINIMAL, border_style="dim"
        )

    def _make_header(self) -> Panel:
        uptime = str(datetime.now() - datetime.fromtimestamp(self.start_time)).split(".")[0]
        status_color = "green" if self.state["status"] == "RUNNING" else "yellow"
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right", ratio=1)
        grid.add_row(
            Text(" 🎰 Casino-V3", style="bold magenta"),
            Text(f"Session: {self.session_id}", style="bold cyan"),
            Text(f"Status: {self.state['status']} | Up: {uptime} ", style=f"bold {status_color}"),
        )
        return Panel(grid, style="white on blue", box=box.MINIMAL)

    def _make_health_table(self) -> Panel:
        table = Table(title="Ingestion Health (Sharding Phase 1)", expand=True, box=box.SIMPLE)
        table.add_column("Shard", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Rate", justify="right")
        table.add_column("Latency", justify="right")

        with self._lock:
            for shard_id, metrics in sorted(self.state["shards"].items()):
                status = metrics.get("status", "Unknown")
                status_style = "green" if status == "ALIVE" else "red"
                rate = f"{metrics.get('msg_rate', 0):.1f}/s"
                lat = metrics.get("latency", 0)
                lat_style = "green" if lat < 200 else "yellow" if lat < 500 else "red"

                table.add_row(shard_id, Text(status, style=status_style), rate, Text(f"{lat:.1f}ms", style=lat_style))

        return Panel(table, title="[bold]System Health[/bold]", border_style="blue")

    def _make_breakers_panel(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(style="bold")
        grid.add_column(justify="right")

        with self._lock:
            for name, status in self.state["breakers"].items():
                status_text = "CLOSED" if status == "closed" else "OPEN"
                status_style = "green" if status == "closed" else "bold red"
                grid.add_row(f" {name}", Text(status_text, style=status_style))

        return Panel(grid, title="[bold]Circuit Breakers[/bold]", border_style="yellow")

    def _make_pnl_panel(self) -> Panel:
        # PnL Summary Header
        pnl = self.state["pnl"]
        pnl_style = "bold green" if pnl >= 0 else "bold red"

        summary = Table.grid(expand=True)
        summary.add_row(
            Text(f" Net PnL: {pnl:+.4f} USDT", style=pnl_style),
            Text(f" Trades: {self.state['trades_count']}", style="bold white"),
        )

        # Performance Heatmap
        table = Table(show_header=True, header_style="bold magenta", expand=True, box=box.SIMPLE)
        table.add_column("Symbol", ratio=1)
        table.add_column("Net PnL", justify="right", ratio=1)
        table.add_column("Trades", justify="center", ratio=1)

        with self._lock:
            # Sort symbols by PnL
            sorted_symbols = sorted(self.state["symbols_perf"].items(), key=lambda x: x[1].get("pnl", 0), reverse=True)
            for sym, data in sorted_symbols[:15]:  # Show top 15
                spnl = data.get("pnl", 0)
                spnl_style = "green" if spnl >= 0 else "red"
                table.add_row(sym, Text(f"{spnl:+.4f}", style=spnl_style), str(data.get("count", 0)))

        return Panel(Group(summary, table), title="[bold]Strategy Performance (Real-time)[/bold]", border_style="green")

    def _make_audit_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold cyan", expand=True, box=box.SIMPLE)
        table.add_column("Trace", style="dim")
        table.add_column("Symbol", style="bold")
        table.add_column("Action", justify="center")
        table.add_column("Reason")

        with self._lock:
            for entry in reversed(self.state["audit_trail"]):
                action = entry.get("action", "SKIP")
                style = "bold green" if action == "LONG" else "bold red" if action == "SHORT" else "dim"

                table.add_row(
                    entry.get("trace_id", "N/A")[-6:],  # Short ID
                    entry.get("symbol", "N/A"),
                    Text(action, style=style),
                    entry.get("reason", "N/A"),
                )

        return Panel(table, title="[bold]Forensic Audit Trail (Phase 103)[/bold]", border_style="cyan")

    def refresh(self):
        if self._live:
            self._live.update(self._generate_layout())
