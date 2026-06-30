from __future__ import annotations

import os

from retail_agent.api import app
from retail_agent.agent import RetailAgent
from retail_agent.store import RetailStore

# Vercel discovers Python applications through a top-level `app` object.
# The instance is imported from retail_agent.api so the CLI and REST entry points remain
# available without duplicating any API routes.


def main() -> None:
    store = RetailStore("data")
    agent = RetailAgent(store, provider=os.getenv("LLM_PROVIDER"))
    print("Retail Store Agent")
    print("Type an instruction, or 'exit' to quit.")
    print(f"Provider: {agent.provider}")
    while True:
        try:
            user_text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_text.lower() in {"exit", "quit"}:
            break
        if not user_text:
            continue
        print(agent.handle(user_text))


if __name__ == "__main__":
    main()
