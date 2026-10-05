# Índice de Documentação dos Serviços do Ecossistema Quant

Este diretório contém a documentação técnica detalhada de cada serviço funcional que compõe a plataforma quantitativa de trading algorítmico, operando no servidor host `192.168.0.104`:

```
                                  ARQUITETURA DE SERVIÇOS
                                  
     [ 192.168.0.104:3000 ] ──────►  04. Quant UI Dashboard (Nginx + React 18)
                                                    │
                 ┌──────────────────────────────────┼──────────────────────────────────┐
                 │                                  │                                  │
                 ▼                                  ▼                                  ▼
      01. Quant Trading API              02. Trading Tokenizer              03. MSG Incoming Ingestor
           (Porta 8000)                       (Porta 8002)                       (Porta 8001)
                 │                                                                     │
        ┌────────┴────────┐                                                   ┌────────┴────────┐
        ▼                 ▼                                                   ▼                 ▼
 05. MT5 Gateway   06. PostgreSQL                                      Telegram Cloud    06. PostgreSQL
  (Socket 5001)     (Porta 5432)                                        (Telethon)        (Porta 5433)
```

---

## Catálogo de Serviços Documentados

1. [**01. Quant Trading API (`quant-trading-api`)**](file:///Users/macseqoia/gits/metatrader5-quant-server-python/docs/services/01-quant-trading-api.md)
   - Motor principal assíncrono em Python 3.12 / FastAPI.
   - Autenticação multi-tenant com JWT Bearer e API Keys.
   - Gestão de contas de brokers (MT5, Quotex, PocketOption, IQ Option) com criptografia Fernet.
   - Roteamento inteligente de sinais, liquidação emergencial de posições e avaliação de metas.

2. [**02. Trading Tokenizer API (`trading-tokenizer-api`)**](file:///Users/macseqoia/gits/metatrader5-quant-server-python/docs/services/02-trading-tokenizer-api.md)
   - Parser e analisador léxico de alta performance em Rust nativo.
   - Latência sub-milissegundo (< 350 µs) com extração de spans de bytes.
   - Matriz sintática de 48 slots gramaticais (A1-D12) para Forex, Cripto, Binárias e OTC.

3. [**03. MSG Incoming Ingestor (`msg_incoming_ingestor`)**](file:///Users/macseqoia/gits/metatrader5-quant-server-python/docs/services/03-msg-incoming-ingestor.md)
   - Cliente Telegram MTProto em tempo real via Telethon com persistência de sessão.
   - Ingestão contínua de dezenas de canais e webhooks externos com deduplicação.
   - Sistema de regras com políticas seletivas: `ALLOW` (Whitelist), `BLOCK` (Blacklist) e `DEFAULT`.

4. [**04. Quant UI Dashboard (`quant-ui-dashboard`)**](file:///Users/macseqoia/gits/metatrader5-quant-server-python/docs/services/04-quant-ui-dashboard.md)
   - Painel de controle completo desenvolvido em React 18, Vite, TypeScript e Tailwind CSS.
   - Nginx Reverse Proxy centralizando portas `:8000`, `:8001` e `:8002` sob a porta `:3000`.
   - 9 telas operacionais funcionais com Zero Exceções e integração em tempo real.

5. [**05. MetaTrader 5 Gateway (`quant-mt5-gateway`)**](file:///Users/macseqoia/gits/metatrader5-quant-server-python/docs/services/05-quant-mt5-gateway.md)
   - Ponte de execução MT5 para sistemas Linux via Wine 64-bit e servidor de sockets TCP (porta `5001`).
   - Gerenciamento de tickets, volume de lote, alvos de Stop Loss/Take Profit e zeragem de posições.

6. [**06. Persistência e Banco de Dados (`quant-postgres-db` e `msg_incoming_postgres`)**](file:///Users/macseqoia/gits/metatrader5-quant-server-python/docs/services/06-database-persistence.md)
   - Bancos de dados desacoplados executando em PostgreSQL 16 Alpine com volumes independentes.
   - Dicionário completo das 11 tabelas relacionais do sistema.
   - Histórico e estrutura das migrações de esquema com Alembic.
