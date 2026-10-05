# Serviço 04: Quant UI Dashboard (`quant-ui-dashboard`)

## 1. Visão Geral e Arquitetura

O **Quant UI Dashboard** é a interface unificada de comando (Single Pane of Glass) do sistema quantitativo. Construído como uma Single Page Application (SPA) ultra-rápida em **React 18**, **TypeScript**, **Vite** e **Tailwind CSS**, é empacotado dentro de um contêiner **Nginx 1.27 Alpine** que atua simultaneamente como servidor web estático e **Reverse Proxy reverso** para todos os microserviços do ecossistema.

Dessa forma, o navegador do operador se comunica exclusivamente com a porta `3000`, eliminando qualquer problema de CORS, resolvendo certificados e distribuindo as requisições internamente na rede privada `quant-network`.

```
                            Navegador do Usuário
                                     │
                             HTTP Port :3000
                                     ▼
                ┌─────────────────────────────────────────┐
                │          quant-ui-dashboard             │
                │        (Nginx 1.27-Alpine :3000)        │
                │ ─────────────────────────────────────── │
                │  • Static Assets (React 18 + Vite Dist) │
                │  • Reverse Proxy Rules                  │
                └─────┬──────────────┬──────────────┬─────┘
                      │              │              │
      /api/quant/     │  /api/msg/   │  /api/token/ │
          ▼           │      ▼       │      ▼       │
   ┌──────────────┐   │┌───────────┐ │┌───────────┐ │
   │ quant-api    │   ││msg-ingest │ ││tokenizer  │ │
   │ (:8000)      │   ││(:8001)    │ ││(:8000)    │ │
   └──────────────┘   │└───────────┘ │└───────────┘ │
```

---

## 2. Metadados do Serviço

| Atributo | Valor / Especificação |
| :--- | :--- |
| **Nome do Contêiner** | `quant-ui-dashboard` |
| **Imagem Base** | `ui-dashboard-ui-dashboard:latest` (base `nginx:1.27-alpine`) |
| **Porta Exposta** | `3000:3000` (TCP) |
| **Rede Docker** | `quant-network` (bridge) |
| **Frameworks de Frontend** | React 18, Vite 6, TypeScript, Tailwind CSS, TanStack Query |
| **Biblioteca de Ícones** | Lucide React |
| **Gerenciamento de Estado** | React Hooks, Context API, TanStack Query com cache reativo |

---

## 3. Roteamento do Nginx Reverse Proxy

O arquivo [`nginx.conf`](file:///Users/macseqoia/gits/AI%20own%20dashboard/nginx.conf) mapeia os prefixos de rota para os contêineres internos:

| Prefixo no Navegador | Destino Interno no Docker | Finalidade |
| :--- | :--- | :--- |
| `/` | `/usr/share/nginx/html/index.html` | SPA Fallback para navegação no React Router |
| `/api/quant/` | `http://quant-trading-api:8000/api/v1/` | Endpoints de contas, ordens, posições, fundos e auth |
| `/api/msg/` | `http://msg_incoming_ingestor:8001/api/v1/` | Histórico de mensagens do Telegram, regras e whitelist |
| `/api/msg/health` | `http://msg_incoming_ingestor:8001/health` | Healthcheck direto do serviço de mensagens |
| `/api/tokenizer/` | `http://trading-tokenizer-api:8000/api/v1/` | Teste de tokenização léxica e templates em Rust |
| `/api/tokenizer/health`| `http://trading-tokenizer-api:8000/health` | Healthcheck direto do tokenizer nativo |
| `/events` | `http://quant-trading-api:8000/events` | Stream de Server-Sent Events (SSE) sem buffering |

---

## 4. Catálogo Completo das Telas e Funcionalidades

### 4.1. Autenticação e Login (`/login`)
- **Login Seguro:** Validação assíncrona com API FastAPI emitindo JWT Bearer e armazenando a sessão no `localStorage`.
- **Botão Master Demo:** *Quick Admin Login* com um clique preenchendo e autenticando automaticamente as credenciais administrativas.
- **TopBar Integrada:** Exibe as iniciais do operador autenticado (`ADM`), seu e-mail e botão de encerramento de sessão (*Sign Out*).

### 4.2. Desk de Operações e Visão Geral (`/dashboard`)
- Indicadores em tempo real da saúde dos motores (Engine Online `:8000`, `:8001`, `:8002`).
- Resumo de métricas: taxa de acerto global (Win Rate %), total de PnL acumulado e latência média em microsegundos.
- Acesso rápido ao disjuntor de segurança *Emergency Close All Positions*.

### 4.3. Pipeline de Operações Ao Vivo (`/explore`)
- **Modo Kanban:** Visualização em colunas das operações (*Not Started*, *In Progress*, *Under Review*).
- **Cartões Operacionais:** Exibe par, direção (`CALL`/`PUT`/`BUY`/`SELL`), preço de entrada, alvo e contador de expiração ao vivo para pares OTC.
- Alternância entre visões: *Board*, *Timeline*, *Spreadsheet* e *Calendar*.

### 4.4. Brokers e Contas Conectadas (`/brokers`)
- **CRUD Completo:** Listagem das contas ativas de MetaTrader 5, Quotex, Pocket Option e IQ Option.
- **Interruptores Dinâmicos:** Liga/desliga contas instantaneamente com sincronização na tabela `trading_accounts`.
- **Modal de Conexão:** Formulário interativo para vincular novas contas com criptografia em repouso Fernet.
- **Sincronização e Remoção:** Botões para testar a conectividade da conta e remoção com confirmação.

### 4.5. Laboratório do Tokenizer em Rust (`/tokens`)
- **Execução Real:** Envia textos brutos de sinais para o motor nativo em Rust na porta `8002`.
- **Métricas de Latência:** Exibição da latência de parsing em microsegundos (µs).
- **Token Viewer:** Renderização visual de chips com os spans de bytes e classes semânticas (`SYMBOL`, `ACTION`, `PRICE_ENTRY`, `TP`, `SL`).
- **AST JSON Inspector:** Exibe a árvore sintática gerada contendo símbolo, tipo de mercado, alvos e passos de Martingale.

### 4.6. Matriz de Templates Gramaticais (`/templates`)
- **Matriz 48 Slots (A1 a D12):** Exibição interativa das categorias Forex MT5, Binary Turbo, Crypto Scalp e Custom Strategy.
- **Controle de Slots:** Botões de ativação e desativação em tempo real por slot com filtros por status (`ALL`, `ACTIVE`, `INACTIVE`, `BINARY`, `MARKET`).

### 4.7. Remetentes e Regras de Whitelist (`/providers`)
- Gerenciamento de políticas de filtragem: `ALLOW` (Whitelist), `BLOCK` (Blacklist) e `DEFAULT`.
- Interruptores globais de política (`Allow Any Sender` e `Strict Whitelist`).
- Tabela com contadores de mensagens processadas e encaminhamento para brokers.

### 4.8. Auditoria de Mensagens do Telegram (`/telegram`)
- **Feed em Tempo Real:** Exibe centenas de mensagens brutas capturadas ao vivo de dezenas de canais do Telegram.
- **Sidebar Dinâmica de Canais:** Identifica automaticamente os canais ativos e suas contagens de sinais.
- **Filtro por Canal e Busca Textual:** Permite filtrar instantaneamente o feed por palavras-chave ou canal selecionado.
- **Auto-Refresh:** Atualização periódica a cada 10 segundos para exibir novos sinais em tempo real.

### 4.9. Fundos e Gestão de Metas (`/funds`)
- Exibição de contas prop firm rastreadas com barras de progresso de acumulação de capital.
- Gráficos de Win Rate e limites de drawdown máximo permitido.
- Modal interativo para criação e acompanhamento de novos fundos no banco de dados.

### 4.10. Desafios e Competições de Traders (`/challenges`)
- Competições ativas com métricas de avaliação (`WIN_RATE_PERCENTAGE`, `TARGET_CAPITAL`, `PROFIT_FACTOR`).
- Tabela de classificação (*Leaderboard*) com ranking de participantes (🥇, 🥈, 🥉).
- Botão interativo *Join Sprint* e modal para criar novas competições.
