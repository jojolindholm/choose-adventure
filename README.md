# Choose Your Adventure

A terminal AI choose-your-own-adventure game. You provide a premise, and an
LLM acts as the Game Master, writing vivid second-person prose, branching
choices, and ASCII art for each scene. Every choice grows the story; every
page is saved so you can replay or continue later.

## Prerequisites

- macOS
- [`uv`](https://docs.astral.sh/uv/) (Python 3.12+ is set up automatically by `uv sync`)

## Run

```sh
uv sync
uv run cya
```

### Install globally (run from any directory)

```sh
uv tool install .          # or: uv build && uv tool install ./dist/*.whl
cya                        # now on ~/.local/bin/cya, works anywhere
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
cya    # http://llm.courtdata.se/v1, huihui-qwen3.8-27b-abliterated
```

**OpenRouter (e.g. fast GLM-4.7-Flash, needs an API key):** set these env vars (or in `~/.zshrc`), then run `cya`:
```sh
export CYA_BASE_URL="https://openrouter.ai/api/v1"
export CYA_MODEL="z-ai/glm-4.7-flash"
export CYA_API_KEY="sk-or-..."     # app-only key; stays out of this repo
cya
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
(override with `--db`). Each page, its options, and the character state are
persisted as you play.

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
uv run cya-server                 # listens on 0.0.0.0:8787
```

### Connect a thin client

```sh
uv run cya-client --server http://localhost:8787 --token "$CYA_SERVER_TOKEN" --player alice
```

Env vars `CYA_SERVER_URL`, `CYA_SERVER_TOKEN`, `CYA_PLAYER` provide the same
defaults. Each player gets their own stories; a shared secret blocks stray
connections. The client is the same Textual UI as the local app, talking to
the server instead of the local engine.

## Development

```sh
uv run pytest                 # default suite (no network)
uv run pytest -m integration -q   # live LLM calls (network required)
uv run ruff check .
uv run basedpyright src tests
```
