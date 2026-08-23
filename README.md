# Choose Your Adventure

A terminal AI choose-your-own-adventure game. You provide a premise, and an
LLM acts as the Game Master, writing vivid second-person prose and branching
choices. Every choice grows the story; every page is saved so you can replay
or continue later.

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
| `--db`       | `~/.local/share/choose-adventure/stories.db`   | SQLite database path   |

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
