# Serviço 01: Quant Trading API (`quant-trading-api`)

## 1. Visão Geral e Arquitetura

O **Quant Trading API** é o núcleo de roteamento, execução algorítmica, gerenciamento multi-tenant de contas e avaliação de performance financeira do ecossistema. Desenvolvido em **Python 3.12** com **FastAPI** assíncrono e **SQLModel (SQLAlchemy 2.0 + Pydantic v2)**, fornece endpoints REST e Server-Sent Events (SSE) para execução simultânea em mercados tradicionais (MetaTrader 5) e plataformas de opções binárias/OTC (Quotex, Pocket Option, IQ Option).

```
                      ┌───────────────────────────────────────┐
                      │          quant-ui-dashboard           │
                      │       (Nginx Proxy / Port 3000)       │
                      └──────────────────┬────────────────────┘
                                         │ /api/quant/
                                         ▼
                 ┌─────────────────────────────────────────────────┐
                 │       quant-trading-api (:8000)                 │
                 │ ─────────────────────────────────────────────── │
                 │ • Multi-Tenant Auth (JWT Bearer & API-Keys)     │
                 │ • Execution Engine (Adapters: MT5, QX, PO, IQ)  │
                 │ • Risk & Capital Evaluator (Funds & Challenges) │
                 │ • Signal Intake & Idempotent Audit              │
                 └───────┬─────────────────────────┬───────────────┘
                         │                         │
            asyncpg (5432)                         │ Sockets / WebSockets
                         ▼                         ▼
             ┌───────────────────────┐   ┌───────────────────────┐
             │   quant-postgres-db   │   │  Brokers: MT5 / QX /  │
             │     (PostgreSQL 16)   │   │     PO / IQ Option    │
             └───────────────────────┘   └───────────────────────┘
```

---

## 2. Metadados do Serviço

| Atributo | Valor / Especificação |
| :--- | :--- |
| **Nome do Contêiner** | `quant-trading-api` |
| **Imagem Base** | `metatrader5-quant-server-python-api:latest` |
| **Porta Exposta** | `8000:8000` (TCP) |
| **Rede Docker** | `quant-network` (bridge) |
| **Linguagem / Runtime** | Python 3.12 (CPython) |
| **Framework Web** | FastAPI 0.115+ (ASGI via Uvicorn) |
| **Camada ORM / Schemas** | SQLModel / SQLAlchemy 2.0 async + Pydantic v2 |
| **Driver de Banco** | `asyncpg` (PostgreSQL 16 nativo assíncrono) |
| **Criptografia em Repouso** | Fernet AES-128-CBC (`cryptography.fernet`) para senhas de brokers |
| **Healthcheck** | `GET /health` (`status: healthy`, `database: ok`) |

---

## 3. Principais Módulos e Responsabilidades

### 3.1. Autenticação e Multi-Tenancy Estrito
- **Modelos:** [`User`](file:///Users/macseqoia/gits/metatrader5-quant-server-python/app/domain/models/user.py) com isolamento estrito por `user_id` em todas as consultas SQL.
- **Tokens:** Emissão de tokens de acesso JWT assinados com HS256 contendo `sub` (ID do usuário), `email` e `role` (`admin` ou `trader`).
- **Chaves de API:** Suporte adicional para autenticação por cabeçalho `X-API-Key` permitindo integração direta de bots externos.
- **Endpoints de Auth:**
  - `POST /api/v1/auth/login` (Autenticação por credenciais com retorno de JWT e perfil)
  - `POST /api/v1/auth/register` (Criação de novos operadores)
  - `GET /api/v1/auth/me` (Consulta de perfil e status da sessão)

### 3.2. Gerenciamento de Contas de Brokers (`/api/v1/accounts`)
- **Adaptadores Suportados:**
  - `mt5`: MetaTrader 5 (Forex, Índices, Cripto e Commodities via Socket Bridge).
  - `quotex`: Opções binárias clássicas e pares OTC com suporte a payout dinâmico.
  - `pocketoption`: Conexão por WebSocket e token SSID de sessão.
  - `iqoption`: Opções digitais e binárias com suporte a expiração rápida.
- **Recursos Disponíveis:**
  - `GET /api/v1/accounts` (Lista de contas cadastradas do usuário autenticado).
  - `GET /api/v1/accounts/catalog` (Catálogo de brokers disponíveis e recursos).
  - `POST /api/v1/accounts` (Adiciona conta com credenciais criptografadas via Fernet).
  - `POST /api/v1/accounts/{id}/toggle` (Ativação/Desativação instantânea da conta).
  - `POST /api/v1/accounts/{id}/connect` (Teste e sincronização de conexão).
  - `DELETE /api/v1/accounts/{id}` (Remoção da conta).

### 3.3. Ingestão e Execução de Sinais (`/api/v1/signals`)
- **Ingestão:** Recebe sinais estruturados originados de Telegram (`msg_incoming_ingestor`), Webhooks externos ou gerados manualmente no painel.
- **Deduplicação Idempotente:** Gera hash criptográfico (`idempotency_hash`) a partir do símbolo, ação, tempo de expiração e preço de entrada para impedir reentradas indevidas.
- **Roteamento Inteligente:** Determina automaticamente o adaptador de broker correto conforme o tipo de ativo (ex: `EURUSD_otc` para Quotex/PocketOption, `XAUUSD` para MT5).
- **Endpoints:**
  - `POST /api/v1/signals/receive` (Ingestão com validação de regras de remetente e template).
  - `POST /api/v1/signals/execute` (Despacho imediato de ordem ao broker de destino).
  - `GET /api/v1/signals/history` (Histórico completo de sinais recebidos e status).

### 3.4. Execução de Ordens e Gestão de Posições (`/api/v1/orders` e `/api/v1/positions`)
- **Tipos de Ordem:** A mercado (`BUY`, `SELL`, `CALL`, `PUT`), ordens limitadas (`BUY_LIMIT`, `SELL_LIMIT`) e opções com tempo de expiração e Martingale progressivo.
- **Liquidação Emergencial:**
  - `POST /api/v1/positions/close` (Fechamento cirúrgico de ticket individual).
  - `POST /api/v1/positions/close-all` (Disjuntor de segurança: encerra todas as posições abertas em todos os brokers com uma única chamada).

### 3.5. Fundos e Desafios de Avaliação (`/api/v1/funds` e `/api/v1/challenges`)
- **Prop Firm Tracking:** Monitoramento contínuo de metas de capital, win rate mínimo e proteção contra drawdown máximo permitido.
- **Leaderboards em Tempo Real:** Classificação de participantes de competições com base em métricas de consistência (`WIN_RATE`, `PROFIT_FACTOR`, `TOTAL_PNL`).
- **Avaliação Automática de Trades:** O serviço [`progress_evaluator.py`](file:///Users/macseqoia/gits/metatrader5-quant-server-python/app/services/progress_evaluator.py) audita cada trade fechado e recalcula a pontuação do participante e do fundo associado.

---

## 4. Variáveis de Ambiente Críticas

| Variável | Descrição | Exemplo em Produção |
| :--- | :--- | :--- |
| `POSTGRES_HOST` | Host do banco PostgreSQL quant | `postgres` |
| `POSTGRES_PORT` | Porta interna do banco | `5432` |
| `POSTGRES_DB` | Nome da base de dados quant | `quant_trading` |
| `POSTGRES_USER` | Usuário do banco de dados | `admin` |
| `POSTGRES_PASSWORD` | Senha segura de acesso ao banco | `quant_secure_pwd` |
| `SECRET_KEY` | Chave de assinatura dos tokens JWT | `change-this-quant-secret-key-32-bytes-min!` |
| `FERNET_KEY` | Chave simétrica AES-128 para credenciais | `v9-eJ9K_FmQy6M9P4_5H6l2_jZ2y_8z0_3u5t_X4w1A=` |
| `MT5_HOST` / `MT5_PORT` | Endereço do bridge MetaTrader 5 | `quant-mt5-gateway:5001` |
| `TOKENIZER_URL` | Endereço do tokenizer Rust nativo | `http://trading-tokenizer-api:8000` |
| `MSG_INGESTOR_URL` | Endereço do serviço de mensagens | `http://msg_incoming_ingestor:8001` |
