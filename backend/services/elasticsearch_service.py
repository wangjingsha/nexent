"""
Elasticsearch Application Interface Module

This module provides REST API interfaces for interacting with Elasticsearch, including index management, document operations, and search functionality.
Main features include:
1. Index creation, deletion, and querying
2. Document indexing, deletion, and searching
3. Support for multiple search methods: exact search, semantic search, and hybrid search
4. Health check interface
"""
import asyncio
import os
import time
import logging

from typing import Optional, Generator, List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
import yaml
from nexent.core.models.embedding_model import JinaEmbedding
from nexent.vector_database.elasticsearch_core import ElasticSearchCore
from nexent.core.nlp.tokenizer import calculate_term_weights
from fastapi import HTTPException, Query, Body, Path, Depends
from fastapi.responses import StreamingResponse
from consts.const import ES_API_KEY, ES_HOST
from consts.model import SearchRequest, HybridSearchRequest
from utils.config_utils import config_manager, tenant_config_manager, get_model_name_from_config
from utils.file_management_utils import get_all_files_status, get_file_size
from database.knowledge_db import create_knowledge_record, get_knowledge_record, update_knowledge_record, delete_knowledge_record
from database import attachment_db

# Configure logging
logger = logging.getLogger("elasticsearch_service")


def generate_knowledge_summary_stream(keywords: str, language: str, tenant_id: str) -> Generator:
    """
    Generate a knowledge base summary based on keywords

    Args:
        keywords: Keywords that frequently appear in the knowledge base content
        language: Language of the knowledge base content
        tenant_id: The tenant ID for configuration

    Returns:
        str:  Generate a knowledge base summary
    """
    # Load environment variables
    load_dotenv()

    # Load prompt words based on language
    template_file = 'backend/prompts/knowledge_summary_agent.yaml' if language == 'zh' else 'backend/prompts/knowledge_summary_agent_en.yaml'
    with open(template_file, 'r', encoding='utf-8') as f:
        prompts = yaml.safe_load(f)
    logger.info(f"Generating knowledge with template: {template_file}")
    # Build messages
    messages = [{"role": "system", "content": prompts['system_prompt']},
        {"role": "user", "content": prompts['user_prompt'].format(content=keywords)}]

    # Get model configuration from tenant config manager
    model_config = tenant_config_manager.get_model_config(key="LLM_SECONDARY_ID", tenant_id=tenant_id)
    
    # initialize OpenAI client
    client = OpenAI(api_key=model_config.get('api_key', ""),
                    base_url=model_config.get('base_url', ""))

    try:
        # Create stream chat completion request
        stream = client.chat.completions.create(
            model=get_model_name_from_config(model_config) if model_config.get("model_name") else "",  # use model name from config
            messages=messages,
            stream=True  # enable stream output
        )

        # Iterate through stream response
        for chunk in stream:
            new_token = chunk.choices[0].delta.content
            if new_token is not None:
                yield new_token
        yield "END"

    except Exception as e:
        logger.error(f"Error occurred: {str(e)}")
        yield f"Error: {str(e)}"
        

# Initialize ElasticSearchCore instance with HTTPS support
elastic_core = ElasticSearchCore(
    host=ES_HOST,
    api_key=ES_API_KEY,
    embedding_model=None,
    verify_certs=False,
    ssl_show_warn=False,
)


def get_es_core():
    # ensure embedding model is latest
    elastic_core.embedding_model = JinaEmbedding(api_key=config_manager.get_config("EMBEDDING_API_KEY"))
    return elastic_core


class ElasticSearchService:
    @staticmethod
    def create_index(
            index_name: str = Path(..., description="Name of the index to create"),
            embedding_dim: Optional[int] = Query(None, description="Dimension of the embedding vectors"),
            es_core: ElasticSearchCore = Depends(get_es_core),
            user_id: Optional[str] = Body(None, description="ID of the user creating the knowledge base"),
            tenant_id: Optional[str] = Body(None, description="ID of the tenant creating the knowledge base"),
    ):
        try:
            if es_core.client.indices.exists(index=index_name):
                raise HTTPException(status_code=400, detail=f"Index {index_name} already exists")
            success = es_core.create_vector_index(index_name, embedding_dim=embedding_dim or es_core.embedding_dim)
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to create index {index_name}")
            knowledge_data = {'index_name': index_name, 'created_by': user_id, "tenant_id": tenant_id}
            create_knowledge_record(knowledge_data)
            return {"status": "success", "message": f"Index {index_name} created successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating index: {str(e)}")

    @staticmethod
    async def delete_index(
            index_name: str = Path(..., description="Name of the index to delete"),
            es_core: ElasticSearchCore = Depends(get_es_core),
            user_id: Optional[str] = Body(None, description="ID of the user delete the knowledge base"),
    ):
        try:
            # 1. Get list of files from the index
            try:
                files_to_delete = await ElasticSearchService.list_files(index_name, search_redis=False, es_core=es_core)
                if files_to_delete and files_to_delete.get("files"):
                    # 2. Delete files from MinIO storage
                    for file_info in files_to_delete["files"]:
                        object_name = file_info.get("path_or_url")
                        source_type = file_info.get("source_type")
                        if object_name and source_type == "minio":
                            logger.info(f"Deleting file {object_name} from MinIO for index {index_name}")
                            attachment_db.delete_file(object_name)
            except Exception as e:
                # Log the error but don't block the index deletion
                logger.error(f"Error deleting associated files from MinIO for index {index_name}: {str(e)}")

            # 3. Delete the index in Elasticsearch
            success = es_core.delete_index(index_name)
            if not success:
                # Even if deletion fails, we proceed to database record cleanup
                logger.warning(f"Index {index_name} not found in Elasticsearch or could not be deleted, but proceeding with DB cleanup.")

            # 4. Delete the knowledge base record from the database
            update_data = {
                "updated_by": user_id,
                "index_name": index_name
            }
            success = delete_knowledge_record(update_data)
            if not success:
                raise HTTPException(status_code=500, detail=f"Error deleting knowledge record for index {index_name}")

            return {"status": "success", "message": f"Index {index_name} and associated files deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error deleting index: {str(e)}")

    @staticmethod
    def list_indices(
            pattern: str = Query("*", description="Pattern to match index names"),
            include_stats: bool = Query(False, description="Whether to include index stats"),
            user_id: Optional[str] = Body(None, description="ID of the user listing the knowledge base"),
            tenant_id: Optional[str] = Body(None, description="ID of the tenant listing the knowledge base"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        List all indices that the current user has permissions to access.

        Args:
            pattern: Pattern to match index names
            include_stats: Whether to include index stats
            user_id: ID of the user listing the knowledge base
            tenant_id: ID of the tenant listing the knowledge base
            es_core: ElasticSearchCore instance

        Returns:
            Dict[str, Any]: A dictionary containing the list of indices and the count.
        """
        all_indices_list = es_core.get_user_indices(pattern)

        filtered_indices_list = []
        if tenant_id:
            for index_name in all_indices_list:
                # Search in the Postgres database to get the tenant_id
                knowledge_record = get_knowledge_record(query={"index_name": index_name})
                if knowledge_record and knowledge_record.get("tenant_id") == tenant_id:
                    filtered_indices_list.append(index_name)
        else:
            filtered_indices_list = all_indices_list

        indices = [info.get("index") if isinstance(info, dict) else info for info in filtered_indices_list]

        response = {
            "indices": indices,
            "count": len(indices)
        }

        if include_stats:
            stats_info = []
            if filtered_indices_list:
                indice_stats = es_core.get_index_stats(filtered_indices_list)
                for index_name in filtered_indices_list:
                    index_stats = indice_stats.get(index_name, {})
                    stats_info.append({
                        "name": index_name,
                        "stats": index_stats
                    })
            response["indices_info"] = stats_info
        
        return response

    @staticmethod
    def get_index_name(
            index_name: str = Path(..., description="Name of the index"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Get detailed information about the index, including statistics, field mappings, file list, and processing information

        Args:
            index_name: Index name
            es_core: ElasticSearchCore instance

        Returns:
            Dictionary containing detailed index information
        """
        try:
            # Get all the info in one combined response
            stats = es_core.get_index_stats([index_name])
            mappings = es_core.get_index_mapping([index_name])

            # Check if stats and mappings are valid
            index_stats = None
            if stats and index_name in stats:
                index_stats = stats[index_name]
            else:
                logger.error(f"404: Index {index_name} not found in stats")
                index_stats = {}

            fields = None
            if mappings and index_name in mappings:
                fields = mappings[index_name]
            else:
                logger.error(f"404: Index {index_name} not found in mappings:")
                fields = []

            # Check if base_info exists in stats
            base_info = None
            search_performance = {}
            if index_stats and "base_info" in index_stats:
                base_info = index_stats["base_info"]
                search_performance = index_stats.get("search_performance", {})
            else:
                logger.error(f"404: Index {index_name} may not be created yet")
                base_info = {
                    "doc_count": 0,
                    "unique_sources_count": 0,
                    "store_size": "0",
                    "process_source": "Unknown",
                    "embedding_model": "Unknown",
                }

            return {
                "base_info": base_info,
                "search_performance": search_performance,
                "fields": fields
            }
        except Exception as e:
            error_msg = str(e)
            # Check if it's an ElasticSearch connection issue
            if "503" in error_msg or "search_phase_execution_exception" in error_msg:
                raise HTTPException(status_code=503, detail=f"ElasticSearch service unavailable for index {index_name}: {error_msg}")
            elif "ApiError" in error_msg:
                raise HTTPException(status_code=503, detail=f"ElasticSearch API error for index {index_name}: {error_msg}")
            else:
                raise HTTPException(status_code=404, detail=f"Error getting info for index {index_name}: {error_msg}")

    @staticmethod
    def index_documents(
            index_name: str = Path(..., description="Name of the index"),
            data: List[Dict[str, Any]] = Body(..., description="Document List to process"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Index documents and create vector embeddings, create index if it doesn't exist

        Args:
            index_name: Index name
            data: List containing document data to be indexed
            es_core: ElasticSearchCore instance

        Returns:
            IndexingResponse object containing indexing result information
        """
        try:
            if not index_name:
                raise HTTPException(status_code=400, detail="Index name is required")

            # Create index if needed (ElasticSearchCore will handle embedding_dim automatically)
            if not es_core.client.indices.exists(index=index_name):
                try:
                    ElasticSearchService.create_index(index_name, es_core=es_core)
                    logger.info(f"Created new index {index_name}")
                except Exception as create_error:
                    raise HTTPException(status_code=500, detail=f"Failed to create index {index_name}: {str(create_error)}")

            # Transform indexing request results to documents
            documents = []

            for idx, item in enumerate(data):
                # All items should be dictionaries
                if not isinstance(item, dict):
                    logger.warning(f"Skipping item {idx} - not a dictionary")
                    continue

                # Extract metadata
                metadata = item.get("metadata", {})
                source = item.get("path_or_url")
                text = item.get("content", "")
                source_type = item.get("source_type")
                file_size = item.get("file_size")
                file_name = item.get("filename", os.path.basename(source) if source and source_type == "local" else "")

                # Get from metadata
                title = metadata.get("title", "")
                language = metadata.get("languages", ["null"])[0] if metadata.get("languages") else "null"
                author = metadata.get("author", "null")
                date = metadata.get("date", time.strftime("%Y-%m-%d", time.localtime()))
                create_time = metadata.get("creation_date", time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()))
                if isinstance(create_time, (int, float)):
                    import datetime
                    create_time = datetime.datetime.fromtimestamp(create_time).isoformat()

                # Set embedding model name from the embedding model
                embedding_model_name = ""
                if es_core.embedding_model:
                    embedding_model_name = es_core.embedding_model.model

                # Create document
                document = {
                    "title": title,
                    "filename": file_name,
                    "path_or_url": source,
                    "source_type": source_type,
                    "language": language,
                    "author": author,
                    "date": date,
                    "content": text,
                    "process_source": "Unstructured",
                    "file_size": file_size,
                    "create_time": create_time,
                    "languages": metadata.get("languages", []),
                    "embedding_model_name": embedding_model_name
                }

                documents.append(document)

            total_submitted = len(documents)
            if total_submitted == 0:
                return {
                    "success": True,
                    "message": "No documents to index",
                    "total_indexed": 0,
                    "total_submitted": 0
                }

            # Index documents (use default batch_size and content_field)
            try:
                total_indexed = es_core.index_documents(
                    index_name=index_name,
                    documents=documents
                )

                return {
                    "success": True,
                    "message": f"Successfully indexed {total_indexed} documents",
                    "total_indexed": total_indexed,
                    "total_submitted": total_submitted
                }
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error during indexing: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Error during indexing: {error_msg}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error indexing documents: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Error indexing documents: {error_msg}")

    @staticmethod
    async def list_files(
            index_name: str = Path(..., description="Name of the index"),
            include_chunks: bool = Query(False, description="Whether to include text chunks for each file"),
            search_redis: bool = Query(True, description="Whether to search Redis to get incomplete files"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Get file list for the specified index, including files that are not yet stored in ES

        Args:
            index_name: Name of the index
            include_chunks: Whether to include text chunks for each file
            search_redis: Whether to search Redis to get incomplete files
            es_core: ElasticSearchCore instance

        Returns:
            Dictionary containing file list
        """
        try:
            files = []
            # Get existing files from ES
            existing_files = es_core.get_file_list_with_details(index_name)

            if search_redis:
                # Get unique celery files list and the status of each file
                celery_task_files = await get_all_files_status(index_name)
                # Create a set of path_or_urls from existing files for quick lookup
                existing_paths = {file_info.get('path_or_url') for file_info in existing_files}

                # For files already stored in ES, add to files list
                for file_info in existing_files:
                    file_data = {
                        'path_or_url': file_info.get('path_or_url'),
                        'file': file_info.get('filename', ''),
                        'file_size': file_info.get('file_size', 0),
                        'create_time': file_info.get('create_time', ''),
                        'status': "COMPLETED",
                        'latest_task_id': ''
                    }
                    files.append(file_data)

                # For files not yet stored in ES (files currently being processed)
                for path_or_url, status_info in celery_task_files.items():
                    # Skip files that are already in existing_files to avoid duplicates
                    if path_or_url not in existing_paths:
                        # Ensure status_info is a dictionary
                        status_dict = status_info if isinstance(status_info, dict) else {}

                        # Get source_type and original_filename, with defaults
                        source_type = status_dict.get('source_type') if status_dict.get('source_type') else 'minio'
                        original_filename = status_dict.get('original_filename')

                        # Determine the filename
                        filename = original_filename or (os.path.basename(path_or_url) if path_or_url else '')

                        file_size = 0
                        file_size = get_file_size(source_type, path_or_url)

                        file_data = {
                            'path_or_url': path_or_url,
                            'file': filename,
                            'file_size': file_size,
                            'create_time': time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                            'status': status_dict.get('state', 'UNKNOWN'),
                            'latest_task_id': status_dict.get('latest_task_id', '')
                        }
                        files.append(file_data)
            else:
                # Only process files already stored in ES (simplified flow)
                for file_info in existing_files:
                    file_data = {
                        'path_or_url': file_info.get('path_or_url'),
                        'file': file_info.get('filename', ''),
                        'file_size': file_info.get('file_size', 0),
                        'create_time': file_info.get('create_time', ''),
                        'status': "COMPLETED"
                    }
                    files.append(file_data)

            # Unified chunks processing for all files
            if include_chunks:
                # Prepare msearch body for all completed files
                completed_files_map = {f['path_or_url']: f for f in files if f['status'] == "COMPLETED"}
                msearch_body = []

                for path_or_url in completed_files_map.keys():
                    msearch_body.append({'index': index_name})
                    msearch_body.append({
                        "query": {"term": {"path_or_url": path_or_url}},
                        "size": 100,
                        "_source": ["id", "title", "content", "create_time"]
                    })

                # Initialize chunks for all files
                for file_data in files:
                    file_data['chunks'] = []
                    file_data['chunk_count'] = 0

                if msearch_body:
                    try:
                        msearch_responses = es_core.client.msearch(
                            body=msearch_body,
                            index=index_name
                        )

                        for i, file_path in enumerate(completed_files_map.keys()):
                            response = msearch_responses['responses'][i]
                            file_data = completed_files_map[file_path]

                            if 'error' in response:
                                logger.error(f"Error getting chunks for {file_data.get('path_or_url')}: {response['error']}")
                                continue

                            chunks = []
                            for hit in response["hits"]["hits"]:
                                source = hit["_source"]
                                chunks.append({
                                    "id": source.get("id"),
                                    "title": source.get("title"),
                                    "content": source.get("content"),
                                    "create_time": source.get("create_time")
                                })

                            file_data['chunks'] = chunks
                            file_data['chunk_count'] = len(chunks)

                    except Exception as e:
                        logger.error(f"Error during msearch for chunks: {str(e)}")
            else:
                for file_data in files:
                    file_data['chunks'] = []
                    file_data['chunk_count'] = 0

            return {"files": files}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error getting file list for index {index_name}: {str(e)}")


    @staticmethod
    def delete_documents(
            index_name: str = Path(..., description="Name of the index"),
            path_or_url: str = Query(..., description="Path or URL of documents to delete"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        # 1. Delete ES documents
        deleted_count = es_core.delete_documents_by_path_or_url(index_name, path_or_url)
        # 2. Delete MinIO file
        minio_result = attachment_db.delete_file(path_or_url)
        return {"status": "success", "deleted_es_count": deleted_count, "deleted_minio": minio_result.get("success")}

    @staticmethod
    # Search Operations
    def accurate_search(
            request: SearchRequest = Body(..., description="Search request parameters"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Search documents in multiple indices using fuzzy text matching

        Args:
            request: SearchRequest object containing search parameters
            es_core: ElasticSearchCore instance

        Returns:
            Response containing search results, total count, and query time
        """
        try:
            # Validate that query is not empty
            if not request.query.strip():
                raise HTTPException(status_code=400, detail="Search query cannot be empty")

            # Validate index names
            if not request.index_names:
                raise HTTPException(status_code=400, detail="At least one index name is required")

            start_time = time.time()
            results = es_core.accurate_search(request.index_names, request.query, request.top_k)
            query_time = (time.time() - start_time) * 1000  # Convert to milliseconds

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
                "query_time_ms": query_time
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error during accurate search: {str(e)}")

    @staticmethod
    def semantic_search(
            request: SearchRequest = Body(..., description="Search request parameters"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Search for similar documents in multiple indices using vector similarity

        Args:
            request: SearchRequest object containing search parameters
            es_core: ElasticSearchCore instance

        Returns:
            Response containing search results, total count, and query time
        """
        try:
            # Validate that query is not empty
            if not request.query.strip():
                raise HTTPException(status_code=400, detail="Search query cannot be empty")

            # Validate index names
            if not request.index_names:
                raise HTTPException(status_code=400, detail="At least one index name is required")

            start_time = time.time()
            results = es_core.semantic_search(request.index_names, request.query, request.top_k)
            query_time = (time.time() - start_time) * 1000  # Convert to milliseconds

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
                "query_time_ms": query_time
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error during semantic search: {str(e)}")

    @staticmethod
    def hybrid_search(
            request: HybridSearchRequest = Body(..., description="Hybrid search request parameters"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Search for similar documents in multiple indices using hybrid search

        Args:
            request: HybridSearchRequest object containing search parameters
            es_core: ElasticSearchCore instance

        Returns:
            Response containing search results, total count, query time, and detailed score information
        """
        try:
            # Validate that query is not empty
            if not request.query.strip():
                raise HTTPException(status_code=400, detail="Search query cannot be empty")

            # Validate index names
            if not request.index_names:
                raise HTTPException(status_code=400, detail="At least one index name is required")

            start_time = time.time()
            results = es_core.hybrid_search(request.index_names, request.query, request.top_k, request.weight_accurate)
            query_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Format results
            formatted_results = []
            for result in results:
                doc = result["document"]
                doc["score"] = result["score"]
                doc["index"] = result["index"]  # Include source index in results
                # Add detailed score information
                doc["score_details"] = {
                    "accurate": result["scores"]["accurate"],
                    "semantic": result["scores"]["semantic"]
                }
                formatted_results.append(doc)

            return {
                "results": formatted_results,
                "total": len(formatted_results),
                "query_time_ms": query_time
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error during hybrid search: {str(e)}")

    @staticmethod
    def health_check(es_core: ElasticSearchCore = Depends(get_es_core)):
        """
        Check the health status of the API and Elasticsearch

        Args:
            es_core: ElasticSearchCore instance

        Returns:
            Response containing health status information
        """
        try:
            # Try to list indices as a health check
            indices = es_core.get_user_indices()
            return {
                "status": "healthy",
                "elasticsearch": "connected",
                "indices_count": len(indices)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

    async def summary_index_name(self,
            index_name: str = Path(..., description="Name of the index to get documents from"),
            batch_size: int = Query(1000, description="Number of documents to retrieve per batch"),
            es_core: ElasticSearchCore = Depends(get_es_core),
            user_id: Optional[str] = Body(None, description="ID of the user delete the knowledge base"),
            tenant_id: Optional[str] = Body(None, description="ID of the tenant"),
            language: str = 'zh'
    ):
        """
        Generate a summary for the specified index based on its content

        Args:
            index_name: Name of the index to summarize
            batch_size: Number of documents to process per batch
            es_core: ElasticSearchCore instance
            user_id: ID of the user requesting the summary
            tenant_id: ID of the tenant
            language: Language of the summary (default: 'zh')

        Returns:
            StreamingResponse containing the generated summary
        """
        try:
            # Get all documents
            if not tenant_id:
                raise HTTPException(status_code=400, detail="Tenant ID is required for summary generation.")
            all_documents = ElasticSearchService.get_random_documents(index_name, batch_size, es_core)
            all_chunks = self._clean_chunks_for_summary(all_documents)
            keywords_dict = calculate_term_weights(all_chunks)
            keywords_for_summary = ""
            for _, key in enumerate(keywords_dict):
                keywords_for_summary = keywords_for_summary + ", " + key

            async def generate_summary():
                token_join = []
                try:
                    for new_token in generate_knowledge_summary_stream(keywords_for_summary, language, tenant_id):
                        if new_token == "END":
                            break
                        else:
                            token_join.append(new_token)
                            yield f"data: {{\"status\": \"success\", \"message\": \"{new_token}\"}}\n\n"
                        await asyncio.sleep(0.1)
                except Exception as e:
                    yield f"data: {{\"status\": \"error\", \"message\": \"{e}\"}}\n\n"

            # Return the flow response
            return StreamingResponse(
                generate_summary(),
                media_type="text/event-stream"
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{str(e)}")

    @staticmethod
    def _clean_chunks_for_summary(all_documents):
        # Only use these three fields for summarization
        all_chunks = ""
        for _, chunk in enumerate(all_documents['documents']):
            all_chunks = all_chunks + "\n" + chunk["title"] + "\n" + chunk["filename"] + "\n" + chunk["content"]
        return all_chunks

    @staticmethod
    def get_random_documents(
            index_name: str = Path(..., description="Name of the index to get documents from"),
            batch_size: int = Query(1000, description="Maximum number of documents to retrieve"),
            es_core: ElasticSearchCore = Depends(get_es_core)
    ):
        """
        Get random sample of documents from the specified index

        Args:
            index_name: Name of the index to get documents from
            batch_size: Maximum number of documents to retrieve, default 1000
            es_core: ElasticSearchCore instance

        Returns:
            Dictionary containing total count and sampled documents
        """
        try:
            # Get total document count
            count_response = es_core.client.count(index=index_name)
            total_docs = count_response['count']

            # Construct the random sampling query using random_score
            query = {
                "size": batch_size,  # Limit return size
                "query": {
                    "function_score": {
                        "query": {"match_all": {}},
                        "random_score": {
                            "seed": int(time.time()),  # Use current time as random seed
                            "field": "_seq_no"
                        }
                    }
                }
            }

            # Execute the query
            response = es_core.client.search(
                index=index_name,
                body=query
            )

            # Extract and process the sampled documents
            sampled_docs = []
            for hit in response['hits']['hits']:
                doc = hit['_source']
                doc['_id'] = hit['_id']  # Add document ID
                sampled_docs.append(doc)

            return {
                "total": total_docs,
                "documents": sampled_docs
            }

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error retrieving random documents from index {index_name}: {str(e)}"
            )

    def change_summary(self,
            index_name: str = Path(..., description="Name of the index to get documents from"),
            summary_result: Optional[str] = Body(description="knowledge base summary"),
            user_id: Optional[str] = Body(None, description="ID of the user delete the knowledge base")
    ):
        """
        Update the summary for the specified Elasticsearch index

        Args:
            index_name: Name of the index to update
            summary_result: New summary content
            user_id: ID of the user making the update

        Returns:
            Dictionary containing status and updated summary information
        """
        try:
            update_data = {
                "knowledge_describe": summary_result,  # Set the new summary
                "updated_by": user_id,
                "index_name": index_name
            }
            update_knowledge_record(update_data)
            return {"status": "success", "message": f"Index {index_name} summary updated successfully", "summary": summary_result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{str(e)}")

    def get_summary(self,
            index_name: str = Path(..., description="Name of the index to get documents from"),
            language: str = 'zh'
    ):
        """
        Get the summary for the specified Elasticsearch index

        Args:
            index_name: Name of the index to get summary from
            language: Language of the summary (default: 'zh')

        Returns:
            Dictionary containing status and summary information
        """
        try:
            knowledge_record = get_knowledge_record({'index_name': index_name})
            if knowledge_record:
                summary_result = knowledge_record["knowledge_describe"]
                success_msg = f"Index {index_name} summary retrieved successfully"
                return {"status": "success", "message": success_msg, "summary": summary_result}
            error_detail = f"Unable to get summary for index {index_name}"
            raise HTTPException(
                status_code=500,
                detail=error_detail
            )
        except Exception as e:
            error_msg = f"Failed to get summary: {str(e)}"
            raise HTTPException(status_code=500, detail=error_msg)