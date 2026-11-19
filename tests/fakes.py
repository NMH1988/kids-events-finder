"""Fakes for tests: a scripted chat model, a keyword vector store and a stub helper model."""

from typing import Any

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from src.rag.retriever import tokenize


class ScriptedChatModel(BaseChatModel):
    """A chat model that returns pre-written messages in order and records what it was sent."""

    responses: list[AIMessage]
    received: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        """Name the fake model type."""
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        """Return the next scripted message."""
        self.received.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])

    def bind_tools(self, tools, **kwargs):
        """Return itself: the scripted messages already hold the tool calls."""
        return self


class KeywordVectorStore:
    """A stand-in for Chroma that ranks documents by shared words with the query."""

    def __init__(self, documents: list[Document]) -> None:
        """Keep the documents to search."""
        self.documents = documents

    def similarity_search(self, query: str, k: int, filter: dict | None = None) -> list[Document]:
        """Return up to k documents with the most words in common with the query."""
        words = set(tokenize(query))
        docs = [
            d
            for d in self.documents
            if not filter or all(d.metadata.get(key) == value for key, value in filter.items())
        ]
        docs.sort(key=lambda d: len(words & set(tokenize(d.page_content))), reverse=True)
        return docs[:k]


class StubStructured:
    """Returns a fixed object from invoke(), like a model with structured output."""

    def __init__(self, value: Any) -> None:
        """Keep the value to return."""
        self.value = value
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> Any:
        """Record the prompt and return the fixed value."""
        self.prompts.append(prompt)
        return self.value


class StubHelperLLM:
    """A helper model whose structured output returns a value chosen per schema name."""

    def __init__(self, by_schema: dict[str, Any]) -> None:
        """Keep the values to return for each schema class name."""
        self.by_schema = by_schema
        self.stubs: dict[str, StubStructured] = {}

    def with_structured_output(self, schema: type) -> StubStructured:
        """Return a stub that answers with the value for this schema."""
        stub = StubStructured(self.by_schema[schema.__name__])
        self.stubs[schema.__name__] = stub
        return stub
