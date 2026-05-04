#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "fastapi",
#   "uvicorn",
#   "yfinance",
#   "pytz",
#   "pandas",
# ]
# ///

"""
Live SPY & VIX Web Tracker with Candlestick Charts

Starts a web server at http://localhost:8765 showing live candlestick
charts for SPY and VIX with 5-minute candles, updated in real-time.

Usage:
  ./spy-vix-live-tracker.py
  ./spy-vix-live-tracker.py --port 9000
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from datetime import time as dt_time

import pandas as pd
import pytz
import yfinance as yf
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

TIMEZONE = pytz.timezone("US/Eastern")
POLL_INTERVAL = 300
ROLLUP_CANDLES = 6

data_cache = {}
sse_clients = set()

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SPY & VIX Live Tracker</title>
<script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0b0e14;color:#d1d4dc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:16px}
#header{display:flex;align-items:center;justify-content:space-between;padding:0 8px 16px;flex-wrap:wrap;gap:8px}
#header h1{font-size:20px;font-weight:600;letter-spacing:-0.3px}
#status{font-size:13px;color:#787b86}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.stats .card{background:#131722;border:1px solid #2a2e39;border-radius:8px;padding:10px 14px}
.stats .card .label{font-size:10px;color:#787b86;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px}
.stats .card .value{font-size:18px;font-weight:600}
.stats .card .sub{font-size:12px;margin-top:2px}
.pos{color:#26a69a}.neg{color:#ef5350}.neut{color:#d1d4dc}
.chart-wrap{background:#131722;border:1px solid #2a2e39;border-radius:8px;overflow:hidden;margin-bottom:12px}
.chart-title{display:flex;align-items:center;gap:12px;padding:10px 16px 0;font-size:13px;color:#787b86;text-transform:uppercase;letter-spacing:0.5px}
.chart-title .price{font-size:22px;font-weight:600;color:#d1d4dc;text-transform:none;letter-spacing:0}
.chart-title .change{font-size:13px;font-weight:500;margin-left:auto}
.chart-title .change.pos{color:#26a69a}
.chart-title .change.neg{color:#ef5350}
.chart-container{height:340px}
.chart-container.vix{height:280px}
@media(max-width:640px){.stats{grid-template-columns:repeat(2,1fr)}.chart-container{height:280px}.chart-container.vix{height:220px}#header h1{font-size:16px}}
</style>
</head>
<body>
<div id="header"><h1>SPY &amp; VIX Live Tracker</h1><span id="status">Connecting...</span></div>
<div class="stats">
<div class="card"><div class="label">SPY 30m</div><div class="value" id="spy-30m">--</div><div class="sub" id="spy-30m-range"></div></div>
<div class="card"><div class="label">VIX 30m</div><div class="value" id="vix-30m">--</div><div class="sub" id="vix-30m-range"></div></div>
<div class="card"><div class="label">SPY Range</div><div class="value" id="spy-range">--</div><div class="sub" id="spy-range-pct"></div></div>
<div class="card"><div class="label">Relation</div><div class="value" id="relation">--</div><div class="sub" id="relation-sub"></div></div>
</div>
<div class="chart-wrap">
<div class="chart-title">SPY - SPDR S&P 500 ETF<span id="spy-price" class="price">--</span><span id="spy-change" class="change">--</span></div>
<div id="spy-chart" class="chart-container"></div>
</div>
<div class="chart-wrap">
<div class="chart-title">VIX - CBOE Volatility Index<span id="vix-price" class="price">--</span><span id="vix-change" class="change">--</span></div>
<div id="vix-chart" class="chart-container vix"></div>
</div>
<script>
const theme={bg:'#131722',text:'#d1d4dc',grid:'#2a2e39',up:'#26a69a',dn:'#ef5350'};
function mkChart(id,h){return LightweightCharts.createChart(document.getElementById(id),{
  layout:{background:{type:'solid',color:theme.bg},textColor:theme.text,fontSize:11},
  grid:{vertLines:{color:theme.grid},horzLines:{color:theme.grid}},
  timeScale:{timeVisible:true,secondsVisible:false,borderColor:theme.grid},
  rightPriceScale:{borderColor:theme.grid},crosshair:{mode:LightweightCharts.CrosshairMode.Normal},
  width:document.getElementById(id).clientWidth||800,height:h,handleScroll:false,handleScale:false,
});}
function fmtPct(v){return (v>=0?'+':'')+v.toFixed(2)+'%'}
function fmtChg(v){return (v>=0?'+':'')+v.toFixed(2)}
function setInfo(id,val,chg,pct){
  document.getElementById(id+'-price').textContent=val;
  const el=document.getElementById(id+'-change');
  if(chg==null){el.textContent='--';el.className='change';return}
  el.textContent=fmtChg(chg)+' / '+fmtPct(pct);el.className='change '+(chg>=0?'pos':'neg');
}
function cls(v){return v>0?'pos':v<0?'neg':'neut'}
function setText(id,v,unit){
  const el=document.getElementById(id);
  if(v==null){el.textContent='--';el.className='value';return}
  el.textContent=(v>=0?'+':'')+v.toFixed(2)+(unit||'');el.className='value '+cls(v);
}
const spyChart=mkChart('spy-chart',340),vixChart=mkChart('vix-chart',280);
const spySeries=spyChart.addCandlestickSeries({upColor:theme.up,downColor:theme.dn,borderDownColor:theme.dn,borderUpColor:theme.up,wickDownColor:theme.dn,wickUpColor:theme.up});
const vixSeries=vixChart.addCandlestickSeries({upColor:theme.up,downColor:theme.dn,borderDownColor:theme.dn,borderUpColor:theme.up,wickDownColor:theme.dn,wickUpColor:theme.up});
let sync=false;
function link(src,tgt){src.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(sync||!r)return;sync=true;tgt.timeScale().setVisibleLogicalRange(r);sync=false;});}
link(spyChart,vixChart);link(vixChart,spyChart);
function resize(){const w=document.getElementById('spy-chart').clientWidth;[spyChart,vixChart].forEach(c=>c.applyOptions({width:w}));}
window.addEventListener('resize',resize);
const es=new EventSource('/stream');
es.onmessage=function(e){
  try{
    const d=JSON.parse(e.data);
    document.getElementById('status').textContent=d.last_update?'Last update: '+d.last_update:'Waiting...';
    if(d.spy&&d.spy.length){spySeries.setData(d.spy);setInfo('spy',d.spy_last_val,d.spy_last_chg,d.spy_last_pct)}
    if(d.vix&&d.vix.length){vixSeries.setData(d.vix);setInfo('vix',d.vix_last_val,d.vix_last_chg,d.vix_last_pct)}
    if(d.last_candle_time){spyChart.timeScale().scrollToRealTime()}
    setText('spy-30m',d.s30_chg);document.getElementById('spy-30m-range').textContent=d.s30_pct!=null?fmtPct(d.s30_pct):'';
    setText('vix-30m',d.v30_chg);document.getElementById('vix-30m-range').textContent=d.v30_pct!=null?fmtPct(d.v30_pct):'';
    setText('spy-range',d.s30_range,'');document.getElementById('spy-range-pct').textContent=d.s30_range_pct!=null?d.s30_range_pct.toFixed(2)+'% range':'';
    const rel=d.relation,relEl=document.getElementById('relation');
    if(rel==='divergent'){relEl.textContent='Divergent';relEl.className='value'}
    else if(rel==='spy_down'){relEl.textContent='Risk-Off';relEl.className='value neg'}
    else if(rel==='spy_up'){relEl.textContent='Risk-On';relEl.className='value pos'}
    else{relEl.textContent='--';relEl.className='value'}
    document.getElementById('relation-sub').textContent=d.relation_detail||'';
  }catch(e){console.error(e)}
};
es.onerror=function(){document.getElementById('status').textContent='Connection lost – reconnecting...';};
setTimeout(resize,100);
</script>
</body>
</html>"""


def now_et():
    return datetime.now(TIMEZONE)


def is_market_open():
    now = now_et()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dt_time(9, 30) <= t <= dt_time(16, 0)


def prev_close(ticker):
    try:
        return yf.Ticker(ticker).info.get("regularMarketPreviousClose")
    except Exception:
        return None


def fetch_ohlcv(ticker):
    df = yf.Ticker(ticker).history(period="2d", interval="5m", auto_adjust=True)
    if df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    rows = []
    for idx, row in df.iterrows():
        ts = idx.tz_convert("US/Eastern") if idx.tz else TIMEZONE.localize(idx)
        t = ts.time()
        if dt_time(9, 30) <= t <= dt_time(16, 0):
            rows.append(
                {
                    "time": int(ts.timestamp()),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "date": ts.date(),
                }
            )

    if not rows:
        return []

    latest = max(r["date"] for r in rows)
    return [
        {k: v for k, v in r.items() if k != "date"} for r in rows if r["date"] == latest
    ]


def latest_price_and_change(ticker, candles):
    if not candles:
        return None, None, None
    last = candles[-1]["close"]
    pc = prev_close(ticker)
    if pc is None:
        return last, None, None
    chg = round(last - pc, 2)
    return last, chg, round(chg / pc * 100, 2)


def rolling_movement(candles, n=ROLLUP_CANDLES):
    if len(candles) < 2:
        return None, None, None, None
    recent = candles[-n:] if len(candles) >= n else candles
    start = recent[0]["close"]
    end = recent[-1]["close"]
    chg = round(end - start, 2)
    pct = round(chg / start * 100, 2) if start else None
    hi = max(c["high"] for c in recent)
    lo = min(c["low"] for c in recent)
    rng = round(hi - lo, 2)
    return chg, pct, rng, round(rng / start * 100, 2) if start else None


def relation(spy_chg, vix_chg):
    if spy_chg is None or vix_chg is None:
        return None, None
    if spy_chg < 0 and vix_chg > 0:
        return "divergent", "SPY ↓ VIX ↑"
    if spy_chg > 0 and vix_chg < 0:
        return "divergent", "SPY ↑ VIX ↓"
    if spy_chg < 0:
        return "spy_down", "Both down"
    if spy_chg > 0:
        return "spy_up", "Both up"
    return None, None


def build_payload():
    spy = data_cache.get("SPY", [])
    vix = data_cache.get("^VIX", [])
    spy_val, spy_chg, spy_pct = latest_price_and_change("SPY", spy)
    vix_val, vix_chg, vix_pct = latest_price_and_change("^VIX", vix)
    s30c, s30p, s30r, s30rp = rolling_movement(spy)
    v30c, v30p, _, _ = rolling_movement(vix)
    rel, rel_detail = relation(s30c, v30c)
    return json.dumps(
        {
            "spy": spy,
            "vix": vix,
            "spy_last_val": spy_val,
            "spy_last_chg": spy_chg,
            "spy_last_pct": spy_pct,
            "vix_last_val": vix_val,
            "vix_last_chg": vix_chg,
            "vix_last_pct": vix_pct,
            "s30_chg": s30c,
            "s30_pct": s30p,
            "s30_range": s30r,
            "s30_range_pct": s30rp,
            "v30_chg": v30c,
            "v30_pct": v30p,
            "relation": rel,
            "relation_detail": rel_detail,
            "last_update": data_cache.get("last_update"),
            "last_candle_time": spy[-1]["time"] if spy else None,
        }
    )


async def notify_clients():
    payload = build_payload()
    dead = [q for q in sse_clients if not await _safe_put(q, payload)]
    for q in dead:
        sse_clients.discard(q)


async def _safe_put(queue, payload):
    try:
        await queue.put(payload)
        return True
    except Exception:
        return False


async def poll_loop():
    await asyncio.sleep(2)
    try:
        spy, vix = await asyncio.gather(
            asyncio.to_thread(fetch_ohlcv, "SPY"),
            asyncio.to_thread(fetch_ohlcv, "^VIX"),
        )
        if spy:
            data_cache["SPY"] = spy
        if vix:
            data_cache["^VIX"] = vix
        data_cache["last_update"] = now_et().strftime("%H:%M:%S ET")
    except Exception as e:
        logging.error(f"Initial fetch failed: {e}")

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        if not is_market_open():
            continue
        try:
            spy, vix = await asyncio.gather(
                asyncio.to_thread(fetch_ohlcv, "SPY"),
                asyncio.to_thread(fetch_ohlcv, "^VIX"),
            )
            if spy:
                data_cache["SPY"] = spy
            if vix:
                data_cache["^VIX"] = vix
            data_cache["last_update"] = now_et().strftime("%H:%M:%S ET")
            await notify_clients()
        except Exception as e:
            logging.error(f"Poll failed: {e}")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(poll_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.get("/stream")
async def stream():
    queue = asyncio.Queue()
    sse_clients.add(queue)

    async def event_gen():
        try:
            yield f"data: {build_payload()}\n\n"
            while True:
                payload = await queue.get()
                yield f"data: {payload}\n\n"
        except asyncio.CancelledError:
            sse_clients.discard(queue)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def main():
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.captureWarnings(True)

    port = 8765
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    elif len(sys.argv) > 2 and sys.argv[1] == "--port":
        port = int(sys.argv[2])

    logging.info(f"Starting server at http://localhost:{port}")
    import uvicorn

    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    except KeyboardInterrupt:
        logging.info("Shutting down...")


if __name__ == "__main__":
    main()
