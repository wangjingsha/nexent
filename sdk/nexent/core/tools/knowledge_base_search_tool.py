import json
import logging
from typing import List

import requests
from smolagents.tools import Tool

from ..utils.observer import MessageObserver, ProcessType
from ..utils.tools_common_message import SearchResultTextMessage
from pydantic import Field
from ...vector_database.elasticsearch_core import ElasticSearchCore
from ..models.embedding_model import BaseEmbedding

# Get logger instance
logger = logging.getLogger("knowledge_base_search_tool")


class KnowledgeBaseSearchTool(Tool):
    """Knowledge base search tool"""
    name = "knowledge_base_search"
    description = "Performs a local knowledge base search based on your query then returns the top search results. " \
                  "A tool for retrieving domain-specific knowledge, documents, and information stored in the local knowledge base. " \
                  "Use this tool when users ask questions related to specialized knowledge, technical documentation, " \
                  "domain expertise, personal notes, or any information that has been indexed in the knowledge base. " \
                  "Suitable for queries requiring access to stored knowledge that may not be publicly available."
    inputs = {"query": {"type": "string", "description": "The search query to perform."},
              "search_mode": {"type": "string", "description": "the search mode, optional values: hybrid, combining accurate matching and semantic search results across multiple indices.; accurate, Search for documents using fuzzy text matching across multiple indices; semantic, Search for similar documents using vector similarity across multiple indices.",
                              "default": "hybrid", "nullable": True},
              "index_names": {"type": "array", "description": "The list of knowledge base index names to search. If not provided, will search all available knowledge bases.", "nullable": True}}
    output_type = "string"

    tool_sign = "a"  # Used to distinguish different index sources for summaries

    def __init__(self, top_k: int = Field(description="Maximum number of search results", default=5),
                       index_names: List[str] = Field(description="The list of index names to search", default=None, exclude=True) ,
                       observer: MessageObserver = Field(description="Message observer", default=None, exclude=True),
                       embedding_model: BaseEmbedding = Field(description="The embedding model to use", default=None, exclude=True),
                       es_core: ElasticSearchCore = Field(description="Elasticsearch client", default=None, exclude=True)
                       ):
        """Initialize the KBSearchTool.
        
        Args:
            top_k (int, optional): Number of results to return. Defaults to 5.
            observer (MessageObserver, optional): Message observer instance. Defaults to None.
        
        Raises:
            ValueError: If language is not supported
        """
        super().__init__()
        self.top_k = top_k
        self.observer = observer
        self.es_core = es_core
        self.index_names = [] if index_names is None else index_names
        self.embedding_model = embedding_model

        self.record_ops = 1  # To record serial number
        self.running_prompt_zh = "知识库检索中..."
        self.running_prompt_en = "Searching the knowledge base..."

    def forward(self, query: str, search_mode: str= "hybrid", index_names: List[str] = None) -> str:
        # Send tool run message
        running_prompt = self.running_prompt_zh if self.observer.lang == "zh" else self.running_prompt_en
        self.observer.add_message("", ProcessType.TOOL, running_prompt)
        card_content = [{"icon": "search", "text": query}]
        self.observer.add_message("", ProcessType.CARD, json.dumps(card_content, ensure_ascii=False))

        # Use provided index_names if available, otherwise use default
        search_index_names = index_names if index_names is not None else self.index_names
        
        # Log the index_names being used for this search
        logger.info(f"KnowledgeBaseSearchTool called with query: '{query}', search_mode: '{search_mode}', index_names: {search_index_names}")
        
        if len(search_index_names) == 0:
            return json.dumps("No knowledge base selected. No relevant information found.", ensure_ascii=False)

        if search_mode=="hybrid":
            kb_search_data = self.es_search_hybrid(query=query, index_names=search_index_names)
        elif search_mode=="accurate":
            kb_search_data = self.es_search_accurate(query=query, index_names=search_index_names)
        elif search_mode=="semantic":
            kb_search_data = self.es_search_semantic(query=query, index_names=search_index_names)
        else:
            raise Exception(f"Invalid search mode: {search_mode}, only support: hybrid, accurate, semantic")

        kb_search_results = kb_search_data["results"]

        if not kb_search_results:
            raise Exception("No results found! Try a less restrictive/shorter query.")

        search_results_json = []  # Organize search results into a unified format
        search_results_return = []  # Format for input to the large model
        for index, single_search_result in enumerate(kb_search_results):
            # Temporarily correct the source_type stored in the knowledge base
            source_type = single_search_result.get("source_type", "")
            source_type = "file" if source_type in ["local", "minio"] else source_type
            title = single_search_result.get("title")
            if not title:
                title = single_search_result.get("filename", "")
            search_result_message = SearchResultTextMessage(title=title,
                text=single_search_result.get("content", ""), source_type=source_type,
                url=single_search_result.get("path_or_url", ""), filename=single_search_result.get("filename", ""),
                published_date=single_search_result.get("create_time", ""), score=single_search_result.get("score", 0),
                score_details=single_search_result.get("score_details", {}), cite_index=self.record_ops + index,
                search_type=self.name, tool_sign=self.tool_sign)

            search_results_json.append(search_result_message.to_dict())
            search_results_return.append(search_result_message.to_model_dict())

        self.record_ops += len(search_results_return)

        # Record the detailed content of this search
        if self.observer:
            search_results_data = json.dumps(search_results_json, ensure_ascii=False)
            self.observer.add_message("", ProcessType.SEARCH_CONTENT, search_results_data)
        return json.dumps(search_results_return, ensure_ascii=False)


    def es_search_hybrid(self, query, index_names):
        try:
            results = self.es_core.hybrid_search(index_names=index_names,
                                                   query_text=query,
                                                   embedding_model=self.embedding_model,
                                                   top_k=self.top_k)

            # Format results
            formatted_results = []
            for result in results:
                doc = result["document"]
                doc["score"] = result["score"]
                doc["index"] = result["index"]  # Include source index in results
                formatted_results.append(doc)

            return {
                "results": formatted_results,
                "total": len(formatted_results),
            }
        except Exception as e:
            raise Exception(f"Error during semantic search: {str(e)}")

    def es_search_accurate(self, query, index_names):
        try:
            results = self.es_core.accurate_search(index_names=index_names,
                                                   query_text=query,
                                                   top_k=self.top_k)

            # Format results
            formatted_results = []
            for result in results:
                doc = result["document"]
                doc["score"] = result["score"]
                doc["index"] = result["index"]  # Include source index in results
                formatted_results.append(doc)

            return {
                "results": formatted_results,
                "total": len(formatted_results),
            }
        except Exception as e:
            raise Exception(detail=f"Error during accurate search: {str(e)}")

    def es_search_semantic(self, query, index_names):
        try:
            results = self.es_core.semantic_search(index_names=index_names,
                                                   query_text=query,
                                                   embedding_model=self.embedding_model,
                                                   top_k=self.top_k)

            # Format results
            formatted_results = []
            for result in results:
                doc = result["document"]
                doc["score"] = result["score"]
                doc["index"] = result["index"]  # Include source index in results
                formatted_results.append(doc)

            return {
                "results": formatted_results,
                "total": len(formatted_results),
            }
        except Exception as e:
            raise Exception(detail=f"Error during semantic search: {str(e)}")