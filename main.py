"""
========================================================================
BTC/USDT Algorithmic Trading Bot
========================================================================
Estratégia: RSI(14) + SMA(200) com Gestão de Risco Estrita
Autor: Gerado via Engenharia de Software - FinTech
Versão: 1.0.0

AVISO: Use apenas em Testnet/Paper Trading até validar completamente.
========================================================================
"""

import time
import logging
import sys
from datetime import datetime

from config import Config
from exchange_client import ExchangeClient
from strategy import TradingStrategy
from risk_manager import RiskManager
from circuit_breaker import CircuitBreaker
from logger_setup import setup_logger


def main():
    # ----------------------------------------------------------------
    # 1. Inicialização do Logger
    # ----------------------------------------------------------------
    logger = setup_logger()
    logger.info("=" * 60)
    logger.info("  BTC/USDT Trading Bot Iniciado")
    logger.info(f"  Timestamp: {datetime.utcnow().isoformat()} UTC")
    logger.info("=" * 60)

    # ----------------------------------------------------------------
    # 2. Carrega Configurações
    # ----------------------------------------------------------------
    config = Config()
    logger.info(f"Configurações carregadas | Par: {config.SYMBOL} | "
                f"Timeframe: {config.TIMEFRAME} | Testnet: {config.USE_TESTNET}")

    # ----------------------------------------------------------------
    # 3. Instancia os Módulos
    # ----------------------------------------------------------------
    exchange = ExchangeClient(config, logger)
    strategy = TradingStrategy(config, logger)
    risk_manager = RiskManager(config, logger)
    circuit_breaker = CircuitBreaker(config, logger)

    # Estado interno da posição aberta
    position = {
        "active": False,
        "entry_price": None,
        "quantity": None,
        "stop_loss": None,
        "take_profit": None,
        "order_id": None,
        "entry_time": None,
    }

    logger.info("Todos os módulos inicializados. Entrando no loop principal...")

    # ----------------------------------------------------------------
    # 4. Loop Principal
    # ----------------------------------------------------------------
    while True:
        try:
            # --- 4.1. Verifica Circuit Breaker ---
            if circuit_breaker.is_triggered():
                logger.critical(
                    "CIRCUIT BREAKER ATIVADO: Perdas diárias atingiram o limite. "
                    "Bot encerrando operações pelo restante do dia."
                )
                # Aguarda até meia-noite UTC para resetar
                seconds_until_reset = circuit_breaker.seconds_until_reset()
                logger.info(f"Próximo reset em {seconds_until_reset:.0f} segundos.")
                time.sleep(min(seconds_until_reset, 3600))  # Verifica a cada 1h
                continue

            # --- 4.2. Busca Dados de Mercado ---
            logger.debug("Buscando dados OHLCV...")
            ohlcv_df = exchange.fetch_ohlcv()
            if ohlcv_df is None or ohlcv_df.empty:
                logger.warning("Dados OHLCV indisponíveis. Aguardando próximo ciclo...")
                time.sleep(config.LOOP_INTERVAL_SECONDS)
                continue

            current_price = ohlcv_df["close"].iloc[-1]
            logger.info(f"Preço atual BTC/USDT: ${current_price:,.2f}")

            # --- 4.3. Calcula Indicadores ---
            ohlcv_df = strategy.calculate_indicators(ohlcv_df)
            rsi = ohlcv_df["rsi"].iloc[-1]
            sma200 = ohlcv_df["sma200"].iloc[-1]
            logger.info(f"Indicadores | RSI(14): {rsi:.2f} | SMA(200): ${sma200:,.2f}")

            # --- 4.4. Gerencia Posição Aberta (Stop Loss / Take Profit) ---
            if position["active"]:
                exit_reason = risk_manager.check_exit_conditions(
                    current_price, position, rsi
                )
                if exit_reason:
                    logger.info(f"Sinal de saída detectado: {exit_reason}")
                    success, closed_price = exchange.close_position(
                        position, exit_reason, current_price
                    )
                    if success:
                        pnl = risk_manager.calculate_pnl(position, closed_price)
                        circuit_breaker.record_trade(pnl)
                        logger.info(
                            f"Posição fechada | Entrada: ${position['entry_price']:,.2f} | "
                            f"Saída: ${closed_price:,.2f} | PnL: ${pnl:,.4f} | "
                            f"Razão: {exit_reason}"
                        )
                        position = risk_manager.reset_position()
                    else:
                        logger.error("Falha ao fechar posição. Tentará no próximo ciclo.")

            # --- 4.5. Verifica Sinal de Entrada (apenas se sem posição aberta) ---
            elif not position["active"]:
                signal = strategy.get_entry_signal(ohlcv_df)
                logger.info(f"Sinal de entrada: {signal}")

                if signal == "BUY":
                    # Busca saldo disponível
                    balance = exchange.fetch_balance()
                    if balance is None:
                        logger.error("Não foi possível obter saldo. Pulando ciclo.")
                        time.sleep(config.LOOP_INTERVAL_SECONDS)
                        continue

                    logger.info(f"Saldo disponível: ${balance:,.2f} USDT")

                    # Calcula tamanho da posição (Position Sizing)
                    quantity, allocated_usdt = risk_manager.calculate_position_size(
                        balance, current_price
                    )

                    if quantity is None or quantity <= 0:
                        logger.warning("Saldo insuficiente para abrir posição.")
                    else:
                        logger.info(
                            f"Abrindo posição | Qtd: {quantity:.6f} BTC | "
                            f"Capital alocado: ${allocated_usdt:,.2f} USDT"
                        )
                        # Envia ordem de compra
                        order = exchange.place_buy_order(quantity, current_price)
                        if order:
                            filled_price = order.get("average") or current_price
                            sl = risk_manager.calc_stop_loss(filled_price)
                            tp = risk_manager.calc_take_profit(filled_price)
                            position = {
                                "active": True,
                                "entry_price": filled_price,
                                "quantity": quantity,
                                "stop_loss": sl,
                                "take_profit": tp,
                                "order_id": order.get("id"),
                                "entry_time": datetime.utcnow().isoformat(),
                            }
                            logger.info(
                                f"Posição aberta! | Entrada: ${filled_price:,.2f} | "
                                f"SL: ${sl:,.2f} (-{config.STOP_LOSS_PCT*100:.1f}%) | "
                                f"TP: ${tp:,.2f} (+{config.TAKE_PROFIT_PCT*100:.1f}%)"
                            )
                        else:
                            logger.error("Falha ao colocar ordem de compra.")

            # --- 4.6. Log de Status do Balance ---
            balance_log = exchange.fetch_balance()
            if balance_log:
                circuit_breaker.update_balance(balance_log)
                logger.info(f"Balance USDT atual: ${balance_log:,.2f}")

        except KeyboardInterrupt:
            logger.info("Interrupção manual detectada (Ctrl+C). Encerrando bot...")
            sys.exit(0)

        except Exception as e:
            # Captura genérica para não derrubar o loop
            logger.error(f"Erro inesperado no loop principal: {type(e).__name__}: {e}",
                         exc_info=True)
            logger.info(f"Aguardando {config.ERROR_RETRY_SECONDS}s antes de reintentar...")
            time.sleep(config.ERROR_RETRY_SECONDS)
            continue

        # --- 4.7. Aguarda próximo ciclo ---
        logger.info(f"Ciclo completo. Próxima verificação em {config.LOOP_INTERVAL_SECONDS}s...")
        logger.info("-" * 60)
        time.sleep(config.LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
