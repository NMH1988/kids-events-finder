"""Wires the pieces together: models, the index, the retriever, the tools and the agent graph."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from src import config, llm
from src.agent.graph import build_graph
from src.rag.index import open_index
from src.rag.retriever import AdvancedRetriever
from src.tools.registry import RagSettings, build_tools


def build_retriever(*, with_helper: bool = True) -> AdvancedRetriever:
    """Build the retriever on the persisted index; BM25 alone if the index is not built yet."""
    embeddings = llm.build_embeddings()
    store = open_index(embeddings)
    helper = llm.build_chat_model(config.HELPER_MODEL) if with_helper else None
    return AdvancedRetriever(vectorstore=store, helper_llm=helper)


def build_agent(
    model: str,
    rag_settings: RagSettings,
    checkpointer: BaseCheckpointSaver,
    retriever: AdvancedRetriever | None = None,
    store: BaseStore | None = None,
):
    """Build the compiled agent graph for a model and RAG settings, with the long-term store."""
    retriever = retriever or build_retriever()
    tools = build_tools(
        retriever, rag_settings, ticketmaster_key=config.get_secret(config.TICKETMASTER_KEY_NAME)
    )
    return build_graph(llm.build_chat_model(model), tools, checkpointer, store)
