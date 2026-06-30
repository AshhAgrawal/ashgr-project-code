from __future__ import annotations

import os

from retail_agent.agent import RetailAgent
from retail_agent.store import RetailStore


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
