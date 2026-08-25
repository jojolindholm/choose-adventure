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

Replay reads the stored story from disk — already-generated pages are shown
exactly as written and are never regenerated. Choosing an option that has not
been explored yet generates a new page and grows the story from there.

## Development

```sh
uv run pytest                 # default suite (no network)
uv run pytest -m integration -q   # live LLM calls (network required)
uv run ruff check .
uv run basedpyright src tests
```
