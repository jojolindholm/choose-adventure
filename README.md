# Saga

A terminal AI choose-your-own-adventure game. You provide a premise, and an
LLM acts as the Game Master, writing vivid second-person prose, branching
choices, ASCII art, and a title for each story. Every choice grows the story;
every page is saved so you can replay or continue later.

## Prerequisites

- macOS
- [`uv`](https://docs.astral.sh/uv/) (Python 3.12+ is set up automatically by `uv sync`)

## Run

```sh
uv sync
uv run saga
```

### Install globally (run from any directory)

```sh
uv tool install .          # or: uv build && uv tool install ./dist/*.whl
saga                       # now on ~/.local/bin/saga, works anywhere
```

## Flags

| Flag         | Default                                        | Description            |
| ------------ | ---------------------------------------------- | ---------------------- |
| `--model`    | `huihui-qwen3.8-27b-abliterated`               | LLM model name         |
| `--base-url` | `http://llm.courtdata.se/v1`                   | LLM API base URL       |
| `--api-key`  | *(empty)*                                      | LLM API key (empty → free no-auth endpoint) |
| `--db`       | `~/.local/share/choose-adventure/stories.db`   | SQLite database path   |

## Model providers

**Free local endpoint (default, no key needed):**
```sh
saga    # http://llm.courtdata.se/v1, huihui-qwen3.8-27b-abliterated
```

**OpenRouter (e.g. fast GLM-4.7-Flash, needs an API key):** set these env vars (or in `~/.zshrc`), then run `saga`:
```sh
export CYA_BASE_URL="https://openrouter.ai/api/v1"
export CYA_MODEL="z-ai/glm-4.7-flash"
export CYA_API_KEY="sk-or-..."     # app-only key; stays out of this repo
saga
```
Environment variables (`CYA_BASE_URL`, `CYA_MODEL`, `CYA_API_KEY`, `CYA_DB`) provide defaults; explicit `--model` / `--base-url` / `--api-key` / `--db` CLI flags take precedence. Keep `CYA_API_KEY` in your shell profile, not in source control.

## Keys

| Key | Action      |
| --- | ----------- |
| `1-4` | Choose an option |
| `a`  | Retry the last generation |
| `n`  | Start a new story |
| `r`  | Replay a saved story |
| `m`  | Back to menu |
| `q`  | Quit |

## Saves

Stories are stored in a SQLite database at `~/.local/share/choose-adventure/stories.db`
(override with `--db`). Each page, its options, the character state, and the
generated story name are persisted as you play.

Replay reads the stored story from disk — already-generated pages are shown
exactly as written and are never regenerated. Choosing an option that has not
been explored yet generates a new page and grows the story from there.

## Server + thin client (multiplayer)

The game can run as a server on one machine with thin terminal clients
connecting over HTTP. The server owns the LLM calls and the SQLite databases;
clients only render pages and send choices.

### Run the server (Docker)

```sh
CYA_SERVER_TOKEN="pick-a-shared-secret" \
CYA_BASE_URL="https://openrouter.ai/api/v1" \
CYA_MODEL="z-ai/glm-4.7-flash" \
CYA_API_KEY="sk-or-..." \
docker compose up -d --build
```

This serves `http://localhost:8787`. Player databases live in the `cya-data`
Docker volume (one `stories-<player>.db` file per player). The LLM endpoint
and databases are never exposed to clients — only the API port is public.

### Run the server without Docker

```sh
export CYA_SERVER_TOKEN="pick-a-shared-secret"
export CYA_DATA_DIR=./data        # where per-player .db files go (default ./data)
uv run saga-server                # listens on 0.0.0.0:8787
```

The server on this machine is also exposed publicly at
`https://saga.johanlindholm.com` (Caddy reverse proxy, Let's Encrypt cert,
auto-renewed). Play from any machine with:
`uv run saga-client --server https://saga.johanlindholm.com --token "$CYA_SERVER_TOKEN" --player <name>`.

## Development

```sh
uv run pytest                 # default suite (no network)
uv run pytest -m integration -q   # live LLM calls (network required)
uv run ruff check .
uv run basedpyright src tests
```
