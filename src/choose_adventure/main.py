import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Choose Your Adventure")
    parser.add_argument("--model", default="qwen/qwen3.8-27b", help="LLM model name")
    parser.add_argument("--base-url", default="http://llm.courtdata.se/v1", help="LLM API base URL")
    parser.add_argument(
        "--db", default="~/.local/share/choose-adventure/stories.db", help="SQLite database path"
    )
    parser.add_argument("--version", action="version", version="0.1.0")

    args = parser.parse_args()
    print(f"model: {args.model}")
    print(f"base-url: {args.base_url}")
    print(f"db: {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
