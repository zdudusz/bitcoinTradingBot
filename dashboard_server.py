"""
dashboard_server.py
--------------------
Servidor local que expõe os dados do bot via HTTP para o dashboard HTML.
Rode este arquivo em um terminal separado enquanto o bot opera.

Uso:
    python dashboard_server.py

Acesse no navegador:
    http://localhost:8765
"""

import os
import json
import time
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

try:
    import ccxt
except ImportError:
    print("Instale o ccxt: pip install ccxt")
    exit(1)

# ----------------------------------------------------------------
# Config
# ----------------------------------------------------------------
API_KEY    = os.getenv("API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"
SYMBOL     = os.getenv("SYMBOL", "BTC/USDT")
LOG_FILE   = os.getenv("LOG_FILE", "logs/trading_bot.log")
PORT       = 8765
CACHE_TTL  = 15  # segundos entre atualizações

# ----------------------------------------------------------------
# Cache global
# ----------------------------------------------------------------
cache = {"data": {}, "last_update": 0}
exchange = None


def init_exchange():
    global exchange
    ex = ccxt.binance({
        "apiKey": API_KEY,
        "secret": SECRET_KEY,
        "timeout": 15000,
        "enableRateLimit": True,
    })
    if USE_TESTNET:
        ex.set_sandbox_mode(True)
    exchange = ex
    print(f"Conectado à Binance {'TESTNET' if USE_TESTNET else 'REAL'}")


def fetch_data():
    data = {}
    try:
        # Preço atual
        ticker = exchange.fetch_ticker(SYMBOL)
        data["price"] = float(ticker["last"])
        data["price_change_pct"] = float(ticker.get("percentage") or 0)

        # Saldo
        bal = exchange.fetch_balance()
        data["usdt_free"]  = float(bal.get("USDT", {}).get("free",  0))
        data["usdt_total"] = float(bal.get("USDT", {}).get("total", 0))
        data["btc_free"]   = float(bal.get("BTC",  {}).get("free",  0))
        data["btc_total"]  = float(bal.get("BTC",  {}).get("total", 0))
        data["portfolio"]  = data["usdt_total"] + data["btc_total"] * data["price"]

        # Ordens abertas
        open_orders = exchange.fetch_open_orders(SYMBOL)
        data["open_orders"] = [
            {
                "id": str(o.get("id", ""))[:12],
                "side": o.get("side", ""),
                "amount": float(o.get("amount", 0)),
                "price": float(o.get("price") or 0),
                "status": o.get("status", ""),
            }
            for o in open_orders
        ]

        # Últimos trades
        trades = exchange.fetch_my_trades(SYMBOL, limit=20)
        data["trades"] = []
        daily_pnl = 0.0
        wins = losses = 0
        today = datetime.now(timezone.utc).date()

        for t in reversed(trades):
            ts = datetime.fromtimestamp(t["timestamp"] / 1000, tz=timezone.utc)
            side = t.get("side", "").upper()
            qty  = float(t.get("amount", 0))
            px   = float(t.get("price", 0))
            fee  = float((t.get("fee") or {}).get("cost", 0))
            total = qty * px

            data["trades"].append({
                "time": ts.strftime("%H:%M:%S"),
                "date": ts.strftime("%Y-%m-%d"),
                "side": side,
                "qty": round(qty, 6),
                "price": round(px, 2),
                "total": round(total, 2),
                "fee": round(fee, 4),
            })

            if ts.date() == today:
                if side == "SELL":
                    daily_pnl += total - fee
                    wins += 1
                elif side == "BUY":
                    daily_pnl -= total + fee
                    losses += 1

        data["daily_pnl"] = round(daily_pnl, 4)
        data["wins"] = wins
        data["losses"] = losses

        # OHLCV para indicadores simples
        ohlcv = exchange.fetch_ohlcv(SYMBOL, "15m", limit=220)
        closes = [c[4] for c in ohlcv]
        data["sma200"] = round(sum(closes[-200:]) / 200, 2) if len(closes) >= 200 else None

        # RSI simples
        if len(closes) >= 15:
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains  = [d if d > 0 else 0 for d in deltas[-14:]]
            losses_ = [abs(d) if d < 0 else 0 for d in deltas[-14:]]
            avg_g = sum(gains) / 14
            avg_l = sum(losses_) / 14
            if avg_l == 0:
                data["rsi"] = 100.0
            else:
                rs = avg_g / avg_l
                data["rsi"] = round(100 - 100 / (1 + rs), 2)
        else:
            data["rsi"] = 50.0

        # Sinal atual
        rsi = data["rsi"]
        price = data["price"]
        sma = data.get("sma200") or price
        if rsi < 30 and price > sma:
            data["signal"] = "BUY"
        elif rsi > 70:
            data["signal"] = "SELL"
        else:
            data["signal"] = "HOLD"

        # Últimas linhas do log
        data["logs"] = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            data["logs"] = [l.strip() for l in lines[-15:]]

        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        data["testnet"] = USE_TESTNET
        data["symbol"] = SYMBOL

    except Exception as e:
        data["error"] = str(e)

    return data


def refresh_loop():
    while True:
        try:
            d = fetch_data()
            cache["data"] = d
            cache["last_update"] = time.time()
        except Exception as e:
            print(f"Erro ao atualizar cache: {e}")
        time.sleep(CACHE_TTL)


# ----------------------------------------------------------------
# Dashboard HTML
# ----------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>BTC Trading Bot — Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0c0f;color:#e8eaed;font-family:'Courier New',monospace;font-size:13px;overflow-x:hidden}
:root{
  --bg1:#111418;--bg2:#181c22;--bg3:#1e242c;
  --border:#ffffff12;--border2:#ffffff20;
  --text2:#9aa0a6;--text3:#5f6368;
  --green:#00d97e;--red:#ff4757;--amber:#ffa940;--blue:#4096ff;--purple:#7c4dff;
}
.topbar{background:var(--bg1);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}
.logo{font-size:16px;font-weight:700;letter-spacing:3px;color:var(--amber)}
.price-big{font-size:24px;font-weight:700;color:var(--green)}
.price-chg{font-size:12px;margin-left:8px}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block;margin-right:6px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.pill{background:var(--bg3);border:1px solid var(--border2);padding:3px 10px;border-radius:4px;font-size:11px;color:var(--text2);margin-left:8px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--border);margin-bottom:1px}
.kpi{background:var(--bg1);padding:14px 18px}
.kpi-label{font-size:10px;color:var(--text3);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:4px}
.kpi-val{font-size:20px;font-weight:700}
.kpi-sub{font-size:10px;color:var(--text3);margin-top:2px}
.green{color:var(--green)}.red{color:var(--red)}.amber{color:var(--amber)}.blue{color:var(--blue)}.purple{color:var(--purple)}
.section{background:var(--bg1);border-bottom:1px solid var(--border);padding:14px 20px}
.section-title{font-size:10px;letter-spacing:1.5px;color:var(--text3);text-transform:uppercase;margin-bottom:12px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border);margin-bottom:1px}
.three-col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--border);margin-bottom:1px}
.ind-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)}
.ind-row:last-child{border-bottom:none}
.bar-wrap{width:80px;height:5px;background:var(--bg3);border-radius:3px;margin:0 10px;flex-shrink:0}
.bar{height:5px;border-radius:3px;transition:width .6s}
.trade-row{display:grid;grid-template-columns:60px 110px 110px 110px 80px 80px;gap:0;padding:7px 20px;border-bottom:1px solid var(--border);align-items:center;font-size:11px}
.trade-row:hover{background:var(--bg2)}
.trade-head{display:grid;grid-template-columns:60px 110px 110px 110px 80px 80px;gap:0;padding:6px 20px;border-bottom:1px solid var(--border);font-size:10px;color:var(--text3);letter-spacing:1px;text-transform:uppercase}
.side-badge{font-weight:700;font-size:10px;padding:2px 8px;border-radius:3px;display:inline-block;text-align:center}
.side-buy{background:#00d97e22;color:var(--green)}
.side-sell{background:#ff475722;color:var(--red)}
.log-area{background:var(--bg2);border-radius:4px;padding:10px;font-size:10px;line-height:1.8;max-height:200px;overflow-y:auto}
.log-info{color:var(--text2)}.log-buy{color:var(--green)}.log-sell{color:var(--red)}.log-warn{color:var(--amber)}.log-sys{color:var(--blue)}
.pos-card{background:var(--bg2);border:1px solid var(--border2);border-radius:6px;padding:14px}
.pos-row{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border)}
.pos-row:last-child{border-bottom:none}
.pos-pnl{font-size:20px;font-weight:700;text-align:center;padding:10px 0;border-top:1px solid var(--border);margin-top:8px}
.cb-wrap{height:8px;background:var(--bg3);border-radius:4px;margin:8px 0}
.cb-fill{height:8px;border-radius:4px;background:var(--green);transition:width 1s}
.risk-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border);font-size:12px}
.risk-row:last-child{border-bottom:none}
.footer{background:var(--bg1);border-top:1px solid var(--border);padding:8px 20px;display:flex;justify-content:space-between;font-size:10px;color:var(--text3)}
.badge-testnet{background:#ffa94022;color:var(--amber);padding:2px 8px;border-radius:3px;font-size:10px;font-weight:700}
.badge-live{background:#ff475722;color:var(--red);padding:2px 8px;border-radius:3px;font-size:10px;font-weight:700}
.error-bar{background:#ff475722;border-left:3px solid var(--red);padding:8px 14px;font-size:11px;color:var(--red);margin:4px 0}
</style>
</head>
<body>

<div class="topbar">
  <div style="display:flex;align-items:center;gap:12px">
    <span class="logo">BTCBOT</span>
    <span class="pill" id="pair-label">BTC/USDT</span>
    <span id="net-badge" class="badge-testnet">TESTNET</span>
  </div>
  <div style="display:flex;align-items:baseline">
    <span class="price-big" id="t-price">--</span>
    <span class="price-chg" id="t-price-chg">--</span>
  </div>
  <div style="display:flex;align-items:center;gap:20px;font-size:11px;color:var(--text2)">
    <span><span class="status-dot"></span>BOT ATIVO</span>
    <span id="t-clock">--:--:-- UTC</span>
    <span style="color:var(--text3)">Atualiza a cada 15s</span>
  </div>
</div>

<div id="error-area"></div>

<div class="grid">
  <div class="kpi"><div class="kpi-label">USDT Livre</div><div class="kpi-val green" id="k-usdt">--</div><div class="kpi-sub">disponível</div></div>
  <div class="kpi"><div class="kpi-label">BTC Total</div><div class="kpi-val amber" id="k-btc">--</div><div class="kpi-sub">carteira</div></div>
  <div class="kpi"><div class="kpi-label">Portfólio</div><div class="kpi-val" id="k-port">--</div><div class="kpi-sub">em USDT</div></div>
  <div class="kpi"><div class="kpi-label">PnL do Dia</div><div class="kpi-val" id="k-pnl">--</div><div class="kpi-sub" id="k-trades-count">0 trades</div></div>
</div>

<div class="two-col">
  <div class="section">
    <div class="section-title">Indicadores Técnicos</div>
    <div class="ind-row">
      <span style="color:var(--text2)">RSI(14)</span>
      <div class="bar-wrap"><div class="bar" id="rsi-bar" style="width:50%;background:var(--amber)"></div></div>
      <span class="amber" id="ind-rsi" style="font-size:14px;font-weight:700">--</span>
    </div>
    <div class="ind-row">
      <span style="color:var(--text2)">SMA(200)</span>
      <div class="bar-wrap"><div class="bar" style="width:100%;background:var(--blue)"></div></div>
      <span class="blue" id="ind-sma" style="font-size:14px;font-weight:700">--</span>
    </div>
    <div class="ind-row">
      <span style="color:var(--text2)">Sinal Atual</span>
      <div class="bar-wrap"></div>
      <span id="ind-signal" style="font-size:14px;font-weight:700">--</span>
    </div>
    <div class="ind-row">
      <span style="color:var(--text2)">Preço vs SMA</span>
      <div class="bar-wrap"></div>
      <span id="ind-trend" style="font-size:14px;font-weight:700">--</span>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Posição Aberta</div>
    <div class="pos-card" id="pos-card">
      <div style="color:var(--text3);font-size:12px;text-align:center;padding:10px 0">Nenhuma posição ativa</div>
    </div>
  </div>
</div>

<div class="two-col">
  <div class="section">
    <div class="section-title">Circuit Breaker Diário</div>
    <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px">
      <span style="color:var(--text2)">Perda acumulada</span>
      <span id="cb-val" class="amber">0.00%</span>
    </div>
    <div class="cb-wrap"><div class="cb-fill" id="cb-bar" style="width:0%"></div></div>
    <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text3)">
      <span>0%</span><span>LIMITE: 5%</span>
    </div>
    <div style="margin-top:12px">
      <div class="risk-row"><span style="color:var(--text2)">Position Size</span><span class="amber">5% por trade</span></div>
      <div class="risk-row"><span style="color:var(--text2)">Stop Loss</span><span class="red">2.5%</span></div>
      <div class="risk-row"><span style="color:var(--text2)">Take Profit</span><span class="green">5.0%</span></div>
      <div class="risk-row"><span style="color:var(--text2)">Ratio R/R</span><span class="purple">2:1</span></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Estatísticas do Dia</div>
    <div class="risk-row"><span style="color:var(--text2)">Total trades</span><span id="st-total">--</span></div>
    <div class="risk-row"><span style="color:var(--text2)">Wins (vendas c/ lucro)</span><span class="green" id="st-wins">--</span></div>
    <div class="risk-row"><span style="color:var(--text2)">Losses</span><span class="red" id="st-losses">--</span></div>
    <div class="risk-row" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">
      <span style="color:var(--text2);font-weight:700">PnL Líquido</span>
      <span id="st-pnl" style="font-size:16px;font-weight:700">--</span>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">Histórico de Trades</div>
  <div class="trade-head">
    <span>Lado</span><span>Horário</span><span>Preço</span><span>Total USDT</span><span>Qtd BTC</span><span>Taxa</span>
  </div>
  <div id="trades-list"><div style="padding:16px 20px;color:var(--text3);font-size:11px">Nenhum trade encontrado</div></div>
</div>

<div class="section">
  <div class="section-title">Log ao vivo (últimas 15 linhas)</div>
  <div class="log-area" id="log-area">
    <div class="log-sys">Aguardando dados do bot...</div>
  </div>
</div>

<div class="footer">
  <span>BTC Trading Bot v1.0 — RSI(14) + SMA(200)</span>
  <span id="f-updated">--</span>
  <span>SL 2.5% | TP 5.0% | Circuit Breaker 5%/dia</span>
</div>

<script>
function pad(n){return String(n).padStart(2,'0')}
function utcClock(){
  const d=new Date();
  return pad(d.getUTCHours())+':'+pad(d.getUTCMinutes())+':'+pad(d.getUTCSeconds())+' UTC';
}
setInterval(()=>{document.getElementById('t-clock').textContent=utcClock();},1000);

function fmtUSD(v,dec=2){
  return '$'+parseFloat(v).toLocaleString('pt-BR',{minimumFractionDigits:dec,maximumFractionDigits:dec});
}
function signColor(v){return v>=0?'var(--green)':'var(--red)'}
function signStr(v){return (v>=0?'+':'')+v.toFixed(4)}

async function fetchData(){
  try{
    const r=await fetch('/api');
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    render(d);
    document.getElementById('error-area').innerHTML='';
  }catch(e){
    document.getElementById('error-area').innerHTML=
      '<div class="error-bar">Erro ao buscar dados: '+e.message+' — verifique se dashboard_server.py está rodando</div>';
  }
}

function render(d){
  if(d.error){
    document.getElementById('error-area').innerHTML='<div class="error-bar">'+d.error+'</div>';
    return;
  }

  document.getElementById('t-price').textContent=fmtUSD(d.price);
  const pchg=d.price_change_pct||0;
  const pchgEl=document.getElementById('t-price-chg');
  pchgEl.textContent=(pchg>=0?'+':'')+pchg.toFixed(2)+'%';
  pchgEl.style.color=pchg>=0?'var(--green)':'var(--red)';

  document.getElementById('net-badge').textContent=d.testnet?'TESTNET':'PRODUÇÃO';
  document.getElementById('net-badge').className=d.testnet?'badge-testnet':'badge-live';

  document.getElementById('k-usdt').textContent=fmtUSD(d.usdt_free);
  document.getElementById('k-btc').textContent=(d.btc_total||0).toFixed(6)+' BTC';
  document.getElementById('k-port').textContent=fmtUSD(d.portfolio);

  const pnl=d.daily_pnl||0;
  const pnlEl=document.getElementById('k-pnl');
  pnlEl.textContent=(pnl>=0?'+':'')+fmtUSD(Math.abs(pnl));
  pnlEl.style.color=signColor(pnl);
  const tot=(d.wins||0)+(d.losses||0);
  document.getElementById('k-trades-count').textContent=tot+' trades hoje';

  const rsi=d.rsi||50;
  document.getElementById('ind-rsi').textContent=rsi.toFixed(2);
  document.getElementById('ind-rsi').style.color=rsi<30?'var(--green)':rsi>70?'var(--red)':'var(--amber)';
  document.getElementById('rsi-bar').style.width=rsi+'%';
  document.getElementById('rsi-bar').style.background=rsi<30?'var(--green)':rsi>70?'var(--red)':'var(--amber)';

  document.getElementById('ind-sma').textContent=d.sma200?fmtUSD(d.sma200,0):'--';

  const sig=d.signal||'HOLD';
  const sigEl=document.getElementById('ind-signal');
  sigEl.textContent=sig;
  sigEl.style.color=sig==='BUY'?'var(--green)':sig==='SELL'?'var(--red)':'var(--amber)';

  const above=d.price>(d.sma200||0);
  const trendEl=document.getElementById('ind-trend');
  trendEl.textContent=above?'Acima SMA200':'Abaixo SMA200';
  trendEl.style.color=above?'var(--green)':'var(--red)';

  const cbPct=d.usdt_total>0?Math.max(0,-pnl/d.usdt_total*100):0;
  document.getElementById('cb-val').textContent=cbPct.toFixed(2)+'%';
  document.getElementById('cb-bar').style.width=Math.min(100,cbPct*20)+'%';
  document.getElementById('cb-bar').style.background=cbPct>=4?'var(--red)':cbPct>=2?'var(--amber)':'var(--green)';

  document.getElementById('st-total').textContent=tot;
  document.getElementById('st-wins').textContent=d.wins||0;
  document.getElementById('st-losses').textContent=d.losses||0;
  const stPnl=document.getElementById('st-pnl');
  stPnl.textContent=(pnl>=0?'+':'')+fmtUSD(Math.abs(pnl));
  stPnl.style.color=signColor(pnl);

  // Posição
  const posCard=document.getElementById('pos-card');
  if(d.open_orders&&d.open_orders.length>0){
    const o=d.open_orders[0];
    posCard.innerHTML=`
      <div class="pos-row"><span style="color:var(--text2)">Ordem ID</span><span>${o.id}</span></div>
      <div class="pos-row"><span style="color:var(--text2)">Lado</span><span class="${o.side==='buy'?'green':'red'}">${o.side.toUpperCase()}</span></div>
      <div class="pos-row"><span style="color:var(--text2)">Quantidade</span><span>${o.amount} BTC</span></div>
      <div class="pos-row"><span style="color:var(--text2)">Preço</span><span>${fmtUSD(o.price)}</span></div>
      <div class="pos-row"><span style="color:var(--text2)">Status</span><span class="amber">${o.status}</span></div>
    `;
  }else{
    posCard.innerHTML='<div style="color:var(--text3);font-size:12px;text-align:center;padding:10px 0">Nenhuma posição ativa — aguardando sinal</div>';
  }

  // Trades
  const tl=document.getElementById('trades-list');
  if(!d.trades||d.trades.length===0){
    tl.innerHTML='<div style="padding:16px 20px;color:var(--text3);font-size:11px">Nenhum trade encontrado</div>';
  }else{
    tl.innerHTML=d.trades.slice(0,15).map(t=>`
      <div class="trade-row">
        <span class="side-badge ${t.side==='BUY'?'side-buy':'side-sell'}">${t.side}</span>
        <span style="color:var(--text2)">${t.date} ${t.time}</span>
        <span style="font-family:'Courier New',monospace">${fmtUSD(t.price)}</span>
        <span style="font-family:'Courier New',monospace">${fmtUSD(t.total)}</span>
        <span>${t.qty}</span>
        <span style="color:var(--text3)">${t.fee}</span>
      </div>
    `).join('');
  }

  // Logs
  const la=document.getElementById('log-area');
  if(d.logs&&d.logs.length>0){
    la.innerHTML=d.logs.map(l=>{
      let cls='log-info';
      if(l.includes('BUY')||l.includes('TAKE_PROFIT'))cls='log-buy';
      else if(l.includes('STOP_LOSS')||l.includes('ERROR')||l.includes('CRITICAL'))cls='log-sell';
      else if(l.includes('WARNING'))cls='log-warn';
      else if(l.includes('Iniciado')||l.includes('Conectado'))cls='log-sys';
      return `<div class="${cls}">${l}</div>`;
    }).join('');
    la.scrollTop=la.scrollHeight;
  }

  const ts=new Date(d.timestamp);
  document.getElementById('f-updated').textContent=
    'Última atualização: '+ts.toLocaleTimeString('pt-BR')+' UTC';
}

fetchData();
setInterval(fetchData,15000);
</script>
</body>
</html>"""


# ----------------------------------------------------------------
# HTTP Handler
# ----------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Silencia logs do servidor HTTP

    def do_GET(self):
        if self.path == "/api":
            data = cache["data"]
            if not data or (time.time() - cache["last_update"]) > CACHE_TTL * 2:
                data = fetch_data()
                cache["data"] = data
                cache["last_update"] = time.time()
            body = json.dumps(data, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            body = DASHBOARD_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("  BTC Trading Bot — Dashboard Server")
    print("=" * 50)
    init_exchange()

    # Faz a primeira busca de dados antes de iniciar o servidor
    print("Buscando dados iniciais...")
    cache["data"] = fetch_data()
    cache["last_update"] = time.time()

    # Thread de atualização em background
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()

    # Inicia servidor HTTP
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\nDashboard disponível em: http://localhost:{PORT}")
    print("Pressione Ctrl+C para parar.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
