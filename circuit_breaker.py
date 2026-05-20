"""
circuit_breaker.py
------------------
Módulo de Circuit Breaker Diário.

Protege contra perdas catastróficas ao encerrar todas as operações
automaticamente quando as perdas acumuladas do dia atingem um limite
percentual do saldo inicial do dia (padrão: 5%).

Lógica:
  - Registra o saldo inicial no início de cada dia (UTC).
  - Acumula PnL de cada trade fechado.
  - Se (saldo_inicial - saldo_atual) / saldo_inicial >= DAILY_LOSS_LIMIT_PCT:
      → is_triggered() retorna True
      → O loop principal para de operar

  - Reset automático à meia-noite UTC.
"""

from datetime import datetime, timezone, timedelta
from config import Config


class CircuitBreaker:
    """
    Monitora perdas diárias e bloqueia novas operações se o limite for atingido.
    """

    def __init__(self, config: Config, logger):
        self.config = config
        self.logger = logger

        # Inicializa o estado para o dia atual
        self._reset_daily_state()

    # ------------------------------------------------------------------
    # Estado Diário
    # ------------------------------------------------------------------

    def _reset_daily_state(self):
        """
        Reinicia o estado do circuit breaker para o novo dia.
        """
        self._day = self._current_day()
        self._daily_start_balance: float = 0.0   # Saldo ao iniciar o dia
        self._daily_pnl: float = 0.0              # PnL acumulado do dia
        self._triggered: bool = False
        self.logger.info(
            f"Circuit Breaker reiniciado para o dia {self._day.isoformat()}"
        )

    def _current_day(self) -> datetime:
        """Retorna a data atual em UTC (apenas a data, sem hora)."""
        return datetime.now(timezone.utc).date()

    def _check_day_rollover(self):
        """
        Verifica se virou o dia (UTC) e faz reset se necessário.
        """
        today = self._current_day()
        if today != self._day:
            self.logger.info(f"Novo dia detectado ({today}). Resetando Circuit Breaker...")
            self._reset_daily_state()

    # ------------------------------------------------------------------
    # Interface Pública
    # ------------------------------------------------------------------

    def update_balance(self, current_balance: float):
        """
        Atualiza o saldo atual e define o saldo inicial do dia
        se ainda não foi definido.

        Deve ser chamado a cada ciclo do loop principal.

        Args:
            current_balance: Saldo livre em USDT.
        """
        self._check_day_rollover()

        if self._daily_start_balance == 0.0 and current_balance > 0:
            self._daily_start_balance = current_balance
            self.logger.info(
                f"Saldo inicial do dia registrado: ${self._daily_start_balance:,.2f} USDT"
            )

    def record_trade(self, pnl: float):
        """
        Registra o PnL de uma operação concluída e verifica o limite diário.

        Args:
            pnl: Lucro ou prejuízo da operação em USDT.
        """
        self._check_day_rollover()
        self._daily_pnl += pnl

        pnl_pct = (
            (self._daily_pnl / self._daily_start_balance * 100)
            if self._daily_start_balance > 0
            else 0
        )

        self.logger.info(
            f"Trade registrado | PnL operação: ${pnl:+.4f} | "
            f"PnL do dia: ${self._daily_pnl:+.4f} ({pnl_pct:+.2f}%)"
        )

        # Verifica se o limite de perda diária foi atingido
        if (
            self._daily_start_balance > 0
            and self._daily_pnl < 0
            and abs(self._daily_pnl) / self._daily_start_balance >= self.config.DAILY_LOSS_LIMIT_PCT
        ):
            self._triggered = True
            self.logger.critical(
                f"⛔ CIRCUIT BREAKER ATIVADO | "
                f"Perda diária: ${abs(self._daily_pnl):,.4f} "
                f"({abs(pnl_pct):.2f}%) >= limite de "
                f"{self.config.DAILY_LOSS_LIMIT_PCT*100:.0f}%. "
                f"Operações suspensas pelo restante do dia."
            )

    def is_triggered(self) -> bool:
        """
        Retorna True se o circuit breaker estiver ativo (bot deve parar).
        Verifica automaticamente o rollover de dia antes de responder.
        """
        self._check_day_rollover()
        return self._triggered

    def seconds_until_reset(self) -> float:
        """
        Retorna o número de segundos até a meia-noite UTC
        (quando o circuit breaker será resetado).
        """
        now = datetime.now(timezone.utc)
        tomorrow = datetime.combine(
            now.date() + timedelta(days=1),
            datetime.min.time(),
            tzinfo=timezone.utc
        )
        return (tomorrow - now).total_seconds()

    # ------------------------------------------------------------------
    # Propriedades de Status (úteis para logging/monitoramento)
    # ------------------------------------------------------------------

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def daily_start_balance(self) -> float:
        return self._daily_start_balance

    @property
    def daily_loss_pct(self) -> float:
        if self._daily_start_balance <= 0:
            return 0.0
        return self._daily_pnl / self._daily_start_balance * 100
