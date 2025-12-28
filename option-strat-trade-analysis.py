#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "openpyxl"
# ]
# ///
"""
Trade analysis script that reads an Excel spreadsheet containing option trades and generates an HTML report.

Usage:
    option-strat-trade-analysis.py -h

Examples:
    option-strat-trade-analysis.py -f /path/to/experiment.xlsx -v
    option-strat-trade-analysis.py -f /path/to/experiment.xlsx -vv --open

Flags:
    -f, --file    Path to the Excel file to analyze (required)
    --open        Open generated HTML report with system `open`
    -v            Increase verbosity (use twice for DEBUG)
"""

import logging
import os
import subprocess
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from html import escape

import pandas as pd


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="file",
        help="Path to the Excel file to analyze",
        required=True,
    )
    parser.add_argument(
        "--open",
        dest="open",
        action="store_true",
        help="Open generated HTML report with system `open`",
        required=False,
    )
    return parser.parse_args()


def main(args):
    logging.debug(f"This is a debug log message: {args.verbose}")
    logging.info(f"This is an info log message: {args.verbose}")

    file_path = os.path.expanduser(args.file)
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return

    analyze_excel(file_path, open_report=getattr(args, "open", False))


def analyze_excel(file_path, open_report=False):
    """Read the given Excel file and write an HTML report to a temp file."""
    logging.info(f"Reading file: {file_path}")
    try:
        df = pd.read_excel(file_path)
        logging.info(f"Shape: {df.shape}")

        trades = []
        current_trade = None

        for _, row in df.iterrows():
            name = str(row["Name"])
            if name == "Symbol":
                continue

            # A trade row usually has a 'Group' and 'Link'
            if pd.notna(row["Group"]):
                if current_trade:
                    trades.append(current_trade)

                current_trade = {"trade_info": row.to_dict(), "legs": []}
            elif current_trade is not None:
                # This is a leg
                leg_info = {
                    "symbol": row["Name"],
                    "quantity": row["Total Return %"],
                    "entry_price": row["Total Return $"],
                    "current_price": row["Created At"],
                    "close_price": row["Expiration"],
                }
                current_trade["legs"].append(leg_info)

        if current_trade:
            trades.append(current_trade)

        logging.info(f"Found {len(trades)} trades.")

        # Detailed Analysis
        analysis_data = []
        from datetime import datetime

        today = datetime.now()

        for t in trades:
            info = t["trade_info"]
            try:
                pl = float(info.get("Total Return $", 0))
            except:
                pl = 0

            try:
                pl_pct = float(info.get("Total Return %", 0)) * 100
            except:
                pl_pct = 0

            dte = None
            if pd.notna(info.get("Expiration")):
                try:
                    exp_date = pd.to_datetime(info.get("Expiration"))
                    dte = (exp_date - today).days
                except:
                    pass

            analysis_data.append(
                {
                    "Name": info.get("Name"),
                    "Group": info.get("Group", "Unknown"),
                    "P/L $": pl,
                    "P/L %": pl_pct,
                    "Delta": float(info.get("Delta", 0))
                    if pd.notna(info.get("Delta"))
                    else 0,
                    "Theta": float(info.get("Theta", 0))
                    if pd.notna(info.get("Theta"))
                    else 0,
                    "IV": float(info.get("IV", 0)) if pd.notna(info.get("IV")) else 0,
                    "DTE": dte,
                    "Status": info.get("Link", "Unknown"),
                    "Leg Count": len(t["legs"]),
                }
            )

        analysis_df = pd.DataFrame(analysis_data)

        # Build HTML report
        title = "Trade Analysis Report"
        html_parts = [f"<h1>{escape(title)}</h1>"]

        # Helper to convert values to safe display strings (blank for NaN)
        def safe_str_val(v):
            try:
                if pd.isna(v):
                    return ""
            except Exception:
                pass
            if v is None:
                return ""
            s = str(v)
            if s.lower() == "nan":
                return ""
            return s

        # Helper to format prices to 2 decimal places (blank for NaN)
        def format_price_display(v):
            try:
                if pd.isna(v):
                    return ""
            except Exception:
                pass
            if v is None or str(v).strip() == "":
                return ""
            try:
                val = float(str(v).replace(",", ""))
                return f"{val:,.2f}"
            except Exception:
                return str(v)

        # Helper to format numeric metrics like Delta/Theta to 2 decimals (blank for NaN)
        def format_numeric(v, prec=2):
            try:
                if pd.isna(v):
                    return ""
            except Exception:
                pass
            if v is None or str(v).strip() == "":
                return ""
            try:
                val = float(v)
                return f"{val:,.{prec}f}"
            except Exception:
                return str(v)

        # Helper to render any DataFrame and highlight rows based on a P/L column
        def render_table_with_pl_styles(
            df,
            pl_column="P/L $",
            include_checkbox=False,
            id_prefix=None,
            hide_closed=False,
        ):
            headers = df.columns.tolist()
            parts = ['<table class="table">']

            # If checkboxes are included, add an extra header for selection
            hdr_cells = ""
            if include_checkbox:
                if id_prefix:
                    hdr_cells += f'<th><input type="checkbox" id="{escape(id_prefix)}-select-all" onchange="toggleSelectAll(\'{escape(id_prefix)}\', this.checked)"></th>'
                else:
                    hdr_cells += "<th></th>"
            hdr_cells += "".join(f"<th>{escape(str(h))}</th>" for h in headers)
            parts.append("<thead><tr>" + hdr_cells + "</tr></thead>")

            parts.append("<tbody>")
            for row_idx, r in df.iterrows():
                raw_pl = r.get(pl_column)
                pl_val = None
                try:
                    if isinstance(raw_pl, str):
                        s = raw_pl.replace("%", "").replace(",", "").strip()
                        pl_val = float(s) if s != "" else None
                    else:
                        pl_val = (
                            float(raw_pl)
                            if raw_pl is not None and not pd.isna(raw_pl)
                            else None
                        )
                except Exception:
                    pl_val = None

                style = ""
                if pl_val is not None:
                    if pl_val > 0:
                        style = "background:#eaffea"
                    elif pl_val < 0:
                        style = "background:#ffecec"

                # Make open positions bold (Status column equals 'Open')
                try:
                    status_val = safe_str_val(r.get("Status", ""))
                    if status_val.lower() == "open":
                        if style:
                            style += ";"
                        style += "font-weight:bold"
                except Exception:
                    pass

                # Prepare row cells
                row_cells = ""
                if include_checkbox and id_prefix:
                    # checkbox data-pl uses numeric pl_val when available
                    pl_attr = f"{pl_val}" if pl_val is not None else ""
                    cb_id = f"{id_prefix}-cb-{row_idx}"
                    row_cells += f"<td><input type='checkbox' id='{cb_id}' class='pos-checkbox' data-trade='{escape(id_prefix)}' data-pl='{pl_attr}' onchange=\"updateTradeSelectedPL('{escape(id_prefix)}')\"></td>"

                for c in headers:
                    val = r.get(c, "")
                    # Format specific numeric columns
                    if c in ("Delta", "Theta", "P/L $"):
                        cell_text = format_numeric(val, 2)
                    elif c == "P/L %":
                        # try numeric formatting then append %
                        try:
                            num = float(str(val).replace("%", "").replace(",", ""))
                            cell_text = f"{num:,.2f}%"
                        except Exception:
                            cell_text = safe_str_val(val)
                    else:
                        cell_text = safe_str_val(val)

                    row_cells += f"<td>{escape(cell_text)}</td>"

                # status for toggling (lowercase)
                status_raw = safe_str_val(r.get("Status", "")).strip()
                status_attr = (
                    f' data-status="{escape(status_raw.lower())}"' if status_raw else ""
                )

                # If hiding closed rows by default, add display:none to closed rows
                if hide_closed and status_raw.lower() == "closed":
                    if style:
                        style += ";"
                    style += "display:none"

                # attach data-pl attribute to row for convenience
                data_pl_attr = f' data-pl="{pl_val}"' if pl_val is not None else ""

                parts.append(
                    f'<tr{status_attr}{data_pl_attr} style="{style}">{row_cells}</tr>'
                )

            parts.append("</tbody></table>")
            return "\n".join(parts)

        if not analysis_df.empty:
            total_trades = len(analysis_df)
            total_pl = analysis_df["P/L $"].sum()
            avg_pl_pct = analysis_df["P/L %"].mean()
            total_delta = analysis_df["Delta"].sum()
            total_theta = analysis_df["Theta"].sum()

            html_parts.append("<h2>Portfolio Summary</h2>")
            html_parts.append("<ul>")
            html_parts.append(f"<li>Total Trades: {total_trades}</li>")
            # Color Total P/L as a pill
            total_pill_base = "padding:6px; border-radius:4px; display:inline-block"
            try:
                if total_pl > 0:
                    total_pill_style = f"background:#eaffea; {total_pill_base}"
                elif total_pl < 0:
                    total_pill_style = f"background:#ffecec; {total_pill_base}"
                else:
                    total_pill_style = total_pill_base
            except Exception:
                total_pill_style = total_pill_base
            html_parts.append(
                f"<li><span style='{total_pill_style}'><strong>Total P/L $: {total_pl:,.2f}</strong></span></li>"
            )
            html_parts.append(f"<li>Average P/L %: {avg_pl_pct:.2f}%</li>")
            html_parts.append(f"<li>Total Delta: {total_delta:.2f}</li>")
            html_parts.append(f"<li>Total Theta: {total_theta:.2f}</li>")
            html_parts.append("</ul>")

            # Detailed trades and their positions (copy-friendly)
            html_parts.append("<h2>Trades and Positions</h2>")
            trade_index = 0
            html_parts.append(
                "<style>.copy-btn{margin-bottom:8px;padding:6px 10px;border-radius:4px;background:#007bff;color:#fff;border:none;cursor:pointer} .copy-btn:active{transform:translateY(1px)} pre.copy-block{background:#f8f8f8;padding:8px;border:1px solid #eee;white-space:pre-wrap}</style>"
            )
            for t in trades:
                info = t.get("trade_info", {})
                name = escape(str(info.get("Name", "")))
                group = escape(str(info.get("Group", "")))

                try:
                    pl = float(info.get("Total Return $", 0))
                except:
                    pl = 0.0
                try:
                    pl_pct = float(info.get("Total Return %", 0)) * 100
                except:
                    pl_pct = 0.0
                try:
                    delta = (
                        float(info.get("Delta", 0))
                        if pd.notna(info.get("Delta"))
                        else 0
                    )
                except:
                    delta = 0
                try:
                    theta = (
                        float(info.get("Theta", 0))
                        if pd.notna(info.get("Theta"))
                        else 0
                    )
                except:
                    theta = 0
                status = escape(str(info.get("Link", "")))

                # Compute DTE for this trade if possible
                dte_val = ""
                if pd.notna(info.get("Expiration")):
                    try:
                        exp_date = pd.to_datetime(info.get("Expiration"))
                        dte_val = (exp_date - today).days
                    except:
                        dte_val = ""

                tid = f"trade-{trade_index}"

                html_parts.append(f'<div class="trade" id="{tid}">')
                html_parts.append(f"<h3>{name} <small>({group})</small></h3>")

                # Build copy-friendly text block
                lines = []
                # Format delta/theta for header and display
                delta_disp = format_numeric(delta, 2)
                theta_disp = format_numeric(theta, 2)
                header = f"Name: {name}, Group: {group}, P/L $: {pl:,.2f}, P/L %: {pl_pct:.2f}%, Delta: {delta_disp}, Theta: {theta_disp}, DTE: {dte_val}, Status: {status}"
                lines.append(header)
                lines.append("Symbol,Quantity,Entry Price,Current Price,Close Price")
                for leg in t.get("legs", []):

                    def maybe_str(x):
                        try:
                            if pd.isna(x):
                                return ""
                        except Exception:
                            pass
                        return str(x) if x is not None else ""

                    def fmt_price_for_copy(x):
                        try:
                            if pd.isna(x):
                                return ""
                        except Exception:
                            pass
                        try:
                            val = float(str(x).replace(",", ""))
                            return f"{val:,.2f}"
                        except Exception:
                            return maybe_str(x)

                    s = [
                        maybe_str(leg.get("symbol", "")),
                        maybe_str(leg.get("quantity", "")),
                        fmt_price_for_copy(leg.get("entry_price", "")),
                        fmt_price_for_copy(leg.get("current_price", "")),
                        fmt_price_for_copy(leg.get("close_price", "")),
                    ]
                    lines.append(",".join(s))
                copy_text = "\n".join(lines)

                # Determine if this trade has closed legs (current empty but close present)
                has_closed = False
                for leg in t.get("legs", []):
                    cur = leg.get("current_price")
                    closep = leg.get("close_price")
                    try:
                        cur_empty = (
                            (cur is None)
                            or (isinstance(cur, float) and pd.isna(cur))
                            or (str(cur).strip() == "")
                        )
                    except Exception:
                        cur_empty = False
                    try:
                        close_present = (
                            (closep is not None)
                            and not (isinstance(closep, float) and pd.isna(closep))
                            and (str(closep).strip() != "")
                        )
                    except Exception:
                        close_present = False
                    if cur_empty and close_present:
                        has_closed = True
                        break

                # Hidden pre contains copyable text; visible copy and toggle buttons
                html_parts.append(
                    f"<button class='copy-btn' onclick=\"copyTrade('{tid}')\">Copy trade</button>"
                )
                if has_closed:
                    html_parts.append(
                        f'<button class=\'copy-btn\' onclick="toggleClosed(\'{tid}\')" id="{tid}-toggle" data-hidden="true">Show closed</button>'
                    )
                else:
                    html_parts.append(
                        f"<button class='copy-btn' onclick=\"toggleClosed('{tid}')\" id=\"{tid}-toggle\">Hide closed</button>"
                    )
                html_parts.append(
                    f'<pre id="{tid}-copy" class="copy-block" style="display:none">{escape(copy_text)}</pre>'
                )

                # Inline trade summary row
                pill_base = "padding:4px; border-radius:4px; display:inline-block"
                try:
                    if pl > 0:
                        pill_style = f"background:#eaffea; {pill_base}"
                    elif pl < 0:
                        pill_style = f"background:#ffecec; {pill_base}"
                    else:
                        pill_style = pill_base
                except Exception:
                    pill_style = pill_base

                html_parts.append(
                    f"<div class='trade-summary' style='display:flex;gap:12px;align-items:center;flex-wrap:wrap'>"
                )
                html_parts.append(
                    f"<div style='{pill_style}'><strong>P/L $: {pl:,.2f}</strong></div>"
                )
                html_parts.append(f"<div>P/L %: {pl_pct:.2f}%</div>")
                html_parts.append(f"<div>Delta: {delta_disp}</div>")
                html_parts.append(f"<div>Theta: {theta_disp}</div>")
                html_parts.append(f"<div>DTE: {dte_val}</div>")
                html_parts.append(f"<div>Status: {status}</div>")
                html_parts.append(f"<div>Leg Count: {len(t.get('legs', []))}</div>")
                html_parts.append("</div>")
                # Add a couple of blank lines for visual spacing
                html_parts.append("<br/>")
                html_parts.append("<br/>")

                if t.get("legs"):
                    legs_df = pd.DataFrame(t.get("legs"))

                    # Normalize column names for display
                    legs_df = legs_df.rename(
                        columns={
                            "symbol": "Symbol",
                            "quantity": "Quantity",
                            "entry_price": "Entry Price",
                            "current_price": "Current Price",
                            "close_price": "Close Price",
                        }
                    )

                    # Compute per-position P/L
                    multiplier = 100  # contract multiplier (default)

                    def to_float(val):
                        try:
                            if pd.isna(val):
                                return None
                        except Exception:
                            pass
                        try:
                            s = str(val).strip()
                            if s == "":
                                return None
                            return float(s.replace(",", ""))
                        except Exception:
                            return None

                    pls = []
                    pl_pcts = []
                    statuses = []
                    price_used = []

                    for _, leg in legs_df.iterrows():
                        entry = to_float(leg.get("Entry Price"))
                        current = to_float(leg.get("Current Price"))
                        closep = to_float(leg.get("Close Price"))
                        qty = to_float(leg.get("Quantity"))

                        # Choose price for P/L calculation: prefer current, else close
                        p_used = current if current is not None else closep
                        price_used.append(p_used if p_used is not None else "")

                        if p_used is None or entry is None or qty is None:
                            pls.append(None)
                            pl_pcts.append(None)
                            statuses.append("Unknown")
                        else:
                            pl_val = (p_used - entry) * qty * multiplier
                            pls.append(pl_val)
                            try:
                                pl_pct = (
                                    (p_used - entry) / entry * 100
                                    if entry != 0
                                    else None
                                )
                            except Exception:
                                pl_pct = None
                            pl_pcts.append(pl_pct if pl_pct is not None else None)

                            # Determine status: closed if close price provided and current not present
                            if (closep is not None) and (current is None):
                                statuses.append("Closed")
                            else:
                                statuses.append("Open")

                    legs_df["Price Used"] = price_used
                    legs_df["P/L $"] = pls
                    legs_df["P/L %"] = pl_pcts
                    legs_df["Status"] = statuses

                    # Format numeric columns for display
                    def fmt(v, prec=2):
                        if v is None or (
                            isinstance(v, float) and (pd.isna(v) or v == None)
                        ):
                            return ""
                        try:
                            return f"{v:,.{prec}f}"
                        except Exception:
                            return str(v)

                    legs_display = legs_df.copy()
                    if "P/L $" in legs_display:
                        legs_display["P/L $"] = legs_display["P/L $"].apply(
                            lambda v: fmt(v, 2)
                        )
                    if "P/L %" in legs_display:
                        legs_display["P/L %"] = legs_display["P/L %"].apply(
                            lambda v: (fmt(v, 2) + "%") if v != None and v != "" else ""
                        )

                    # Format price columns to 2 decimals for display
                    if "Entry Price" in legs_display:
                        legs_display["Entry Price"] = legs_display["Entry Price"].apply(
                            lambda v: format_price_display(v)
                        )
                    if "Current Price" in legs_display:
                        legs_display["Current Price"] = legs_display[
                            "Current Price"
                        ].apply(lambda v: format_price_display(v))
                    if "Close Price" in legs_display:
                        legs_display["Close Price"] = legs_display["Close Price"].apply(
                            lambda v: format_price_display(v)
                        )
                    if "Price Used" in legs_display:
                        legs_display["Price Used"] = legs_display["Price Used"].apply(
                            lambda v: format_price_display(v)
                        )

                    # Use shared renderer for leg table (formats rows by P/L $); hide closed rows by default
                    html_parts.append(
                        render_table_with_pl_styles(
                            legs_display,
                            include_checkbox=True,
                            id_prefix=tid,
                            hide_closed=has_closed,
                        )
                    )

                    # Sum of leg P/Ls (if any) and display next to trade header
                    try:
                        total_legs_pl = (
                            sum([v for v in pls if v is not None])
                            if len([v for v in pls if v is not None]) > 0
                            else 0.0
                        )
                        color_style = ""
                        if total_legs_pl > 0:
                            color_style = "background:#eaffea"
                        elif total_legs_pl < 0:
                            color_style = "background:#ffecec"
                        html_parts.append(
                            f"<p style='{color_style} padding:6px; border-radius:4px; display:inline-block'><strong>Legs P/L $: {total_legs_pl:,.2f}</strong></p>"
                        )
                    except Exception:
                        pass

                    # Placeholder for selected positions P/L in this trade
                    html_parts.append(
                        f'<p id="{tid}-selected-pl" style="margin-left:12px; display:inline-block">Selected P/L $: <strong>$0.00</strong></p>'
                    )

                html_parts.append("</div>")
                trade_index += 1

            # Insert copy script
            html_parts.append("""<script>
function copyTrade(id){
  try{
    const pre = document.getElementById(id + "-copy");
    if(!pre) return;
    const text = pre.innerText || pre.textContent;
    navigator.clipboard.writeText(text).then(()=>{
      const b = document.querySelector('#' + id + ' .copy-btn');
      if(b){ b.textContent = "Copied"; setTimeout(()=> b.textContent = "Copy trade", 1200); }
    }).catch(e => { console.error("Copy failed", e); });
  }catch(e){ console.error(e); }
}

function toggleClosed(id){
  try{
    const container = document.getElementById(id);
    if(!container) return;
    const btn = document.getElementById(id + '-toggle');
    const rows = container.querySelectorAll('tr[data-status="closed"]');
    const hidden = btn && btn.getAttribute('data-hidden') === 'true';
    if(!hidden){
      rows.forEach(r => r.style.display = 'none');
      if(btn){ btn.textContent = 'Show closed'; btn.setAttribute('data-hidden', 'true'); }
    } else {
      rows.forEach(r => r.style.display = '');
      if(btn){ btn.textContent = 'Hide closed'; btn.setAttribute('data-hidden', 'false'); }
    }
  }catch(e){ console.error(e); }
}

function updateTradeSelectedPL(tradeId){
  try{
    const container = document.getElementById(tradeId);
    if(!container) return;
    const checkboxes = container.querySelectorAll('input.pos-checkbox[data-trade="'+tradeId+'"]');
    let total = 0;
    checkboxes.forEach(cb=>{
      if(cb.checked){
        const v = parseFloat(cb.getAttribute('data-pl'));
        if(!isNaN(v)) total += v;
      }
    });
    const el = document.getElementById(tradeId+'-selected-pl');
    if(el){
      const span = el.querySelector('strong');
      if(span){
        span.textContent = '$' + total.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
        if(total>0){ el.style.background='#eaffea'; } else if(total<0){ el.style.background='#ffecec'; } else { el.style.background=''; }
      }
    }
    // Update header select-all checkbox state for this trade
    updateSelectAllCheckbox(tradeId);
    // Update global selected total
    recomputeSelectedTotal();
  }catch(e){ console.error(e); }
}

function updateSelectAllCheckbox(tradeId){
  try{
    const header = document.getElementById(tradeId + '-select-all');
    if(!header) return;
    const cbs = document.querySelectorAll('input.pos-checkbox[data-trade="'+tradeId+'"]');
    const allChecked = Array.from(cbs).length > 0 && Array.from(cbs).every(cb=>cb.checked);
    header.checked = allChecked;
  }catch(e){ console.error(e); }
}

function toggleSelectAll(tradeId, checked){
  try{
    const cbs = document.querySelectorAll('input.pos-checkbox[data-trade="'+tradeId+'"]');
    cbs.forEach(cb=>{ cb.checked = checked; });
    updateTradeSelectedPL(tradeId);
  }catch(e){ console.error(e); }
}

function recomputeSelectedTotal(){
  try{
    const cbs = document.querySelectorAll('input.pos-checkbox');
    let total = 0;
    cbs.forEach(cb=>{ if(cb.checked){ const v=parseFloat(cb.getAttribute('data-pl')); if(!isNaN(v)) total += v; }});
    const el = document.getElementById('selected-total-pl');
    if(el){ el.querySelector('strong').textContent = '$' + total.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
      if(total>0){ el.style.background='#eaffea'; } else if(total<0){ el.style.background='#ffecec'; } else { el.style.background=''; }
    }
  }catch(e){ console.error(e); }
}
</script>""")

        else:
            html_parts.append("<p><em>No trade data found to analyze.</em></p>")

        html_body = "\n".join(html_parts)
        full_html = (
            '<!doctype html><html><head><meta charset="utf-8"><title>'
            + escape(title)
            + "</title>\n<style>\n"
            + "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial;margin:20px}\n"
            + "/* Make tables use full available width and improve wrapping */\n"
            + "table, table.table {width:100%; max-width:100%; border-collapse:collapse}\n"
            + "table.table th, table.table td {border:1px solid #ddd; padding:6px; text-align:left; vertical-align:top}\n"
            + "table.table th {background:#f2f2f2}\n"
            + "/* Allow long content to wrap instead of overflowing */\n"
            + "table.table td {word-break:break-word; white-space:normal}\n"
            + "</style></head><body>"
            + html_body
            + "</body></html>"
        )

        # Write to a temporary file
        tmp_dir = None
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".html",
            prefix="trade-analysis-",
            mode="w",
            encoding="utf-8",
            dir=tmp_dir,
        ) as tmp:
            tmp.write(full_html)
            out_path = tmp.name

        logging.info(f"Report written to: {out_path}")

        if open_report:
            try:
                subprocess.run(["open", out_path], check=False)
                logging.info("Opened report with 'open'")
            except Exception as ex:
                logging.error(f"Failed to open report: {ex}")

        return out_path

    except Exception as e:
        logging.error(f"Failed to read Excel file '{file_path}': {e}")
        import traceback

        logging.error(traceback.format_exc())


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
