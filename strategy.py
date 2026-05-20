"""
strategy.py
-----------
Módulo de Estratégia de Trading.

Implementa o cálculo dos indicadores técnicos e a geração de sinais:

  SINAL DE COMPRA:
    - RSI(14) cruza ABAIXO de 30 (sobrevenda)
    - E preço atual está ACIMA da SMA(200) (tendência de alta confirmada)

  SINAL DE VENDA:
    - RSI(14) cruza ACIMA de 70 (sobrecompra)
    (Saída por Stop Loss / Take Profit é gerenciada pelo RiskManager)

Cálculo manual do RSI para evitar dependências externas desnecessárias.
Compatível com pandas >= 1.5.
"""

import numpy as np
import pandas as pd
from typing import Literal

from config import Config


SignalType = Literal["BUY", "SELL", "HOLD"]


class TradingStrategy:
    """
    Calcula indicadores técnicos e gera sinais de entrada/saída.
    """

    def __init__(self, config: Config, logger):
        self.config = config
        self.logger = logger

    # ------------------------------------------------------------------
    # Cálculo de Indicadores
    # ------------------------------------------------------------------

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Adiciona colunas de indicadores ao DataFrame de velas.

        Indicadores calculados:
          - rsi:    RSI de N períodos (padrão 14)
          - sma200: Média Móvel Simples de 200 períodos

        Args:
            df: DataFrame OHLCV com coluna "close".

        Returns:
            DataFrame com colunas extras: rsi, sma200.
        """
        df = df.copy()
        df["rsi"] = self._calc_rsi(df["close"], self.config.RSI_PERIOD)
        df["sma200"] = df["close"].rolling(window=self.config.SMA_PERIOD).mean()
        return df

    def _calc_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        """
        Calcula o RSI (Relative Strength Index) usando o método de Wilder
        (Exponential Moving Average com alpha = 1/period).

        Fórmula:
            delta = diferença de preço entre períodos consecutivos
            gain  = média exponencial dos ganhos (variações positivas)
            loss  = média exponencial das perdas (variações negativas, valor absoluto)
            RS    = gain / loss
            RSI   = 100 - (100 / (1 + RS))

        Args:
            series: Série de preços de fechamento.
            period: Período do RSI (padrão: 14).

        Returns:
            Série pandas com valores do RSI (0–100).
        """
        delta = series.diff()

        # Separa ganhos e perdas
        gain = delta.clip(lower=0)   # Zera valores negativos
        loss = -delta.clip(upper=0)  # Zera valores positivos, inverte sinal

        # EMA de Wilder: alpha = 1/period (equivalente ao com_mean com adjust=False)
        avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

        # Evita divisão por zero
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        return rsi.fillna(50)  # RSI = 50 enquanto dados insuficientes

    # ------------------------------------------------------------------
    # Geração de Sinais
    # ------------------------------------------------------------------

    def get_entry_signal(self, df: pd.DataFrame) -> SignalType:
        """
        Avalia as últimas duas velas para detectar cruzamentos de RSI.

        Lógica de cruzamento (para evitar falsos positivos):
          - Compra: RSI estava ACIMA de 30 e agora CAIU ABAIXO de 30
                    (cruzamento de baixa da linha de sobrevenda)
          - Para confirmar tendência: preço atual > SMA(200)

        Usar cruzamento em vez de apenas "RSI < 30" evita entrar em
        tendências de queda prolongada onde o RSI fica indefinidamente
        abaixo de 30.

        Returns:
            "BUY", "SELL" ou "HOLD"
        """
        if len(df) < self.config.SMA_PERIOD + 2:
            self.logger.warning(
                f"Dados insuficientes para calcular sinais "
                f"(necessário >= {self.config.SMA_PERIOD + 2} velas)."
            )
            return "HOLD"

        # Últimas duas velas
        prev_rsi = df["rsi"].iloc[-2]
        curr_rsi = df["rsi"].iloc[-1]
        curr_price = df["close"].iloc[-1]
        sma200 = df["sma200"].iloc[-1]

        # Verifica se SMA200 é válida
        if pd.isna(sma200):
            self.logger.warning("SMA(200) ainda não calculada (dados insuficientes).")
            return "HOLD"

        self.logger.debug(
            f"Signal check | prev_RSI: {prev_rsi:.2f} | curr_RSI: {curr_rsi:.2f} | "
            f"Price: ${curr_price:,.2f} | SMA200: ${sma200:,.2f}"
        )

        # --- SINAL DE COMPRA ---
        rsi_crossed_oversold = (
            prev_rsi >= self.config.RSI_OVERSOLD
            and curr_rsi < self.config.RSI_OVERSOLD
        )
        price_above_sma = curr_price > sma200

        if rsi_crossed_oversold and price_above_sma:
            self.logger.info(
                f"BUY SIGNAL | RSI cruzou abaixo de {self.config.RSI_OVERSOLD} "
                f"({prev_rsi:.2f} → {curr_rsi:.2f}) | "
                f"Preço ${curr_price:,.2f} > SMA200 ${sma200:,.2f}"
            )
            return "BUY"

        # Log de motivo para não comprar (útil para debugging)
        if curr_rsi < self.config.RSI_OVERSOLD and not price_above_sma:
            self.logger.debug(
                f"RSI em sobrevenda mas preço ABAIXO da SMA200 "
                f"(${curr_price:,.2f} < ${sma200:,.2f}). Tendência baixista. HOLD."
            )

        return "HOLD"
