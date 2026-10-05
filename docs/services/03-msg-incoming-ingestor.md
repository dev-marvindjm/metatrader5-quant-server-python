# Serviço 03: MSG Incoming Ingestor (`msg_incoming_ingestor`)

## 1. Visão Geral e Arquitetura

O **MSG Incoming Ingestor** é o microserviço especializado na escuta em tempo real, filtragem seletiva e ingestão de mensagens de trading provenientes do protocolo **Telegram MTProto (via Telethon)** e de **Webhooks externos** (TradingView, Discord, WhatsApp ou bots customizados).

O ingestor opera de forma autônoma e resiliente: ele persiste as credenciais de sessão do Telegram em volume dedicado, armazena o histórico bruto de mensagens em seu próprio banco PostgreSQL (`msg_incoming_postgres`), aplica políticas de Whitelist/Blacklist por canal ou ID de remetente e despacha os sinais autorizados para o motor quantitativo (`quant-trading-api`).

```
                    Telegram Cloud (MTProto) & Webhooks
                                      │
                                      ▼
                 ┌───────────────────────────────────────────┐
                 │          msg_incoming_ingestor            │
                 │          (Porta Externa: 8001)            │
                 │ ───────────────────────────────────────── │
                 │ • Telethon MTProto Client                 │
                 │ • Policy Evaluator (ALLOW / BLOCK)        │
                 │ • Global Filtering Rules                  │
                 │ • Dispatcher HTTP assíncrono com retry    │
                 └──────────────┬─────────────────────┬──────┘
                                │                     │
                                ▼                     ▼
                    ┌──────────────────────┐  ┌──────────────────────┐
                    │ msg_incoming_postgres│  │  quant-trading-api   │
                    │   (Audit DB :5433)   │  │   (Signals Intake)   │
                    └──────────────────────┘  └──────────────────────┘
```

---

## 2. Metadados do Serviço

| Atributo | Valor / Especificação |
| :--- | :--- |
| **Nome do Contêiner** | `msg_incoming_ingestor` |
| **Imagem Base** | `msg-incoming-msg-ingestor:latest` |
| **Porta Exposta** | `8001:8001` (TCP) |
| **Rede Docker** | `quant-network` (bridge) |
| **Tecnologias** | Python 3.12, Telethon (MTProto), FastAPI, asyncpg |
| **Volume de Sessão** | `msg_incoming_telethon_sessions` (montado em `/app/sessions`) |
| **Healthcheck** | `GET /health` (`status: healthy`, `telegram_connected: true`) |

---

## 3. Principais Módulos e Responsabilidades

### 3.1. Cliente Telegram MTProto e Persistência de Sessão
- Conecta-se diretamente aos servidores do Telegram via `API_ID` e `API_HASH` utilizando a `TELEGRAM_SESSION_STRING` fornecida pelo operador.
- Mantém reconexão automática e escuta contínua de centenas de canais, supergrupos e bots de trading.
- Extrai metadados completos de cada mensagem: `chat_id`, `chat_title`, `sender_username`, `date`, visualizações e contagem de reencaminhamentos.

### 3.2. Motor de Políticas e Regras de Remetentes (`/api/v1/rules/senders`)
- **Políticas Individuais por Remetente:**
  - `ALLOW` (Whitelist): As mensagens do canal são aprovadas e despachadas para os brokers.
  - `BLOCK` (Blacklist): O remetente é bloqueado no ponto de entrada; as mensagens são registradas apenas para auditoria, sem encaminhamento aos brokers.
  - `DEFAULT`: Segue as diretrizes globais do operador.
- **Controle Global de Ingestão (`/api/v1/rules/config`):**
  - `allow_any_sender`: Quando ativado, aceita sinais de qualquer novo canal a menos que esteja explicitamente bloqueado.
  - `strict_whitelist`: Quando ativado, descarta sinais de qualquer canal que não esteja expressamente registrado na Whitelist com regra `ALLOW`.

### 3.3. Auditoria Completa de Mensagens (`/api/v1/messages/history`)
- Registra cada mensagem bruta recebida, com status de entrega:
  - `EMITTED`: Sinais aprovados encaminhados com sucesso ao motor quantitativo.
  - `BLOCKED`: Mensagens filtradas pelas políticas de proteção.
  - `RECEIVED`: Mensagens em fase de análise ou não classificadas como sinais executáveis.
- Fornece endpoints com paginação, filtro por plataforma (`TELEGRAM`, `THREADS`, `WHATSAPP`), remetente e busca textual.

### 3.4. Endpoint de Webhook para Ingestão Genérica (`/api/v1/messages/webhook`)
- Permite que robôs externos enviem sinais de trading em formato JSON via requisição HTTP POST autenticada, aplicando as mesmas regras de auditoria e validação de remetente antes de encaminhar ao broker.

---

## 4. Variáveis de Ambiente Críticas

| Variável | Descrição | Valor / Configuração |
| :--- | :--- | :--- |
| `API_ID` / `API_HASH` | Credenciais oficiais da aplicação Telegram MTProto | `2040` / `b18441a1...` |
| `TELEGRAM_SESSION_STRING` | String de sessão autorizada para login persistente | Sessão persistida em string Base64 |
| `TELEGRAM_AUTO_START` | Inicia o listener de mensagens no startup do contêiner | `true` |
| `BROKER_API_URL` | URL de destino do motor quantitativo de trading | `http://metatrader5-quant-server:8000` |
| `POSTGRES_HOST` / `PORT` | Conexão com o banco independente de mensagens | `postgres` (5432 interno) |
| `POSTGRES_DB` | Nome da base de dados de mensagens | `msg_incoming_db` |
| `SECRET_KEY` | Chave de assinatura dos tokens JWT do serviço | `generate_a_super_secret_jwt_key...` |
