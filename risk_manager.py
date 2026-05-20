"""
risk_manager.py
---------------
Módulo de Gestão de Risco.

Responsabilidades:
  - Position Sizing: limita cada operação a X% do saldo disponível
  - Stop Loss: saída imediata se preço cair Y% do preço de entrada
  - Take Profit: realização de lucro se preço subir Z%
  - Saída por RSI em sobrecompra
  - Cálculo de PnL (Profit and Loss)

A lógica de risco é completamente separada da lógica de mercado,
permitindo alterar parâmetros sem tocar na estratégia.
"""

from typing import Optional, Tuple

from config import Config


class RiskManager:
    """
    Centraliza todas as decisões de gestão de risco do bot.
    """

    def __init__(self, config: Config, logger):
        self.config = config
        self.logger = logger

    # ------------------------------------------------------------------
    # Position Sizing
    # ------------------------------------------------------------------

    def calculate_position_size(
        self, available_balance: float, current_price: float
    ) -> Tuple[Optional[float], float]:
        """
        Calcula a quantidade de BTC a comprar baseada no saldo disponível
        e no limite de alocação por operação (POSITION_SIZE_PCT).

        Exemplo:
            Saldo: $10.000 USDT | POSITION_SIZE_PCT: 5%
            Capital alocado: $500 USDT
            Quantidade BTC: 500 / preço_atual

        Args:
            available_balance: Saldo livre em USDT.
            current_price: Preço atual do BTC em USDT.

        Returns:
            (quantidade_btc, usdt_alocado) ou (None, 0) se insuficiente.
        """
        if available_balance <= 0 or current_price <= 0:
            return None, 0.0

        allocated_usdt = available_balance * self.config.POSITION_SIZE_PCT
        quantity = allocated_usdt / current_price

        # Binance exige mínimo de $10 USDT por ordem
        MIN_ORDER_USDT = 10.0
        if allocated_usdt < MIN_ORDER_USDT:
            self.logger.warning(
                f"Capital alocado (${allocated_usdt:.2f}) abaixo do mínimo "
                f"da exchange (${MIN_ORDER_USDT})."
            )
            return None, 0.0

        self.logger.debug(
            f"Position sizing | Saldo: ${available_balance:,.2f} | "
            f"Alocado ({self.config.POSITION_SIZE_PCT*100:.0f}%): "
            f"${allocated_usdt:,.2f} | Qtd: {quantity:.6f} BTC"
        )

        return round(quantity, 6), round(allocated_usdt, 2)

    # ------------------------------------------------------------------
    # Níveis de Stop Loss e Take Profit
    # ------------------------------------------------------------------

    def calc_stop_loss(self, entry_price: float) -> float:
        """
        Calcula o nível de Stop Loss.
        SL = entry_price * (1 - STOP_LOSS_PCT)

        Exemplo com STOP_LOSS_PCT=2.5%:
            Entrada: $50.000 → SL: $48.750
        """
        return round(entry_price * (1 - self.config.STOP_LOSS_PCT), 2)

    def calc_take_profit(self, entry_price: float) -> float:
        """
        Calcula o nível de Take Profit.
        TP = entry_price * (1 + TAKE_PROFIT_PCT)

        Exemplo com TAKE_PROFIT_PCT=5% (ratio 2:1 com SL de 2.5%):
            Entrada: $50.000 → TP: $52.500
        """
        return round(entry_price * (1 + self.config.TAKE_PROFIT_PCT), 2)

    # ------------------------------------------------------------------
    # Verificação de Condições de Saída
    # ------------------------------------------------------------------

    def check_exit_conditions(
        self, current_price: float, position: dict, rsi: float
    ) -> Optional[str]:
        """
        Verifica se alguma condição de saída foi atingida.

        Ordem de prioridade:
          1. Stop Loss (proteção máxima — verificado primeiro)
          2. Take Profit (realização de lucro)
          3. RSI em sobrecompra (saída técnica)

        Args:
            current_price: Preço atual do BTC.
            position: Dicionário com dados da posição ativa.
            rsi: Valor atual do RSI.

        Returns:
            String descrevendo o motivo de saída, ou None se manter.
        """
        entry = position["entry_price"]
        sl = position["stop_loss"]
        tp = position["take_profit"]

        # Calcula variação percentual
        pct_change = (current_price - entry) / entry * 100

        self.logger.debug(
            f"Exit check | Entrada: ${entry:,.2f} | Atual: ${current_price:,.2f} | "
            f"PnL: {pct_change:+.2f}% | SL: ${sl:,.2f} | TP: ${tp:,.2f} | RSI: {rsi:.2f}"
        )

        # 1. Stop Loss
        if current_price <= sl:
            self.logger.warning(
                f"STOP LOSS ATIVADO | Preço ${current_price:,.2f} <= SL ${sl:,.2f} | "
                f"Perda: {pct_change:+.2f}%"
            )
            return "STOP_LOSS"

        # 2. Take Profit
        if current_price >= tp:
            self.logger.info(
                f"TAKE PROFIT ATINGIDO | Preço ${current_price:,.2f} >= TP ${tp:,.2f} | "
                f"Lucro: {pct_change:+.2f}%"
            )
            return "TAKE_PROFIT"

        # 3. Saída Técnica por RSI em sobrecompra
        if rsi >= self.config.RSI_OVERBOUGHT:
            self.logger.info(
                f"RSI OVERBOUGHT | RSI {rsi:.2f} >= {self.config.RSI_OVERBOUGHT} | "
                f"PnL: {pct_change:+.2f}%"
            )
            return "RSI_OVERBOUGHT"

        return None  # Mantém posição

    # ------------------------------------------------------------------
    # PnL e Reset
    # ------------------------------------------------------------------

    def calculate_pnl(self, position: dict, exit_price: float) -> float:
        """
        Calcula o lucro/prejuízo da operação em USDT.

        PnL = (preço_saída - preço_entrada) * quantidade

        Args:
            position: Dados da posição fechada.
            exit_price: Preço de saída.

        Returns:
            PnL em USDT (positivo = lucro, negativo = prejuízo).
        """
        pnl = (exit_price - position["entry_price"]) * position["quantity"]
        return round(pnl, 4)

    def reset_position(self) -> dict:
        """
        Retorna um dicionário de posição vazio (sem operação ativa).
        """
        return {
            "active": False,
            "entry_price": None,
            "quantity": None,
            "stop_loss": None,
            "take_profit": None,
            "order_id": None,
            "entry_time": None,
        }
