"""
config.py
---------
Carrega todas as configurações do bot a partir de variáveis de ambiente (.env).
NUNCA inclua chaves de API diretamente no código-fonte.
"""

import os
from dotenv import load_dotenv

# Carrega o arquivo .env da raiz do projeto
load_dotenv()


class Config:
    """
    Centraliza todas as configurações do bot.
    Valores padrão seguros são definidos inline; variáveis sensíveis
    vêm EXCLUSIVAMENTE do arquivo .env.
    """

    # ------------------------------------------------------------------
    # Credenciais da Exchange (OBRIGATÓRIO no .env)
    # ------------------------------------------------------------------
    API_KEY: str = os.getenv("API_KEY", "")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # ------------------------------------------------------------------
    # Configurações da Exchange
    # ------------------------------------------------------------------
    EXCHANGE_ID: str = os.getenv("EXCHANGE_ID", "binance")
    USE_TESTNET: bool = os.getenv("USE_TESTNET", "true").lower() == "true"
    SYMBOL: str = os.getenv("SYMBOL", "BTC/USDT")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "15m")   # 5m, 15m, 1h, 4h

    # Quantas velas buscar (mínimo 200 para a SMA200 ser válida)
    OHLCV_LIMIT: int = int(os.getenv("OHLCV_LIMIT", "300"))

    # ------------------------------------------------------------------
    # Parâmetros da Estratégia
    # ------------------------------------------------------------------
    RSI_PERIOD: int = int(os.getenv("RSI_PERIOD", "14"))
    RSI_OVERSOLD: float = float(os.getenv("RSI_OVERSOLD", "30"))    # Sinal de compra
    RSI_OVERBOUGHT: float = float(os.getenv("RSI_OVERBOUGHT", "70")) # Sinal de venda
    SMA_PERIOD: int = int(os.getenv("SMA_PERIOD", "200"))

    # ------------------------------------------------------------------
    # Gestão de Risco (Risco/Retorno 2:1)
    # ------------------------------------------------------------------
    # Máximo do saldo alocado por operação
    POSITION_SIZE_PCT: float = float(os.getenv("POSITION_SIZE_PCT", "0.05"))  # 5%

    # Stop Loss: 2.5% abaixo do preço de entrada
    STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", "0.025"))

    # Take Profit: 5% acima do preço de entrada (ratio 2:1)
    TAKE_PROFIT_PCT: float = float(os.getenv("TAKE_PROFIT_PCT", "0.05"))

    # ------------------------------------------------------------------
    # Circuit Breaker Diário
    # ------------------------------------------------------------------
    # Se as perdas do dia atingirem X% do saldo inicial do dia, para tudo
    DAILY_LOSS_LIMIT_PCT: float = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.05"))  # 5%

    # ------------------------------------------------------------------
    # Configurações de Timing
    # ------------------------------------------------------------------
    LOOP_INTERVAL_SECONDS: int = int(os.getenv("LOOP_INTERVAL_SECONDS", "900"))  # 15 min
    ERROR_RETRY_SECONDS: int = int(os.getenv("ERROR_RETRY_SECONDS", "60"))
    API_TIMEOUT_MS: int = int(os.getenv("API_TIMEOUT_MS", "30000"))  # 30s

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/trading_bot.log")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self) -> None:
        """
        Valida que as configurações críticas estão presentes.
        Lança ValueError se algo estiver faltando.
        """
        if not self.API_KEY or not self.SECRET_KEY:
            raise ValueError(
                "API_KEY e SECRET_KEY são obrigatórias. "
                "Verifique o arquivo .env na raiz do projeto."
            )
        if self.STOP_LOSS_PCT <= 0 or self.TAKE_PROFIT_PCT <= 0:
            raise ValueError("STOP_LOSS_PCT e TAKE_PROFIT_PCT devem ser > 0.")
        if self.POSITION_SIZE_PCT <= 0 or self.POSITION_SIZE_PCT > 0.20:
            raise ValueError("POSITION_SIZE_PCT deve estar entre 0 e 20%.")
        if self.TAKE_PROFIT_PCT < self.STOP_LOSS_PCT:
            raise ValueError(
                f"Take Profit ({self.TAKE_PROFIT_PCT}) deve ser >= Stop Loss "
                f"({self.STOP_LOSS_PCT}). Mantenha ratio >= 2:1."
            )
