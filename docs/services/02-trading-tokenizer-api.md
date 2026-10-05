# Serviço 02: Trading Tokenizer API (`trading-tokenizer-api`)

## 1. Visão Geral e Arquitetura

O **Trading Tokenizer API** é o motor de alta performance responsável pela análise léxica em nível de sub-milissegundos (microsegundos), correspondência de gramáticas sintáticas e extração semântica de entidades financeiras (ativo, par OTC, direção, tempo de expiração, preço de entrada, Take-Profit, Stop-Loss e passos de Martingale).

Construído utilizando um núcleo nativo em **Rust** integrado a uma camada de serviço assíncrona, este serviço garante que sinais recebidos de fontes ruidosas (como canais do Telegram e salas de sinais VIP) sejam normalizados e estruturados antes de atingir os adaptadores de broker.

```
                  Raw Trading Message (Telegram / Chat / Webhook)
                                       │
                                       ▼
                   ┌───────────────────────────────────────┐
                   │        trading-tokenizer-api          │
                   │        (Porta Externa: 8002)          │
                   │ ───────────────────────────────────── │
                   │  1. Rust Lexer (Zero-Copy Slicing)    │
                   │  2. Token Flow (Spans de Bytes)       │
                   │  3. 48-Slot Matrix Grammar Matcher    │
                   │  4. Financial AST Entity Serializer   │
                   └──────────────────┬────────────────────┘
                                      │ Output Estruturado JSON
                                      ▼
                   ┌───────────────────────────────────────┐
                   │          quant-trading-api            │
                   │        (Despacho ao Broker)           │
                   └───────────────────────────────────────┘
```

---

## 2. Metadados do Serviço

| Atributo | Valor / Especificação |
| :--- | :--- |
| **Nome do Contêiner** | `trading-tokenizer-api` |
| **Imagem Base** | `trading-tokenizer-api:latest` |
| **Porta Mapeada** | `8002:8000` (TCP) |
| **Rede Docker** | `quant-network` (bridge) |
| **Tecnologias** | Rust (Lexer nativo) + PyO3 / FastAPI / ASGI |
| **Latência Típica de Análise** | **< 350 microsegundos (µs)** |
| **Healthcheck** | `GET /health` (`status: healthy`, `service: trading-tokenizer-api`) |

---

## 3. Principais Módulos e Responsabilidades

### 3.1. Laboratório de Tokenização Léxica (`/api/v1/tokens/tokenize`)
- **Extração Semântica com Spans:** Identifica e rotula cada palavra do sinal bruto com seus índices exatos de byte:
  - `SYMBOL`: Pares tradicionais (`EURUSD`, `GBPUSD`), cripto (`BTCUSDT`, `SOLUSDT`), commodities (`XAUUSD`) e binários OTC (`EURUSD_otc`, `AUDJPY-OTC`).
  - `ACTION`: Ordens de compra (`BUY`, `CALL`, `COMPRA`, `LONG`) e venda (`SELL`, `PUT`, `VENDA`, `SHORT`).
  - `PRICE_ENTRY`: Preços de entrada com precisão decimal arbitrária.
  - `EXPIRATION / TIMEFRAME`: Tempos de expiração de opções binárias (`M1`, `M5`, `15min`, `19:45`).
  - `TAKE_PROFIT (TP)` e `STOP_LOSS (SL)`: Alvos de ganho e proteção de capital.
  - `MARTINGALE (GALE)`: Passos de progressão (`GALE 1`, `GALE 2`, `SEM GALE`).

### 3.2. Matriz de Templates Gramaticais (`/api/v1/templates`)
- **Arquitetura 48-Slot Matrix (A1 a D12):**
  - **Grupo A (A1-A12):** Sinais de mercado tradicionais Forex / MT5 com múltiplos níveis de Take Profit e Stop Loss.
  - **Grupo B (B1-B12):** Sinais de opções binárias turbo (M1/M5) com horários e passos de Martingale.
  - **Grupo C (C1-C12):** Sinais de criptomoedas com ordens limites e contratos perpétuos.
  - **Grupo D (D1-D12):** Padrões customizados e estratégias algorítmicas experimentais.
- **Ativação e Desativação Dinâmica:** Permite ligar ou desligar slots de templates em tempo real sem reiniciar o contêiner.

### 3.3. Replay e Benchmarking (`/api/v1/benchmarks/replay-signals`)
- Permite submeter lotes históricos de mensagens brutas para testar a taxa de acerto do parser, medindo a latência média por sinal processado em microsegundos.

---

## 4. Exemplo de Resposta do Tokenizer

### Requisição:
```bash
POST /api/v1/tokens/tokenize
Content-Type: application/json

{
  "text": "EURUSD BUY 1.0850 TP 1.0900 SL 1.0800"
}
```

### Resposta Estruturada:
```json
{
  "success": true,
  "data": {
    "execution_time_us": 300,
    "has_signal": true,
    "signal_type": "FOREX_MARKET",
    "matched_template": "$(symbol) $(action) $(entry_price) TP $(profit_price) SL $(stoploss)",
    "tokens": [
      { "token_type": "SYMBOL", "raw_value": "EURUSD", "span": [0, 6] },
      { "token_type": "ACTION_BUY", "raw_value": "BUY", "span": [7, 10] },
      { "token_type": "PRICE_ENTRY", "raw_value": "1.0850", "span": [11, 17] },
      { "token_type": "TP", "raw_value": "1.0900", "span": [21, 27] },
      { "token_type": "SL", "raw_value": "1.0800", "span": [31, 37] }
    ],
    "entities": [
      {
        "symbol": { "asset": "EURUSD", "is_otc": false, "is_perp": false },
        "action": "BUY",
        "entry": { "type": "price", "prices": [1.085] },
        "stoploss": 1.08,
        "profits": [1.09],
        "gales": []
      }
    ]
  }
}
```
