# 🤖 BTC/USDT Algorithmic Trading Bot

Bot de trading automatizado para Bitcoin usando **RSI(14) + SMA(200)** com gestão de risco estrita, circuit breaker diário e suporte a Testnet/Paper Trading.

> ⚠️ **AVISO**: Este software é educacional. Trading de criptomoedas envolve risco de perda total do capital. Sempre teste exaustivamente no Testnet antes de usar dinheiro real.

---

## 📁 Estrutura do Projeto

```
btc_trading_bot/
│
├── main.py              # Loop principal — orquestra todos os módulos
├── config.py            # Configurações centralizadas (lê do .env)
├── exchange_client.py   # Camada de API: conexão, ordens, dados OHLCV
├── strategy.py          # Estratégia: RSI + SMA200, geração de sinais
├── risk_manager.py      # Gestão de risco: position sizing, SL, TP, PnL
├── circuit_breaker.py   # Proteção de perdas diárias
├── logger_setup.py      # Configuração de logs (console + arquivo rotativo)
│
├── .env.example         # Template de configuração (copie para .env)
├── .gitignore           # Protege .env e logs de commit acidental
├── requirements.txt     # Dependências Python
└── logs/
    └── trading_bot.log  # Gerado automaticamente
```

---

## ⚙️ Arquitetura e Fluxo de Execução

```
main.py (loop a cada 15min)
│
├── CircuitBreaker.is_triggered()?
│   └── Se sim: aguarda até meia-noite UTC e reinicia
│
├── ExchangeClient.fetch_ohlcv()         → dados de mercado
├── Strategy.calculate_indicators()      → RSI(14) + SMA(200)
│
├── [Posição ativa?]
│   ├── RiskManager.check_exit_conditions()
│   │   ├── Stop Loss (-2.5%)   → VENDE imediatamente
│   │   ├── Take Profit (+5.0%) → VENDE e realiza lucro
│   │   └── RSI >= 70           → VENDE (sobrecompra técnica)
│   └── ExchangeClient.close_position() → ordem SELL MARKET
│
└── [Sem posição]
    ├── Strategy.get_entry_signal()
    │   └── RSI cruzou < 30 AND preço > SMA200 → BUY
    ├── RiskManager.calculate_position_size()  → 5% do saldo
    └── ExchangeClient.place_buy_order()       → ordem BUY MARKET
```

---

## 🚀 Configuração e Execução

### 1. Clonar e instalar dependências

```bash
git clone <seu-repositorio>
cd btc_trading_bot
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 2. Configurar o arquivo .env

```bash
cp .env.example .env
```

Edite o `.env` com suas credenciais e parâmetros. **Nunca commite o `.env`.**

### 3. Configurar Testnet da Binance (Paper Trading)

**Passo a passo:**

1. Acesse [testnet.binance.vision](https://testnet.binance.vision)
2. Faça login com sua conta GitHub
3. Clique em **"Generate HMAC_SHA256 Key"**
4. Copie a `API Key` e `Secret Key` geradas
5. Cole no seu `.env`:
   ```
   API_KEY=sua_testnet_api_key
   SECRET_KEY=sua_testnet_secret_key
   USE_TESTNET=true
   ```
6. A Testnet credita automaticamente saldo de papel (BTC + USDT)

> **Nota Testnet**: O `ccxt` usa `exchange.set_sandbox_mode(True)` para redirecionar automaticamente as chamadas para os endpoints da Testnet da Binance (`testnet.binance.vision`).

### 4. Executar o bot

```bash
python main.py
```

Você verá logs no console e em `logs/trading_bot.log`:

```
[2024-01-15 14:00:00 UTC] [INFO] [main] BTC/USDT Trading Bot Iniciado
[2024-01-15 14:00:01 UTC] [INFO] [exchange_client] Conectado à BINANCE | Par: BTC/USDT | Testnet: True
[2024-01-15 14:00:02 UTC] [INFO] [main] Preço atual BTC/USDT: $42,350.00
[2024-01-15 14:00:02 UTC] [INFO] [main] Indicadores | RSI(14): 28.43 | SMA(200): $41,200.00
[2024-01-15 14:00:02 UTC] [INFO] [strategy] BUY SIGNAL | RSI cruzou abaixo de 30 (31.2 → 28.4) | ...
```

---

## 📊 Estratégia em Detalhe

### Sinal de Compra (RSI + SMA200)

| Condição | Valor | Explicação |
|----------|-------|------------|
| RSI(14) cruzou abaixo de | 30 | Ativo em zona de sobrevenda |
| Preço atual > SMA(200) | — | Tendência maior é de alta |

O cruzamento (e não apenas "RSI < 30") evita entrar em tendências de queda prolongada onde o RSI pode ficar abaixo de 30 por semanas.

### Sinais de Saída

| Condição | Prioridade | Tipo |
|----------|------------|------|
| Preço <= Stop Loss (-2.5%) | 🔴 Alta | Proteção de capital |
| Preço >= Take Profit (+5.0%) | 🟢 Alta | Realização de lucro |
| RSI(14) >= 70 | 🟡 Técnica | Sobrecompra |

### Risk/Reward Ratio: **2:1**

```
Stop Loss:   2.5% → Risco $250 em uma posição de $10.000
Take Profit: 5.0% → Retorno $500
Ratio:       500/250 = 2:1 ✅
```

---

## 🛡️ Gestão de Risco — Resumo

| Proteção | Valor | Descrição |
|----------|-------|-----------|
| Position Sizing | 5% | Máximo do saldo por trade |
| Stop Loss | 2.5% | Saída automática por perda |
| Take Profit | 5.0% | Realização automática de lucro |
| Circuit Breaker | 5%/dia | Encerra operações se perdas diárias atingirem 5% |
| Anti-duplicação | — | Verifica ordens abertas antes de cada compra |
| Retry com verificação | 3x | Em timeouts, verifica se ordem foi criada antes de retentar |

---

## 🔧 Explicação das Principais Funções

### `strategy._calc_rsi()` — Cálculo do RSI

O RSI mede a velocidade e magnitude das variações de preço:

```python
delta = series.diff()                          # Variação entre velas
gain  = delta.clip(lower=0)                    # Apenas altas
loss  = -delta.clip(upper=0)                   # Apenas quedas

# EMA de Wilder (alpha = 1/period) — mais suave que SMA simples
avg_gain = gain.ewm(com=period-1, adjust=False).mean()
avg_loss = loss.ewm(com=period-1, adjust=False).mean()

rs  = avg_gain / avg_loss                      # Força relativa
rsi = 100 - (100 / (1 + rs))                  # Normaliza 0–100
```

RSI < 30 → sobrevenda (mercado "cansado de cair" → potencial reversão)
RSI > 70 → sobrecompra (mercado "cansado de subir" → potencial correção)

### `exchange_client.place_buy_order()` — Envio de Ordem com Anti-duplicação

```python
# 1. Verifica ordens abertas ANTES de enviar nova ordem
if self._has_open_orders():
    return None  # Bloqueia duplicação

# 2. Tenta enviar ordem (até 3 tentativas em timeout)
# 3. Em caso de timeout: busca ordem recente antes de retentar
existing = self._check_recent_order("buy")
if existing:
    return existing  # Retorna a ordem que foi criada mesmo com timeout
```

### `risk_manager.check_exit_conditions()` — Stop Loss e Take Profit

```python
# Verifica na ordem: SL > TP > RSI (mais crítico primeiro)
if current_price <= position["stop_loss"]:
    return "STOP_LOSS"   # Sai imediatamente

if current_price >= position["take_profit"]:
    return "TAKE_PROFIT" # Realiza lucro

if rsi >= config.RSI_OVERBOUGHT:
    return "RSI_OVERBOUGHT" # Saída técnica
```

### `circuit_breaker.record_trade()` — Limite de Perda Diária

```python
self._daily_pnl += pnl  # Acumula PnL do dia

loss_ratio = abs(self._daily_pnl) / self._daily_start_balance
if loss_ratio >= DAILY_LOSS_LIMIT_PCT:
    self._triggered = True  # Para todas as operações
```

---

## 🧪 Testando sem Dinheiro Real

### Opção A: Binance Testnet (recomendado)
- URL: [testnet.binance.vision](https://testnet.binance.vision)
- Saldo virtual disponível automaticamente
- API idêntica à produção
- Configure `USE_TESTNET=true` no `.env`

### Opção B: Paper Trading Local (sem exchange)
Para backtesting antes de usar a Testnet, você pode substituir
temporariamente o `ExchangeClient` por uma versão simulada que lê
dados históricos de um CSV e simula execução de ordens.

---

## 📈 Recomendações antes de ir para Produção

- [ ] Rodar mínimo **30 dias** na Testnet com logs completos
- [ ] Validar que o Circuit Breaker reseta à meia-noite UTC
- [ ] Testar comportamento com timeout forçado (desligar internet por 5s)
- [ ] Confirmar que não há ordens duplicadas após reconexão
- [ ] Ajustar `TIMEFRAME` e `LOOP_INTERVAL_SECONDS` para o mesmo período
- [ ] Revisar `POSITION_SIZE_PCT` conforme seu apetite de risco real
- [ ] Configurar alertas externos (Telegram, e-mail) para logs CRITICAL

---

## ⚖️ Disclaimer

Este projeto é fornecido exclusivamente para fins **educacionais e de pesquisa**. Não constitui aconselhamento financeiro. O autor não se responsabiliza por perdas financeiras decorrentes do uso deste software. **Nunca invista mais do que pode perder.**
