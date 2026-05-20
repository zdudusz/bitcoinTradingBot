"""
exchange_client.py
------------------
Camada de abstração para todas as chamadas à Exchange via CCXT.
Isola a lógica de rede do restante do bot.

Responsabilidades:
  - Conexão e autenticação com a Exchange (Binance Testnet ou real)
  - Busca de velas OHLCV
  - Envio e consulta de ordens
  - Verificação de status de ordens pendentes (anti-duplicação)
"""

import time
import ccxt
import pandas as pd
from typing import Optional, Tuple, Dict, Any

from config import Config


class ExchangeClient:
    """
    Wrapper sobre o CCXT para a Exchange configurada.
    Todos os métodos possuem tratamento de exceções específico para
    timeout, autenticação e erros de rede.
    """

    # Número máximo de tentativas em caso de falha de rede/timeout
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # segundos entre tentativas

    def __init__(self, config: Config, logger):
        self.config = config
        self.logger = logger
        self.exchange = self._initialize_exchange()

    # ------------------------------------------------------------------
    # Inicialização
    # ------------------------------------------------------------------

    def _initialize_exchange(self) -> ccxt.Exchange:
        """
        Cria e configura a instância da Exchange via CCXT.
        Ativa o modo Testnet se USE_TESTNET=true.
        """
        exchange_class = getattr(ccxt, self.config.EXCHANGE_ID)
        exchange = exchange_class({
            "apiKey": self.config.API_KEY,
            "secret": self.config.SECRET_KEY,
            "timeout": self.config.API_TIMEOUT_MS,
            "enableRateLimit": True,  # Respeita os rate limits da exchange
            "options": {
                "defaultType": "spot",
            },
        })

        if self.config.USE_TESTNET:
            self.logger.info("Modo TESTNET ativado.")
            # Binance Testnet URLs
            exchange.set_sandbox_mode(True)

        # Valida conectividade
        try:
            exchange.load_markets()
            self.logger.info(
                f"Conectado à {self.config.EXCHANGE_ID.upper()} | "
                f"Par: {self.config.SYMBOL} | Testnet: {self.config.USE_TESTNET}"
            )
        except ccxt.AuthenticationError as e:
            self.logger.critical(f"Falha de autenticação: {e}. Verifique API_KEY e SECRET_KEY.")
            raise
        except Exception as e:
            self.logger.critical(f"Erro ao conectar à exchange: {e}")
            raise

        return exchange

    # ------------------------------------------------------------------
    # Dados de Mercado
    # ------------------------------------------------------------------

    def fetch_ohlcv(self) -> Optional[pd.DataFrame]:
        """
        Busca as velas OHLCV (Open/High/Low/Close/Volume) da exchange.

        Retorna um DataFrame pandas com colunas:
            timestamp, open, high, low, close, volume

        Implementa retry automático para falhas temporárias de rede.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                raw = self.exchange.fetch_ohlcv(
                    self.config.SYMBOL,
                    timeframe=self.config.TIMEFRAME,
                    limit=self.config.OHLCV_LIMIT
                )
                if not raw:
                    self.logger.warning("fetch_ohlcv retornou lista vazia.")
                    return None

                df = pd.DataFrame(
                    raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df.set_index("timestamp", inplace=True)
                df = df.astype(float)
                return df

            except ccxt.RequestTimeout as e:
                self.logger.warning(
                    f"Timeout ao buscar OHLCV (tentativa {attempt}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
                else:
                    self.logger.error("Máximo de tentativas atingido para fetch_ohlcv.")
                    return None

            except ccxt.NetworkError as e:
                self.logger.warning(f"Erro de rede (tentativa {attempt}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY * attempt)
                else:
                    return None

            except ccxt.ExchangeError as e:
                self.logger.error(f"Erro da exchange ao buscar OHLCV: {e}")
                return None

            except Exception as e:
                self.logger.error(f"Erro inesperado em fetch_ohlcv: {e}", exc_info=True)
                return None

    # ------------------------------------------------------------------
    # Saldo
    # ------------------------------------------------------------------

    def fetch_balance(self) -> Optional[float]:
        """
        Retorna o saldo livre (free) em USDT da conta.
        Retorna None em caso de erro.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                balance_data = self.exchange.fetch_balance()
                usdt_free = balance_data.get("USDT", {}).get("free", 0.0)
                return float(usdt_free)

            except ccxt.RequestTimeout as e:
                self.logger.warning(
                    f"Timeout ao buscar saldo (tentativa {attempt}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                else:
                    return None

            except Exception as e:
                self.logger.error(f"Erro ao buscar saldo: {type(e).__name__}: {e}")
                return None

    # ------------------------------------------------------------------
    # Ordens
    # ------------------------------------------------------------------

    def place_buy_order(
        self, quantity: float, current_price: float
    ) -> Optional[Dict[str, Any]]:
        """
        Envia uma ordem de compra a mercado.

        ANTI-DUPLICAÇÃO: Verifica se não há ordem pendente antes de enviar.

        Args:
            quantity: Quantidade de BTC a comprar.
            current_price: Preço atual (para logging).

        Returns:
            Dicionário com dados da ordem ou None em caso de falha.
        """
        # Verifica ordens abertas para evitar duplicação
        if self._has_open_orders():
            self.logger.warning(
                "Ordem aberta detectada. Ignorando novo sinal de compra "
                "para evitar duplicação."
            )
            return None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.logger.info(
                    f"Enviando ordem BUY MARKET | {quantity:.6f} BTC @ ~${current_price:,.2f}"
                )
                order = self.exchange.create_market_buy_order(
                    self.config.SYMBOL, quantity
                )
                self.logger.info(
                    f"Ordem BUY executada | ID: {order.get('id')} | "
                    f"Status: {order.get('status')} | "
                    f"Filled: {order.get('filled', 0):.6f} BTC @ "
                    f"${order.get('average', current_price):,.2f}"
                )
                return order

            except ccxt.InsufficientFunds as e:
                self.logger.error(f"Saldo insuficiente para ordem de compra: {e}")
                return None

            except ccxt.RequestTimeout as e:
                self.logger.warning(
                    f"Timeout ao colocar ordem BUY (tentativa {attempt}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES:
                    # Verifica se a ordem foi criada apesar do timeout
                    self.logger.info("Verificando se ordem foi criada apesar do timeout...")
                    time.sleep(self.RETRY_DELAY)
                    existing = self._check_recent_order("buy")
                    if existing:
                        self.logger.info(
                            f"Ordem encontrada pós-timeout | ID: {existing.get('id')}"
                        )
                        return existing
                else:
                    self.logger.error("Máximo de tentativas atingido para place_buy_order.")
                    return None

            except ccxt.ExchangeError as e:
                self.logger.error(f"Erro da exchange ao comprar: {e}")
                return None

            except Exception as e:
                self.logger.error(
                    f"Erro inesperado em place_buy_order: {type(e).__name__}: {e}",
                    exc_info=True
                )
                return None

    def place_sell_order(
        self, quantity: float, current_price: float, reason: str
    ) -> Optional[Dict[str, Any]]:
        """
        Envia uma ordem de venda a mercado.

        Args:
            quantity: Quantidade de BTC a vender.
            current_price: Preço atual (para logging).
            reason: Motivo da venda (STOP_LOSS, TAKE_PROFIT, RSI_OVERBOUGHT).

        Returns:
            Dicionário com dados da ordem ou None em caso de falha.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.logger.info(
                    f"Enviando ordem SELL MARKET | {quantity:.6f} BTC @ "
                    f"~${current_price:,.2f} | Razão: {reason}"
                )
                order = self.exchange.create_market_sell_order(
                    self.config.SYMBOL, quantity
                )
                self.logger.info(
                    f"Ordem SELL executada | ID: {order.get('id')} | "
                    f"Status: {order.get('status')} | "
                    f"Filled: {order.get('filled', 0):.6f} BTC @ "
                    f"${order.get('average', current_price):,.2f}"
                )
                return order

            except ccxt.InsufficientFunds as e:
                self.logger.error(f"Saldo BTC insuficiente para venda: {e}")
                return None

            except ccxt.RequestTimeout as e:
                self.logger.warning(
                    f"Timeout ao colocar ordem SELL (tentativa {attempt}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    existing = self._check_recent_order("sell")
                    if existing:
                        self.logger.info(
                            f"Ordem SELL encontrada pós-timeout | ID: {existing.get('id')}"
                        )
                        return existing
                else:
                    self.logger.error("Máximo de tentativas atingido para place_sell_order.")
                    return None

            except Exception as e:
                self.logger.error(
                    f"Erro inesperado em place_sell_order: {type(e).__name__}: {e}",
                    exc_info=True
                )
                return None

    def close_position(
        self, position: dict, reason: str, current_price: float
    ) -> Tuple[bool, float]:
        """
        Fecha a posição ativa enviando uma ordem de venda.

        Returns:
            (True, preço_de_saída) em sucesso, (False, 0) em falha.
        """
        order = self.place_sell_order(position["quantity"], current_price, reason)
        if order:
            filled_price = order.get("average") or current_price
            return True, float(filled_price)
        return False, 0.0

    # ------------------------------------------------------------------
    # Helpers Internos
    # ------------------------------------------------------------------

    def _has_open_orders(self) -> bool:
        """
        Verifica se há ordens abertas no par configurado.
        Usado para evitar duplicação de ordens em caso de timeout.
        """
        try:
            open_orders = self.exchange.fetch_open_orders(self.config.SYMBOL)
            return len(open_orders) > 0
        except Exception as e:
            self.logger.warning(f"Não foi possível verificar ordens abertas: {e}")
            return False  # Em caso de dúvida, permite continuar

    def _check_recent_order(self, side: str) -> Optional[Dict[str, Any]]:
        """
        Busca a ordem mais recente do lado (buy/sell) especificado.
        Usado após timeouts para verificar se a ordem foi criada.

        Args:
            side: "buy" ou "sell"

        Returns:
            Dados da ordem mais recente ou None.
        """
        try:
            orders = self.exchange.fetch_orders(self.config.SYMBOL, limit=5)
            for order in reversed(orders):  # Mais recente primeiro
                if (
                    order.get("side") == side
                    and order.get("status") in ("closed", "filled", "partially_filled")
                ):
                    return order
            return None
        except Exception as e:
            self.logger.warning(f"Erro ao verificar ordens recentes: {e}")
            return None
