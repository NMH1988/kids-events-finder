"""Embed the knowledge base with OpenRouter and write the Chroma index (needs the API key).

Run: python -m scripts.build_index
"""

from src import llm
from src.rag.index import build_index


def main() -> None:
    """Build the index and print how many places were embedded."""
    count = build_index(llm.build_embeddings())
    print(f"Indexed {count} places.")


if __name__ == "__main__":
    main()
