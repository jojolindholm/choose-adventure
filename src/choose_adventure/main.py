import argparse
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Choose Your Adventure")
    parser.add_argument("--model", default="huihui-qwen3.8-27b-abliterated", help="LLM model name")
    parser.add_argument("--base-url", default="http://llm.courtdata.se/v1", help="LLM API base URL")
    parser.add_argument(
        "--db", default="~/.local/share/choose-adventure/stories.db", help="SQLite database path"
    )
    parser.add_argument("--version", action="version", version="0.1.0")

    args = parser.parse_args()

    from choose_adventure.config import CyaConfig
    from choose_adventure.llm.client import LLMClient
    from choose_adventure.llm.storygen import StoryGenerator
    from choose_adventure.storage.repo import StoryRepository
    from choose_adventure.story.engine import StoryEngine
    from choose_adventure.ui.app import AdventureApp

    config = CyaConfig(
        base_url=args.base_url,
        model=args.model,
        db_path=str(pathlib.Path(args.db).expanduser()),
    )

    repo = StoryRepository(pathlib.Path(config.db_path).expanduser())
    llm = LLMClient(config)
    gen = StoryGenerator(llm)
    engine = StoryEngine(repo, gen)

    app = AdventureApp(config, repo, engine)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
