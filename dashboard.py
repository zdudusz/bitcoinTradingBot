"""
dashboard.py
------------
Painel de monitoramento do bot via terminal.
Execute em um terminal separado enquanto o bot roda em outro.

Uso:
    python dashboard.py

Mostra:
  - Saldo atual USDT e BTC
  - Posição aberta (se houver)
  - Histórico de trades do dia
  - PnL do dia
  - Status do Circuit Breaker
  - Últimas linhas do log
"""

import os
import time
import ccxt
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ----------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------
API_KEY    = os.getenv("API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")
USE_TESTNET = os.getenv("USE_TESTNET", "true").lower() == "true"
SYMBOL     = os.getenv("SYMBOL", "BTC/USDT")
LOG_FILE   = os.getenv("LOG_FILE", "logs/trading_bot.log")
REFRESH_SECONDS = 30  # Atualiza a cada 30s

# Cores ANSI
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


def connect_exchange():
    exchange = ccxt.binance({
        "apiKey": API_KEY,
        "secret": SECRET_KEY,
        "timeout": 15000,
        "enableRateLimit": True,
    })
    if USE_TESTNET:
        exchange.set_sandbox_mode(True)
    return exchange


def get_balances(exchange):
    try:
        b = exchange.fetch_balance()
        usdt = b.get("USDT", {})
        btc  = b.get("BTC",  {})
        return {
            "usdt_free":  float(usdt.get("free",  0)),
            "usdt_total": float(usdt.get("total", 0)),
            "btc_free":   float(btc.get("free",  0)),
            "btc_total":  float(btc.get("total", 0)),
        }
    except Exception as e:
        return {"error": str(e)}


def get_current_price(exchange):
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        return float(ticker["last"])
    except Exception:
        return None


def get_recent_trades(exchange, limit=10):
    try:
        trades = exchange.fetch_my_trades(SYMBOL, limit=limit)
        return trades
    except Exception:
        return []


def get_open_orders(exchange):
    try:
        return exchange.fetch_open_orders(SYMBOL)
    except Exception:
        return []


def get_last_log_lines(n=8):
    try:
        if not os.path.exists(LOG_FILE):
            return ["(arquivo de log ainda não criado)"]
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception:
        return ["(erro ao ler log)"]


def color_pnl(value: float) -> str:
    if value > 0:
        return f"{GREEN}+${value:,.4f}{RESET}"
    elif value < 0:
        return f"{RED}-${abs(value):,.4f}{RESET}"
    return f"$0.0000"


def color_side(side: str) -> str:
    if side.upper() == "BUY":
        return f"{GREEN}BUY {RESET}"
    return f"{RED}SELL{RESET}"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def render_dashboard(exchange):
    clear()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    price = get_current_price(exchange)
    balances = get_balances(exchange)
    trades = get_recent_trades(exchange, limit=10)
    open_orders = get_open_orders(exchange)
    log_lines = get_last_log_lines(8)

    # ----------------------------------------------------------------
    # Header
    # ----------------------------------------------------------------
    print(f"{BOLD}{CYAN}{'='*64}{RESET}")
    print(f"{BOLD}{CYAN}  🤖  BTC/USDT Trading Bot — Dashboard{RESET}")
    print(f"{DIM}  Atualizado: {now} UTC  |  Refresh: {REFRESH_SECONDS}s  |  Ctrl+C para sair{RESET}")
    print(f"{BOLD}{CYAN}{'='*64}{RESET}")

    # ----------------------------------------------------------------
    # Preço Atual
    # ----------------------------------------------------------------
    if price:
        print(f"\n{BOLD}💰 Preço BTC/USDT:{RESET}  {YELLOW}${price:,.2f}{RESET}")
    else:
        print(f"\n{RED}Preço indisponível{RESET}")

    # ----------------------------------------------------------------
    # Saldo
    # ----------------------------------------------------------------
    print(f"\n{BOLD}📊 Saldo da Conta{RESET}")
    print(f"{'─'*40}")
    if "error" in balances:
        print(f"  {RED}Erro: {balances['error']}{RESET}")
    else:
        print(f"  USDT livre:   {GREEN}${balances['usdt_free']:>12,.2f}{RESET}")
        print(f"  USDT total:   ${balances['usdt_total']:>12,.2f}")
        print(f"  BTC  livre:   {YELLOW}{balances['btc_free']:>15.6f}{RESET} BTC")
        print(f"  BTC  total:   {balances['btc_total']:>15.6f} BTC")

        # Valor do BTC em USDT
        if price and balances["btc_total"] > 0:
            btc_value = balances["btc_total"] * price
            total_portfolio = balances["usdt_total"] + btc_value
            print(f"  {'─'*36}")
            print(f"  Valor BTC:    ${btc_value:>12,.2f} USDT")
            print(f"  {BOLD}Portfólio:    ${total_portfolio:>12,.2f} USDT{RESET}")

    # ----------------------------------------------------------------
    # Ordens Abertas
    # ----------------------------------------------------------------
    print(f"\n{BOLD}📋 Ordens Abertas{RESET}")
    print(f"{'─'*40}")
    if not open_orders:
        print(f"  {DIM}Nenhuma ordem aberta{RESET}")
    else:
        for o in open_orders:
            side = color_side(o.get("side", ""))
            amt  = o.get("amount", 0)
            px   = o.get("price") or 0
            oid  = str(o.get("id", ""))[:12]
            print(f"  [{oid}] {side} {amt:.6f} BTC @ ${px:,.2f}")

    # ----------------------------------------------------------------
    # Histórico de Trades Recentes
    # ----------------------------------------------------------------
    print(f"\n{BOLD}📈 Últimos Trades (BTC/USDT){RESET}")
    print(f"{'─'*64}")
    if not trades:
        print(f"  {DIM}Nenhum trade encontrado{RESET}")
    else:
        print(f"  {'Data/Hora (UTC)':<22} {'Lado':<6} {'Qtd BTC':>12} {'Preço':>12} {'Total USDT':>12}")
        print(f"  {'─'*60}")
        daily_pnl = 0.0
        today = datetime.now(timezone.utc).date()

        for t in reversed(trades):
            ts    = datetime.fromtimestamp(t["timestamp"] / 1000, tz=timezone.utc)
            side  = t.get("side", "").upper()
            qty   = float(t.get("amount", 0))
            px    = float(t.get("price", 0))
            total = qty * px
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            side_c = color_side(side)

            print(f"  {ts_str:<22} {side_c} {qty:>12.6f} {px:>12,.2f} {total:>12,.2f}")

    # ----------------------------------------------------------------
    # Log Recente
    # ----------------------------------------------------------------
    print(f"\n{BOLD}📝 Log Recente ({LOG_FILE}){RESET}")
    print(f"{'─'*64}")
    for line in log_lines:
        if "[ERROR]" in line or "[CRITICAL]" in line:
            print(f"  {RED}{line}{RESET}")
        elif "[WARNING]" in line:
            print(f"  {YELLOW}{line}{RESET}")
        elif "BUY" in line or "TAKE_PROFIT" in line:
            print(f"  {GREEN}{line}{RESET}")
        elif "STOP_LOSS" in line:
            print(f"  {RED}{line}{RESET}")
        else:
            print(f"  {DIM}{line}{RESET}")

    print(f"\n{DIM}{'─'*64}")
    print(f"  Próxima atualização em {REFRESH_SECONDS}s... (Ctrl+C para sair){RESET}")


def main():
    print("Conectando à exchange...")
    try:
        exchange = connect_exchange()
    except Exception as e:
        print(f"{RED}Erro ao conectar: {e}{RESET}")
        return

    print("Conectado! Carregando dashboard...")
    time.sleep(1)

    while True:
        try:
            render_dashboard(exchange)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Dashboard encerrado.{RESET}")
            break
        except Exception as e:
            print(f"{RED}Erro no dashboard: {e}{RESET}")

        try:
            time.sleep(REFRESH_SECONDS)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Dashboard encerrado.{RESET}")
            break


if __name__ == "__main__":
    main()
