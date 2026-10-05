# Serviço 06: Persistência e Banco de Dados (`quant-postgres-db` e `msg_incoming_postgres`)

## 1. Visão Geral e Arquitetura de Persistência

Para garantir desacoplamento total, escalabilidade horizontal e isolamento de falhas, a camada de banco de dados foi estruturada de forma independente da aplicação. Nenhuma base de dados é executada dentro dos contêineres de API. Em vez disso, dois serviços **PostgreSQL 16 Alpine** dedicados operam na rede `quant-network` com volumes persistentes montados no host:

1. **`quant-postgres-db` (Porta 5432):** Banco de dados principal do motor quantitativo (`quant_trading`). Armazena operadores multi-tenant, contas criptografadas de brokers, ordens, posições, sinais normalizados, fundos e competições.
2. **`msg_incoming_postgres` (Porta 5433):** Banco de dados de alta vazão para ingestão de mensagens do Telegram e Webhooks (`msg_incoming_db`), garantindo que o alto volume de mensagens em salas de sinais não cause contenção de I/O no banco transacional de ordens.

```
                      ┌───────────────────────────────────────┐
                      │          Docker Host Storage          │
                      │ ───────────────────────────────────── │
                      │ • Volume: quant_postgres_data         │
                      │ • Volume: msg_incoming_postgres_data  │
                      └──────────────────┬────────────────────┘
                                         │ Montagem em /var/lib/postgresql/data
                                         ▼
                 ┌─────────────────────────────────────────────────┐
                 │          quant-network (Bridge 172.x)           │
                 │ ─────────────────────────────────────────────── │
                 │ • quant-postgres-db     (:5432) -> quant_trading│
                 │ • msg_incoming_postgres (:5433) -> msg_incoming │
                 └─────────────────────────────────────────────────┘
```

---

## 2. Metadados dos Bancos

| Atributo | Instância Quant (`quant-postgres-db`) | Instância Mensagens (`msg_incoming_postgres`) |
| :--- | :--- | :--- |
| **Imagem Docker** | `postgres:16-alpine` | `postgres:16-alpine` |
| **Porta Exposta no Host** | `5432:5432` | `5433:5432` |
| **Nome da Base de Dados** | `quant_trading` | `msg_incoming_db` |
| **Usuário Padrão** | `admin` | `admin` |
| **Volume de Armazenamento** | `quant_postgres_data` | `msg_incoming_postgres_data` |
| **Conexão Assíncrona** | `postgresql+asyncpg://admin:***@quant-postgres-db:5432/quant_trading` | `postgresql+asyncpg://admin:***@msg_incoming_postgres:5432/msg_incoming_db` |
| **Gerenciador de Migrações** | **Alembic** (revisões automáticas versionadas) | Alembic / SQLModel DDL |

---

## 3. Esquema Completo das Tabelas (`quant_trading`)

A base de dados `quant_trading` é composta por 11 tabelas de domínio relacional estritamente tipadas e auditadas:

### 3.1. `users` (Operadores Multi-Tenant)
- `id` (PK, INTEGER): Identificador único do operador.
- `email` (VARCHAR, UNIQUE, INDEX): E-mail de login.
- `username` (VARCHAR, UNIQUE, INDEX): Apelido ou handle.
- `hashed_password` (VARCHAR): Hash seguro gerado via Bcrypt.
- `full_name` (VARCHAR): Nome completo do operador.
- `role` (VARCHAR): Nível de privilégio (`admin` ou `trader`).
- `api_key` (VARCHAR, UNIQUE, INDEX): Chave estática para acesso programático.
- `is_active` (BOOLEAN): Status da conta.
- `is_superuser` (BOOLEAN): Indicador de privilégio administrativo.
- `created_at` / `updated_at` (TIMESTAMP WITH TIME ZONE).

### 3.2. `trading_accounts` (Contas de Brokers Conectadas)
- `id` (PK, INTEGER): Identificador da conta.
- `user_id` (FK -> users.id, INDEX): Dono da conta (isolamento multi-tenant).
- `broker` (VARCHAR): Provedor (`MT5`, `QUOTEX`, `POCKETOPTION`, `IQOPTION`).
- `account_alias` (VARCHAR): Nome de identificação (ex: "MT5 Real MEXAtlantic").
- `account_number` (VARCHAR): Login ou e-mail de acesso da corretora.
- `encrypted_credentials` (TEXT): Senhas e tokens de sessão criptografados via AES-128 Fernet.
- `mode` (VARCHAR): Modalidade operacional (`PRACTICE` ou `REAL`).
- `is_active` (BOOLEAN): Interruptor de ativação para execução de ordens.
- `balance` (NUMERIC(14,4)): Saldo atual sincronizado.
- `currency` (VARCHAR): Moeda base da conta (padrão `USD`).
- `server_name` (VARCHAR): Nome do servidor da corretora MT5.

### 3.3. `trading_signals` (Sinais Ingeridos e Auditados)
- `id` (PK, INTEGER): Identificador do sinal.
- `user_id` (FK -> users.id, INDEX): Operador associado.
- `sender_id` (VARCHAR, INDEX): ID do canal ou remetente de origem.
- `template_id` (INTEGER, INDEX): Slot ou ID do template gramatical correspondido.
- `broker_target` (VARCHAR): Broker de destino sugerido.
- `symbol` (VARCHAR, INDEX): Ativo financeiro (`EURUSD`, `EURUSD_otc`, `BTCUSDT`, etc.).
- `direction` (VARCHAR): `BUY`, `SELL`, `CALL`, `PUT`.
- `timeframe` (VARCHAR): Tempo gráfico (`M1`, `M5`, `H1`).
- `entry_price` (NUMERIC(14,5)): Preço alvo de abertura.
- `stop_loss` / `take_profit` (NUMERIC(14,5)): Proteções de saída.
- `raw_text` (TEXT): Mensagem original capturada na íntegra.
- `idempotency_hash` (VARCHAR(64), UNIQUE, INDEX): Hash criptográfico anti-duplicação.
- `status` (VARCHAR): `PENDING`, `EXECUTED`, `CANCELLED`, `FAILED`.

### 3.4. `order_executions` (Histórico de Execuções)
- `id` (PK, INTEGER): Identificador da execução.
- `user_id` (FK -> users.id, INDEX): Operador responsável.
- `account_id` (FK -> trading_accounts.id, INDEX): Conta que executou a ordem.
- `signal_id` (FK -> trading_signals.id, INDEX, NULLABLE): Sinal que gerou a ordem.
- `broker` (VARCHAR): Broker executor.
- `broker_ticket` (VARCHAR, INDEX): Ticket de identificação oficial gerado pela corretora.
- `symbol` (VARCHAR): Ativo operado.
- `side` (VARCHAR): Direção executada.
- `order_type` (VARCHAR): `MARKET`, `LIMIT`, `BINARY_OPTION`.
- `volume` (NUMERIC(10,4)): Tamanho do lote ou valor apostado.
- `entry_price` / `exit_price` (NUMERIC(14,5)): Preços de abertura e encerramento.
- `pnl` (NUMERIC(14,4)): Lucro ou prejuízo líquido obtido.
- `status` (VARCHAR): `OPEN`, `FILLED`, `CANCELLED`, `CLOSED`, `REJECTED`.

### 3.5. `signal_templates` (Templates da Matriz Gramatical)
- `id` (PK, INTEGER): Identificador do template.
- `user_id` (FK -> users.id, INDEX): Proprietário do template.
- `title` (VARCHAR): Título identificador do padrão sintático.
- `pattern` (TEXT): Expressão regular ou string de template (ex: `$(symbol) $(action) $(entry_price)...`).
- `signal_type` (VARCHAR): `MARKET` ou `BINARY`.
- `slot_code` (VARCHAR, INDEX): Identificador de matriz (ex: `A1`, `B4`).
- `priority` (INTEGER): Prioridade de avaliação léxica.
- `is_active` (BOOLEAN): Estado do slot.

### 3.6. `sender_rules` (Políticas de Filtragem de Remetentes)
- `id` (PK, INTEGER): Identificador da regra.
- `user_id` (FK -> users.id, INDEX): Operador.
- `sender_id` (VARCHAR, INDEX): ID do chat ou canal do Telegram.
- `sender_name` (VARCHAR): Nome de exibição do canal.
- `platform` (VARCHAR): `TELEGRAM`, `THREADS`, `WHATSAPP`.
- `policy` (VARCHAR): `ALLOW`, `BLOCK`, `DEFAULT`.
- `forward_to_brokers` (BOOLEAN): Flag para autorizar o despacho imediato de ordens.
- `is_active` (BOOLEAN): Estado da regra.

### 3.7. `funds` (Fundos e Gestão de Metas Prop Firm)
- `id` (PK, INTEGER): Identificador do fundo.
- `user_id` (FK -> users.id, INDEX): Operador proprietário.
- `title` (VARCHAR): Título do fundo (ex: "Alpha Prop Firm 100K").
- `target_amount` (NUMERIC(14,4)): Meta financeira total.
- `current_amount` (NUMERIC(14,4)): Saldo atual acumulado.
- `goal_type` (VARCHAR): `TARGET_CAPITAL`, `WIN_RATE_PERCENTAGE`, `PROFIT_FACTOR_RATIO`.
- `goal_target_value` (FLOAT): Valor numérico da meta.
- `max_drawdown_limit` (NUMERIC(14,4)): Limite máximo de perda aceitável.
- `win_rate_percentage` (FLOAT): Taxa de acerto acumulada.
- `current_drawdown` (NUMERIC(14,4)): Drawdown registrado a partir do pico.
- `status` (VARCHAR): `ACTIVE`, `PAUSED`, `COMPLETED`, `BREACHED`.

### 3.8. `challenges` e `challenge_participants` (Competições de Trading)
- Gerencia sprints e ligas competitivas entre operadores com ranking automático em tempo real (`rank_position`, `final_rank`, `gross_profit`, `gross_loss`).

### 3.9. `fund_contribution_audits` (Auditoria Contábil de Trades)
- Registra cirurgicamente o impacto individual de cada trade fechado no progresso de um fundo ou desafio, gravando `profit_loss`, `outcome`, `drawdown_recorded` e valores de progresso anterior e posterior.

---

## 4. Histórico de Migrações com Alembic

O esquema foi evoluído de forma não destrutiva através do diretório [`app/db/migrations`](file:///Users/macseqoia/gits/metatrader5-quant-server-python/app/db/migrations):

1. **`001_initial_schema.py`:** Criação das tabelas fundamentais de contas, sinais e ordens.
2. **`002_add_multitenancy_users.py`:** Adição da tabela `users`, chaves estrangeiras com cascata e colunas de `api_key` e `role`.
3. **`003_add_funds_and_templates.py`:**
   - Adição das colunas `sender_id` e `template_id` na tabela `trading_signals`.
   - Criação das tabelas `signal_templates`, `sender_rules`, `funds`, `challenges`, `challenge_participants` e `fund_contribution_audits`.
   - Ajuste de compatibilidade para `rank_position` e extensão da coluna `alembic_version.version_num` para `VARCHAR(64)`.
