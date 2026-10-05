# Serviço 05: MetaTrader 5 Gateway (`quant-mt5-gateway`)

## 1. Visão Geral e Arquitetura

O **MetaTrader 5 Gateway** é o componente de ponte (bridge) encarregado da interoperabilidade entre os contêineres Linux do ecossistema e o terminal de negociação **MetaTrader 5 (MT5)** de 64 bits.

Como a biblioteca oficial `MetaTrader5` da MetaQuotes foi desenhada exclusivamente para sistemas Windows, este gateway utiliza uma camada de emulação via **Wine** em conjunto com um servidor de sockets TCP Python de baixa latência (porta `5001`), permitindo que a API principal (`quant-trading-api`) envie ordens, consulte cotações de book de ofertas e monitore posições abertas sem dependência de uma máquina física Windows.

```
                  ┌────────────────────────────────────────┐
                  │          quant-trading-api             │
                  │   (Adaptador MT5: app/services/mt5)    │
                  └──────────────────┬─────────────────────┘
                                     │ TCP Socket Protocol (:5001)
                                     │ JSON RPC / Binary Commands
                                     ▼
                  ┌────────────────────────────────────────┐
                  │          quant-mt5-gateway             │
                  │ ────────────────────────────────────── │
                  │ • Python Socket Server (Wine Bridge)   │
                  │ • Wine Virtual Prefix (.wine64)        │
                  │ • MetaTrader 5 Terminal (terminal64)   │
                  │ • Headless Xvfb & VNC (Port 5900)      │
                  └──────────────────┬─────────────────────┘
                                     │ MT5 Client Protocol
                                     ▼
                  ┌────────────────────────────────────────┐
                  │    Corretora MT5 (Ex: MEXAtlantic,     │
                  │      IC Markets, RoboForex, etc.)      │
                  └────────────────────────────────────────┘
```

---

## 2. Metadados do Serviço

| Atributo | Valor / Especificação |
| :--- | :--- |
| **Porta do Socket Bridge** | `5001` (TCP) |
| **Porta VNC (Depuração Gráfica)** | `5900` (opcional, para visualização do terminal) |
| **Ambiente de Execução** | Wine 64-bit sobre Debian/Ubuntu headless com Xvfb |
| **Biblioteca MT5** | Python `MetaTrader5` 5.0.45+ |
| **Tempo de Execução Médio de Ordem** | **15 - 45 milissegundos (ms)** |

---

## 3. Principais Responsabilidades do Gateway

### 3.1. Gerenciamento de Conexão com a Corretora
- Executa `mt5.initialize()` apontando para o arquivo `terminal64.exe` configurado.
- Autentica a conta de negociação através de `mt5.login(login, password, server)`.
- Monitora a saúde da conexão verificando periodicamente o status `mt5.terminal_info().connected`.

### 3.2. Execução de Ordens de Compra e Venda
- Suporta ordens a mercado:
  - `TRADE_ACTION_DEAL` com `ORDER_TYPE_BUY` ou `ORDER_TYPE_SELL`.
- Configuração automática de parâmetros institucionais:
  - `type_filling`: `ORDER_FILLING_IOC` ou `ORDER_FILLING_FOK`.
  - `type_time`: `ORDER_TIME_GTC`.
  - Preço de entrada, `sl` (Stop Loss) e `tp` (Take Profit) normalizados para os dígitos do ativo (`digits`).
- Retorna o número do ticket (`order_ticket`), volume executado e timestamp do servidor da corretora.

### 3.3. Liquidação e Fechamento de Posições
- Localização de posições ativas por ticket via `mt5.positions_get(ticket=...)`.
- Envio de ordem inversa para zeragem imediata da posição:
  - Fechamento de compra através de ordem de venda pelo preço `bid`.
  - Fechamento de venda através de ordem de compra pelo preço `ask`.
- Suporte a fechamento em lote (Emergency Close All) em menos de 100ms.

### 3.4. Extração de Dados de Mercado e Símbolos
- Consulta de cotações em tempo real via `mt5.symbol_info_tick(symbol)`.
- Verificação das especificações do contrato (tamanho do lote, spread, alavancagem, margem requerida e horário de negociação).
