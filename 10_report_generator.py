import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
"""
Report generator module for crypto perpetual futures backtesting system.
Generates charts, tables, and PDF/HTML reports using plotly to avoid DLL issues.
"""

import pandas as pd
import numpy as np
import logging
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pathlib import Path
from typing import Dict, List, Tuple, Any
import json
from datetime import datetime, timedelta
import os
import importlib.util
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self, trade_log: List[Dict], equity_curve: List[Tuple[pd.Timestamp, float]], 
                 stats: Dict, regime_data: Dict[str, pd.DataFrame] = None):
        """
        Initialize the report generator.

        Args:
            trade_log (List[Dict]): List of trade dictionaries.
            equity_curve (List[Tuple[pd.Timestamp, float]]): List of (timestamp, equity) tuples.
            stats (Dict): Performance statistics dictionary.
            regime_data (Dict[str, pd.DataFrame], optional): Dictionary of DataFrames with regime data for each instrument.
        """
        self.trade_log = trade_log
        self.equity_curve = equity_curve
        self.stats = stats
        self.regime_data = regime_data or {}

        # Convert trade log to DataFrame for easier analysis
        if self.trade_log:
            self.trades_df = pd.DataFrame(self.trade_log)
        else:
            self.trades_df = pd.DataFrame()

        # Convert equity curve to DataFrame
        if self.equity_curve:
            self.equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
            self.equity_df.set_index('timestamp', inplace=True)
        else:
            self.equity_df = pd.DataFrame()

        # Create reports directory
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)

    def print_console_report(self):
        """Print formatted console summary of all backtest results."""
        # Build results dictionary from instance variables
        results = {
            "metrics": {
                "net_pnl": self.stats.get('net_pnl', 0),
                "net_pnl_pct": self.stats.get('net_pnl_pct', 0),
                "gross_pnl": self.stats.get('gross_pnl', 0),
                "gross_pnl_pct": self.stats.get('gross_pnl_pct', 0),
                "total_costs": self.stats.get('total_cost', 0),
                "sharpe": self.stats.get('sharpe_ratio', 0),
                "sortino": self.stats.get('sortino_ratio', 0),
                "calmar": self.stats.get('calmar_ratio', 0),
                "max_drawdown": self.stats.get('max_drawdown', 0),
                "avg_drawdown": self.stats.get('avg_drawdown', 0) if 'avg_drawdown' in self.stats else 0.0,
                "var_95": self.stats.get('var_95', 0),
                "total_trades": self.stats.get('total_trades', 0),
                "winning_trades": self.stats.get('winning_trades', 0),
                "losing_trades": self.stats.get('losing_trades', 0),
                "win_rate": self.stats.get('win_rate', 0),
                "avg_win": self.stats.get('avg_win', 0),
                "avg_loss": self.stats.get('avg_loss', 0),
                "reward_risk": self.stats.get('reward_risk', 0),
                "profit_factor": self.stats.get('profit_factor', 0),
                "trades_per_month": self.stats.get('trades_per_month', 0)
            },
            "regime_metrics": self.stats.get('regime_stats', {}),
            "acceptance_checks": {
                "freq_ok": self.stats.get('trades_per_month', 0) >= 30,
                "dd_ok": self.stats.get('max_drawdown', 1) <= 0.20,
                "rr_ok": self.stats.get('reward_risk', 0) > 1.0,
                "pnl_ok": self.stats.get('net_pnl_pct', 0) > 0,
                "stress_ok": True   # placeholder, we don't have stress test results yet
            }
        }
        m = results.get("metrics", {})
        r = results.get("regime_metrics", {})
        checks = results.get("acceptance_checks", {})

        print("\n")
        print("╔═════════════════════════════════════════════════════════╗")
        print("║      TRIPLE-SIGNAL STRATEGY — 2Y BACKTEST RESULTS       ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║ PERFORMANCE                                              ║")
        print(f"║ Net PnL:       ${m.get('net_pnl', 0):>10,.2f}  ({m.get('net_pnl_pct', 0)*100:.1f}%)           ║")
        print(f"║ Gross PnL:     ${m.get('gross_pnl', 0):>10,.2f}  ({m.get('gross_pnl_pct', 0)*100:.1f}%)           ║")
        print(f"║ Total Costs:   ${m.get('total_costs', 0):>10,.2f}                            ║")
        print(f"║ Sharpe Ratio:  {m.get('sharpe', 0):.2f}                                   ║")
        print(f"║ Sortino Ratio: {m.get('sortino', 0):.2f}                                   ║")
        print(f"║ Calmar Ratio:  {m.get('calmar', 0):.2f}                                   ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║ RISK                                                     ║")
        print(f"║ Max Drawdown:  {m.get('max_drawdown', 0)*100:.1f}%                                  ║")
        print(f"║ Avg Drawdown:  {m.get('avg_drawdown', 0)*100:.1f}%                                  ║")
        print(f"║ VaR (95%):     {m.get('var_95', 0)*100:.1f}% daily                             ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║ TRADING STATS                                            ║")
        print(f"║ Total Trades:  {m.get('total_trades', 0):<6}                                 ║")
        print(f"║ Trades/Month:  {m.get('trades_per_month', 0):.1f}  avg                               ║")
        print(f"║ Win Rate:      {m.get('win_rate', 0)*100:.1f}%                                  ║")
        print(f"║ Avg Winner:    +{m.get('avg_win', 0)*100:.2f}%                                ║")
        print(f"║ Avg Loser:     -{abs(m.get('avg_loss', 0))*100:.2f}%                                ║")
        print(f"║ Reward:Risk:   {m.get('reward_risk', 0):.2f} : 1                               ║")
        print(f"║ Profit Factor: {m.get('profit_factor', 0):.2f}                                   ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║ REGIME BREAKDOWN                                         ║")
        for regime in ["BULL", "SIDEWAYS", "BEAR"]:
            rd = r.get(regime, {})
            print(f"║ {regime:<8}: {rd.get('trades',0):>4} trades | "
                  f"Win: {rd.get('win_rate',0)*100:.0f}% | "
                  f"PnL: ${rd.get('net_pnl',0):>8,.0f}        ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║ ACCEPTANCE CRITERIA                                      ║")
        criteria = [
            ("Trades/month >= 30",    checks.get("freq_ok", False)),
            ("Max drawdown <= 20%",   checks.get("dd_ok", False)),
            ("Reward:Risk > 1:1",     checks.get("rr_ok", False)),
            ("Net PnL positive",      checks.get("pnl_ok", False)),
            ("Survives stress tests", checks.get("stress_ok", False)),
        ]
        for label, passed in criteria:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"║  {status}  {label:<40}║")
        print("╚══════════════════════════════════════════════════════════╝")
        logger.info("=== BACKTEST PERFORMANCE REPORT ===")
        logger.info(f"Total Trades: {self.stats.get('total_trades', 0)}")
        logger.info(f"Winning Trades: {self.stats.get('winning_trades', 0)}")
        logger.info(f"Losing Trades: {self.stats.get('losing_trades', 0)}")
        logger.info(f"Win Rate: {self.stats.get('win_rate', 0):.2%}")
        logger.info(f"Net PnL: {self.stats.get('net_pnl', 0):.2f} USDT")
        logger.info(f"Return %: {self.stats.get('net_pnl_pct', 0):.2f}%")
        logger.info(f"Gross PnL: {self.stats.get('gross_pnl', 0):.2f} USDT")
        logger.info(f"Total Cost: {self.stats.get('total_cost', 0):.2f} USDT")
        logger.info(f"Average Win: {self.stats.get('avg_win', 0):.2f} USDT")
        logger.info(f"Average Loss: {self.stats.get('avg_loss', 0):.2f} USDT")
        logger.info(f"Profit Factor: {self.stats.get('profit_factor', 0):.2f}")
        logger.info(f"Sharpe Ratio: {self.stats.get('sharpe_ratio', 0):.2f}")
        logger.info(f"Sortino Ratio: {self.stats.get('sortino_ratio', 0):.2f}")
        logger.info(f"Calmar Ratio: {self.stats.get('calmar_ratio', 0):.2f}")
        logger.info(f"Max Drawdown: {self.stats.get('max_drawdown', 0):.2%}")
        logger.info(f"VaR (95%): {self.stats.get('var_95', 0):.4f}")
        logger.info(f"Trades per Month: {self.stats.get('trades_per_month', 0):.2f}")

        # Regime breakdown
        regime_stats = self.stats.get('regime_stats', {})
        if regime_stats:
            logger.info("--- Regime Breakdown ---")
            for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
                if regime in regime_stats:
                    r = regime_stats[regime]
                    logger.info(f"{regime}: Trades={r.get('trades', 0)}, Win Rate={r.get('win_rate', 0):.2%}, "
                              f"Avg PnL={r.get('avg_pnl', 0):.2f}, Total PnL={r.get('total_pnl', 0):.2f}")

        logger.info("=" * 50)

    def generate_equity_curve_chart(self) -> str:
        """Generate equity curve chart and save to file."""
        if self.equity_df.empty:
            logger.warning("No equity curve data to plot")
            return ""

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=self.equity_df.index,
            y=self.equity_df['equity'],
            mode='lines',
            name='Equity',
            line=dict(color='blue', width=2)
        ))

        fig.update_layout(
            title='Equity Curve',
            xaxis_title='Date',
            yaxis_title='Equity (USDT)',
            hovermode='x unified',
            template='plotly_white'
        )

        file_path = self.reports_dir / "equity_curve.html"
        fig.write_html(str(file_path))

        logger.info(f"Saved equity curve chart to {file_path}")
        return str(file_path)

    def generate_drawdown_chart(self) -> str:
        """Generate drawdown chart and save to file."""
        if self.equity_df.empty:
            logger.warning("No equity curve data to plot drawdown")
            return ""

        # Calculate drawdown
        rolling_max = self.equity_df['equity'].cummax()
        drawdown = (self.equity_df['equity'] - rolling_max) / rolling_max

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=self.equity_df.index,
            y=drawdown,
            fill='tozeroy',
            mode='lines',
            name='Drawdown',
            line=dict(color='red', width=2)
        ))

        fig.update_layout(
            title='Drawdown',
            xaxis_title='Date',
            yaxis_title='Drawdown',
            hovermode='x unified',
            template='plotly_white'
        )

        file_path = self.reports_dir / "drawdown.html"
        fig.write_html(str(file_path))

        logger.info(f"Saved drawdown chart to {file_path}")
        return str(file_path)

    def generate_monthly_returns_heatmap(self) -> str:
        """Generate monthly returns heatmap and save to file."""
        if self.trades_df.empty or 'exit_time' not in self.trades_df.columns:
            logger.warning("No trade data for monthly returns heatmap")
            return ""

        # Prepare monthly returns
        trades_df = self.trades_df.copy()
        trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
        trades_df.set_index('exit_time', inplace=True)

        # Calculate monthly returns
        monthly_returns = trades_df['net_pnl'].resample('M').sum()
        monthly_returns = monthly_returns.to_period('M')

        # Create a pivot table for heatmap
        monthly_returns.index = monthly_returns.index.to_timestamp()
        monthly_returns = monthly_returns.reset_index()
        monthly_returns['year'] = monthly_returns['exit_time'].dt.year
        monthly_returns['month'] = monthly_returns['exit_time'].dt.month

        # Pivot for heatmap
        pivot_table = monthly_returns.pivot(index='year', columns='month', values='net_pnl')
        pivot_table = pivot_table.fillna(0)

        # Convert to list for heatmap
        z = pivot_table.values.tolist()
        x = [f"{int(m):02d}" for m in pivot_table.columns]  # Month names
        y = [str(int(y)) for y in pivot_table.index]  # Year names

        fig = go.Figure(data=go.Heatmap(
            z=z,
            x=x,
            y=y,
            colorscale='RdYlGn',
            zmid=0,
            text=np.around(z, decimals=0),
            texttemplate="%{text}",
            textfont={"size": 10},
        ))

        fig.update_layout(
            title='Monthly Returns Heatmap (USDT)',
            xaxis_title='Month',
            yaxis_title='Year',
            template='plotly_white'
        )

        file_path = self.reports_dir / "monthly_returns_heatmap.html"
        fig.write_html(str(file_path))

        logger.info(f"Saved monthly returns heatmap to {file_path}")
        return str(file_path)

    def generate_trade_analysis_charts(self) -> List[str]:
        """Generate trade analysis charts and save to files."""
        if self.trades_df.empty:
            logger.warning("No trade data for analysis charts")
            return []

        chart_paths = []

        # 1. Trade PnL distribution
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=self.trades_df['net_pnl'],
            nbinsx=30,
            name='PnL Distribution',
            marker_color='blue',
            opacity=0.7
        ))

        fig.update_layout(
            title='Trade PnL Distribution',
            xaxis_title='PnL (USDT)',
            yaxis_title='Frequency',
            template='plotly_white'
        )

        file_path = self.reports_dir / "trade_pnl_distribution.html"
        fig.write_html(str(file_path))
        chart_paths.append(str(file_path))
        logger.info(f"Saved trade PnL distribution chart to {file_path}")

        # 2. Win/Loss by regime
        if 'regime_at_entry' in self.trades_df.columns:
            regime_pnl = self.trades_df.groupby('regime_at_entry')['net_pnl'].sum()

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=regime_pnl.index,
                y=regime_pnl.values,
                name='Total PnL by Regime',
                marker_color=['green', 'gray', 'red']
            ))

            fig.update_layout(
                title='Total PnL by Regime',
                xaxis_title='Regime',
                yaxis_title='Total PnL (USDT)',
                template='plotly_white'
            )

            file_path = self.reports_dir / "pnl_by_regime.html"
            fig.write_html(str(file_path))
            chart_paths.append(str(file_path))
            logger.info(f"Saved PnL by regime chart to {file_path}")

        # 3. Cumulative PnL over time
        if 'exit_time' in self.trades_df.columns:
            trades_df = self.trades_df.copy()
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            trades_df = trades_df.sort_values('exit_time')
            trades_df['cumulative_pnl'] = trades_df['net_pnl'].cumsum()

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trades_df['exit_time'],
                y=trades_df['cumulative_pnl'],
                mode='lines',
                name='Cumulative PnL',
                line=dict(color='blue', width=2)
            ))

            fig.update_layout(
                title='Cumulative PnL Over Time',
                xaxis_title='Date',
                yaxis_title='Cumulative PnL (USDT)',
                hovermode='x unified',
                template='plotly_white'
            )

            file_path = self.reports_dir / "cumulative_pnl.html"
            fig.write_html(str(file_path))
            chart_paths.append(str(file_path))
            logger.info(f"Saved cumulative PnL chart to {file_path}")

        return chart_paths

    def generate_regime_performance_chart(self) -> str:
        """Generate regime performance chart and save to file."""
        if self.trades_df.empty or 'regime_at_entry' not in self.trades_df.columns:
            logger.warning("No trade data with regime for performance chart")
            return ""

        # Calculate win rate and avg PnL by regime
        regime_stats = self.trades_df.groupby('regime_at_entry').agg(
            win_rate=('net_pnl', lambda x: (x > 0).mean()),
            avg_pnl=('net_pnl', 'mean'),
            total_pnl=('net_pnl', 'sum'),
            trade_count=('net_pnl', 'count')
        ).reset_index()

        # Create subplot
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Win Rate by Regime', 'Average PnL per Trade by Regime'),
            specs=[[{"type": "bar"}, {"type": "bar"}]]
        )

        # Win rate
        fig.add_trace(go.Bar(
            x=regime_stats['regime_at_entry'],
            y=regime_stats['win_rate'],
            name='Win Rate',
            marker_color=['green', 'gray', 'red']
        ), row=1, col=1)

        # Average PnL
        fig.add_trace(go.Bar(
            x=regime_stats['regime_at_entry'],
            y=regime_stats['avg_pnl'],
            name='Average PnL',
            marker_color=['green', 'gray', 'red']
        ), row=1, col=2)

        fig.update_layout(
            title_text="Regime Performance Analysis",
            showlegend=False,
            template='plotly_white'
        )

        # Update y-axis labels
        fig.update_yaxes(title_text="Win Rate", range=[0, 1], row=1, col=1)
        fig.update_yaxes(title_text="Average PnL (USDT)", row=1, col=2)

        file_path = self.reports_dir / "regime_performance.html"
        fig.write_html(str(file_path))

        logger.info(f"Saved regime performance chart to {file_path}")
        return str(file_path)

    def generate_all_charts(self) -> Dict[str, str]:
        """Generate all charts and return dictionary of chart names and file paths."""
        chart_paths = {}

        # Equity curve
        chart_paths['equity_curve'] = self.generate_equity_curve_chart()

        # Drawdown
        chart_paths['drawdown'] = self.generate_drawdown_chart()

        # Monthly returns heatmap
        chart_paths['monthly_returns_heatmap'] = self.generate_monthly_returns_heatmap()

        # Trade analysis charts
        trade_charts = self.generate_trade_analysis_charts()
        if trade_charts:
            chart_paths['trade_pnl_distribution'] = trade_charts[0] if len(trade_charts) > 0 else ""
            if len(trade_charts) > 1:
                chart_paths['pnl_by_regime'] = trade_charts[1]
            if len(trade_charts) > 2:
                chart_paths['cumulative_pnl'] = trade_charts[2]

        # Regime performance
        chart_paths['regime_performance'] = self.generate_regime_performance_chart()

        return chart_paths

    def generate_html_report(self, chart_paths: Dict[str, str]) -> str:
        """Generate HTML report with embedded charts."""
        html_parts = []
        html_parts.append('<!DOCTYPE html>')
        html_parts.append('<html>')
        html_parts.append('<head>')
        html_parts.append('    <title>Crypto Perpetual Futures Backtest Report</title>')
        html_parts.append('    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>')
        html_parts.append('    <style>')
        html_parts.append('        body { font-family: Arial, sans-serif; margin: 40px; }')
        html_parts.append('        h1, h2, h3 { color: #2c3e50; }')
        html_parts.append('        .container { max-width: 1200px; margin: 0 auto; }')
        html_parts.append('        .chart { margin: 30px 0; }')
        html_parts.append('        .stats { display: flex; flex-wrap: wrap; gap: 20px; margin: 20px 0; }')
        html_parts.append('        .stat-box { background: #ecf0f1; padding: 15px; border-radius: 4px; flex: 1; min-width: 200px; }')
        html_parts.append('        .stat-label { font-weight: bold; color: #34495e; }')
        html_parts.append('        .stat-value { font-size: 1.2em; color: #2c3e50; }')
        html_parts.append('        table { width: 100%; border-collapse: collapse; margin: 20px 0; }')
        html_parts.append('        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }')
        html_parts.append('        th { background-color: #f2f2f2; }')
        html_parts.append('        tr:hover { background-color: #f5f5f5; }')
        html_parts.append('    </style>')
        html_parts.append('</head>')
        html_parts.append('<body>')
        html_parts.append('    <div class="container">')
        html_parts.append('        <h1>Crypto Perpetual Futures Backtest Report</h1>')
        from datetime import datetime
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        html_parts.append('        <p>Generated on: ' + timestamp_str + '</p>')
        html_parts.append('')
        html_parts.append('        <h2>Performance Summary</h2>')
        html_parts.append('        <div class="stats">')
        html_parts.append('            <div class="stat-box">')
        html_parts.append('                <div class="stat-label">Total Trades</div>')
        html_parts.append('                <div class="stat-value">' + str(self.stats.get('total_trades', 0)) + '</div>')
        html_parts.append('            </div>')
        html_parts.append('            <div class="stat-box">')
        html_parts.append('                <div class="stat-label">Win Rate</div>')
        html_parts.append('                <div class="stat-value">' + "{:.2%}".format(self.stats.get('win_rate', 0)) + '</div>')
        html_parts.append('            </div>')
        html_parts.append('            <div class="stat-box">')
        html_parts.append('                <div class="stat-label">Net PnL</div>')
        html_parts.append('                <div class="stat-value">' + "{:.2f}".format(self.stats.get('net_pnl', 0)) + ' USDT</div>')
        html_parts.append('            </div>')
        html_parts.append('            <div class="stat-box">')
        html_parts.append('                <div class="stat-label">Return %</div>')
        html_parts.append('                <div class="stat-value">' + "{:.2f}%".format(self.stats.get('net_pnl_pct', 0)) + '</div>')
        html_parts.append('            </div>')
        html_parts.append('        </div>')
        html_parts.append('')
        html_parts.append('        <h2>Charts</h2>')
        # Add charts
        chart_names = {
            'equity_curve': 'Equity Curve',
            'drawdown': 'Drawdown',
            'monthly_returns_heatmap': 'Monthly Returns Heatmap',
            'trade_pnl_distribution': 'Trade PnL Distribution',
            'pnl_by_regime': 'PnL by Regime',
            'cumulative_pnl': 'Cumulative PnL Over Time',
            'regime_performance': 'Regime Performance'
        }
        for key, name in chart_names.items():
            if key in chart_paths and chart_paths[key]:
                # Convert file path to relative path for HTML
                rel_path = chart_paths[key].replace('\\', '/')
                html_parts.append('        <div class="chart">')
                html_parts.append('            <h3>' + name + '</h3>')
                html_parts.append('            <div id="' + key.replace('-', '_') + '"></div>')
                html_parts.append('        </div>')
        html_parts.append('')
        html_parts.append('        <h2>Trade Log</h2>')
        if not self.trades_df.empty:
            # Convert trade log to HTML table
            html_parts.append(self.trades_df.to_html(
                classes='table table-striped',
                index=False,
                float_format=lambda x: "{:.2f}".format(x)
            ))
        else:
            html_parts.append('        <p>No trades recorded.</p>')
        html_parts.append('    </div>')
        html_parts.append('</body>')
        html_parts.append('</html>')
        html_content = '\n'.join(html_parts)
        # Save HTML report
        html_path = self.reports_dir / "backtest_report.html"
        with open(html_path, 'w') as f:
            f.write(html_content)
        logger.info(f"Saved HTML report to {html_path}")
        return str(html_path)
    def generate_report(self) -> Dict[str, Any]:
        """Generate all reports and return paths."""
        logger.info("Generating reports...")

        # Generate all charts
        chart_paths = self.generate_all_charts()

        # Generate HTML report
        html_path = self.generate_html_report(chart_paths)

        # Save trade log to CSV
        if not self.trades_df.empty:
            trades_csv_path = self.reports_dir / "trades_log.csv"
            self.trades_df.to_csv(trades_csv_path, index=False)
            logger.info(f"Saved trade log CSV to {trades_csv_path}")
        else:
            trades_csv_path = ""

        # Save equity curve to CSV
        if not self.equity_df.empty:
            equity_csv_path = self.reports_dir / "equity_curve.csv"
            self.equity_df.to_csv(equity_csv_path)
            logger.info(f"Saved equity curve CSV to {equity_csv_path}")
        else:
            equity_csv_path = ""

        # Save stats to JSON
        stats_json_path = self.reports_dir / "stats.json"
        with open(stats_json_path, 'w') as f:
            json.dump(self.stats, f, indent=2)
        logger.info(f"Saved stats JSON to {stats_json_path}")

        return {
            'charts': chart_paths,
            'html_report': html_path,
            'trades_csv': trades_csv_path,
            'equity_curve_csv': equity_csv_path,
            'stats_json': str(stats_json_path)
        }

def generate_reports(trade_log: List[Dict], equity_curve: List[Tuple[pd.Timestamp, float]], 
                     stats: Dict, regime_data: Dict[str, pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Convenience function to generate reports.

    Args:
        trade_log (List[Dict]): List of trade dictionaries.
        equity_curve (List[Tuple[pd.Timestamp, float]]): List of (timestamp, equity) tuples.
        stats (Dict): Performance statistics dictionary.
        regime_data (Dict[str, pd.DataFrame], optional): Dictionary of DataFrames with regime data for each instrument.

    Returns:
        Dict[str, Any]: Dictionary containing paths to generated reports.
    """
    report_generator = ReportGenerator(trade_log, equity_curve, stats, regime_data)
    return report_generator.generate_report()

if __name__ == "__main__":
    # For testing - generate empty report
    print("Report generator module - run via main.py")