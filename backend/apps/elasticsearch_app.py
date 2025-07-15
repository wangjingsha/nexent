from typing import Dict, List, Any, Optional
import logging

from fastapi import HTTPException, Query, Body, Path, Depends, APIRouter, Header
from consts.model import IndexingResponse, SearchRequest, HybridSearchRequest

from nexent.vector_database.elasticsearch_core import ElasticSearchCore
from services.elasticsearch_service import ElasticSearchService, get_es_core
from services.redis_service import get_redis_service
from utils.auth_utils import get_current_user_id
from services.tenant_config_service import delete_selected_knowledge_by_index_name
from database.attachment_db import delete_file

router = APIRouter(prefix="/indices")
service = ElasticSearchService()

logger = logging.getLogger("elasticsearch_app")

@router.post("/{index_name}")
def create_new_index(
        index_name: str = Path(..., description="Name of the index to create"),
        embedding_dim: Optional[int] = Query(None, description="Dimension of the embedding vectors"),
        es_core: ElasticSearchCore = Depends(get_es_core),
        authorization: Optional[str] = Header(None)
):
    """Create a new vector index and store it in the knowledge table"""
    try:
        user_id, tenant_id = get_current_user_id(authorization)
        return ElasticSearchService.create_index(index_name, embedding_dim, es_core, user_id, tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating index: {str(e)}")


@router.delete("/{index_name}")
async def delete_index(
        index_name: str = Path(..., description="Name of the index to delete"),
        es_core: ElasticSearchCore = Depends(get_es_core),
        authorization: Optional[str] = Header(None)
):
    """Delete an index, its related files in MinIO, and clean up all related Redis records"""
    logger.debug(f"Starting deletion process for knowledge base (index): {index_name}")
    try:
        user_id, tenant_id = get_current_user_id(authorization)

        # 1. Get all files associated with the index from Elasticsearch
        logger.debug(f"Step 1/4: Retrieving file list for index: {index_name}")
        try:
            file_list_result = await ElasticSearchService.list_files(index_name, include_chunks=False, search_redis=True, es_core=es_core)
            files_to_delete = file_list_result.get("files", [])
            logger.debug(f"Found {len(files_to_delete)} files to delete from MinIO for index '{index_name}'.")
        except Exception as e:
            logger.error(f"Failed to retrieve file list for index '{index_name}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to retrieve file list for index {index_name}: {str(e)}")

        # 2. Delete files from MinIO
        minio_deletion_success_count = 0
        minio_deletion_failure_count = 0
        if files_to_delete:
            logger.debug(f"Step 2/4: Starting deletion of {len(files_to_delete)} files from MinIO.")
            for file_info in files_to_delete:
                object_name = file_info.get("path_or_url")
                if not object_name:
                    logger.warning(f"Could not find 'path_or_url' for file entry: {file_info}. Skipping deletion.")
                    minio_deletion_failure_count += 1
                    continue
                
                try:
                    logger.debug(f"Deleting object: '{object_name}' from MinIO for index '{index_name}'")
                    delete_result = delete_file(object_name=object_name)
                    if delete_result.get("success"):
                        logger.debug(f"Successfully deleted object: '{object_name}' from MinIO.")
                        minio_deletion_success_count += 1
                    else:
                        minio_deletion_failure_count += 1
                        error_msg = delete_result.get("error", "Unknown error")
                        logger.error(f"Failed to delete object: '{object_name}' from MinIO. Reason: {error_msg}")
                except Exception as e:
                    minio_deletion_failure_count += 1
                    logger.error(f"An exception occurred while deleting object: '{object_name}' from MinIO. Error: {str(e)}")
            
            logger.info(f"MinIO file deletion summary for index '{index_name}': "
                        f"{minio_deletion_success_count} succeeded, {minio_deletion_failure_count} failed.")
        else:
            logger.debug(f"Step 2/4: No files found in index '{index_name}', skipping MinIO deletion.")

        # 3. Delete from tenant config
        logger.debug(f"Step 3/4: Deleting knowledge base selection records for index '{index_name}'.")
        delete_selected_knowledge_by_index_name(tenant_id=tenant_id, user_id=user_id, index_name=index_name)
        
        # 4. Delete Elasticsearch index
        logger.debug(f"Step 4/4: Deleting Elasticsearch index '{index_name}'.")
        result = await ElasticSearchService.delete_index(index_name, es_core, user_id)

        # Add MinIO cleanup info to the result
        result["minio_cleanup"] = {
            "total_files_found": len(files_to_delete),
            "deleted_count": minio_deletion_success_count,
            "failed_count": minio_deletion_failure_count
        }

        # Then clean up Redis records related to this knowledge base
        try:
            redis_service = get_redis_service()
            redis_cleanup_result = redis_service.delete_knowledgebase_records(index_name)
            logger.debug(f"Redis cleanup for index '{index_name}' completed. "
                        f"Deleted {redis_cleanup_result['total_deleted']} records.")

            # Add Redis cleanup info to the result
            result["redis_cleanup"] = redis_cleanup_result
            result["message"] = (f"Index {index_name} deleted successfully. "
                               f"MinIO: {minio_deletion_success_count} files deleted, {minio_deletion_failure_count} failed. "
                               f"Redis: Cleaned up {redis_cleanup_result['total_deleted']} records.")

            if redis_cleanup_result.get("errors"):
                result["redis_warnings"] = redis_cleanup_result["errors"]
                logger.warning(f"Redis cleanup for index '{index_name}' had warnings: {redis_cleanup_result['errors']}")

        except Exception as redis_error:
            logger.error(f"Redis cleanup failed for index '{index_name}': {str(redis_error)}")
            result["redis_cleanup_error"] = str(redis_error)
            result["message"] = (f"Index {index_name} deleted successfully, "
                               f"but Redis cleanup encountered an error: {str(redis_error)}")

        logger.info(f"Successfully completed deletion process for knowledge base '{index_name}'.")
        return result

    except Exception as e:
        logger.error(f"Error during deletion of index '{index_name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting index: {str(e)}")


@router.get("")
def get_list_indices(
        pattern: str = Query("*", description="Pattern to match index names"),
        include_stats: bool = Query(False, description="Whether to include index stats"),
        es_core: ElasticSearchCore = Depends(get_es_core),
        authorization: Optional[str] = Header(None),
):
    """List all user indices with optional stats"""
    try:
        user_id, tenant_id = get_current_user_id(authorization)
        return ElasticSearchService.list_indices(pattern, include_stats, user_id, tenant_id, es_core)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error get index: {str(e)}")


@router.get("/{index_name}/info")
def get_es_index_info(
        index_name: str = Path(..., description="Name of the index"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """Get comprehensive information about an index including stats, fields, sources and process info"""
    try:
        return ElasticSearchService.get_index_info(index_name, es_core)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{str(e)}")


# Document Operations
@router.post("/{index_name}/documents", response_model=IndexingResponse)
def create_index_documents(
        index_name: str = Path(..., description="Name of the index"),
        data: List[Dict[str, Any]] = Body(..., description="Document List to process"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """
    Index documents with embeddings, creating the index if it doesn't exist.
    Accepts an document list from data processing.
    """
    try:
        return ElasticSearchService.index_documents(index_name, data, es_core)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error indexing documents: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Error indexing documents: {error_msg}")


@router.get("/{index_name}/files")
async def get_index_files(
        index_name: str = Path(..., description="Name of the index"),
        search_redis: bool = Query(True, description="Whether to search Redis to get incomplete files"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """Get all files from an index, including those that are not yet stored in ES"""
    try:
        result = await ElasticSearchService.list_files(index_name, include_chunks=False, search_redis=search_redis, es_core=es_core)
        # Transform result to match frontend expectations
        return {
            "status": "success",
            "files": result.get("files", [])
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error indexing documents: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Error indexing documents: {error_msg}")


@router.delete("/{index_name}/documents")
def delete_documents(
        index_name: str = Path(..., description="Name of the index"),
        path_or_url: str = Query(..., description="Path or URL of documents to delete"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """Delete documents by path or URL and clean up related Redis records"""
    try:
        # First delete the documents using existing service
        result = ElasticSearchService.delete_documents(index_name, path_or_url, es_core)

        # Then clean up Redis records related to this specific document
        try:
            redis_service = get_redis_service()
            redis_cleanup_result = redis_service.delete_document_records(index_name, path_or_url)

            # Add Redis cleanup info to the result
            result["redis_cleanup"] = redis_cleanup_result

            # Update the message to include Redis cleanup info
            original_message = result.get("message", f"Documents deleted successfully")
            result["message"] = (f"{original_message}. "
                               f"Cleaned up {redis_cleanup_result['total_deleted']} Redis records "
                               f"({redis_cleanup_result['celery_tasks_deleted']} tasks, "
                               f"{redis_cleanup_result['cache_keys_deleted']} cache keys).")

            if redis_cleanup_result.get("errors"):
                result["redis_warnings"] = redis_cleanup_result["errors"]

        except Exception as redis_error:
            # Don't fail the whole operation if Redis cleanup fails
            # Just log the error and add a warning to the response
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Redis cleanup failed for document {path_or_url} in index {index_name}: {str(redis_error)}")

            result["redis_cleanup_error"] = str(redis_error)
            original_message = result.get("message", f"Documents deleted successfully")
            result["message"] = (f"{original_message}, "
                               f"but Redis cleanup encountered an error: {str(redis_error)}")

        return result

    except HTTPException as e:
        raise HTTPException(status_code=500, detail=f"Error delete indexing documents: {e}")


# Search Operations

@router.post("/search/accurate")
def accurate_search(
        request: SearchRequest = Body(..., description="Search request parameters"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """Search for documents using fuzzy text matching across multiple indices"""
    try:
      return ElasticSearchService.accurate_search(request, es_core)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{str(e)}")


@router.post("/search/semantic")
def semantic_search(
        request: SearchRequest = Body(..., description="Search request parameters"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """Search for similar documents using vector similarity across multiple indices"""
    try:
       return ElasticSearchService.semantic_search(request, es_core)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{str(e)}")


@router.post("/search/hybrid")
def hybrid_search(
        request: HybridSearchRequest = Body(..., description="Hybrid search request parameters"),
        es_core: ElasticSearchCore = Depends(get_es_core)
):
    """Search for similar documents using hybrid search across multiple indices"""
    try:
        return ElasticSearchService.hybrid_search(request, es_core)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during hybrid search: {str(e)}")


# Health check
@router.get("/health")
def health_check(es_core: ElasticSearchCore = Depends(get_es_core)):
    """Check API and Elasticsearch health"""
    try:
        # Try to list indices as a health check
        return ElasticSearchService.health_check(es_core)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{str(e)}")
