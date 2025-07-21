from typing import Optional, Dict, List, Any

from sqlalchemy import func, insert, update, select, and_

from .client import db_client, get_db_session, as_dict
from .db_models import ModelRecord


def create_model_record(model_data: Dict[str, Any], user_id: str, tenant_id: str) -> bool:
    """
    Create a model record

    Args:
        model_data: Dictionary containing model data
        user_id: Reserved parameter for filling created_by and updated_by fields
        tenant_id: Optional tenant ID, defaults to "tenant_id" if None or empty

    Returns:
        bool: Whether the operation was successful
    """
    with get_db_session() as session:
        # Data cleaning
        cleaned_data = db_client.clean_string_values(model_data)

        # Add creation timestamp
        cleaned_data["create_time"] = func.current_timestamp()

        # Add tenant_id to cleaned_data
        if tenant_id is not None:
            cleaned_data["tenant_id"] = tenant_id

        # Build the insert statement
        stmt = insert(ModelRecord).values(cleaned_data)

        # Execute the insert statement
        result = session.execute(stmt)

        return result.rowcount > 0


def update_model_record(model_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> bool:
    """
    Update a model record

    Args:
        model_id: Model ID
        update_data: Dictionary containing update data
        user_id: Reserved parameter for filling updated_by field

    Returns:
        bool: Whether the operation was successful
    """
    with get_db_session() as session:
        # Data cleaning
        cleaned_data = db_client.clean_string_values(update_data)

        # Add update timestamp
        cleaned_data["update_time"] = func.current_timestamp()

        # Add tenant_id to cleaned_data if provided
        if tenant_id is not None:
            cleaned_data["tenant_id"] = tenant_id

        # Build the update statement
        stmt = update(ModelRecord).where(
            ModelRecord.model_id == model_id
        ).values(cleaned_data)

        # Execute the update statement
        result = session.execute(stmt)

        return result.rowcount > 0


def delete_model_record(model_id: int, user_id: str, tenant_id: str) -> bool:
    """
    Delete a model record (soft delete) and update the update timestamp

    Args:
        model_id: Model ID
        user_id: Reserved parameter for filling updated_by field

    Returns:
        bool: Whether the operation was successful
    """
    with get_db_session() as session:
        # Prepare update data for soft delete
        update_data = {
            "delete_flag": 'Y',
            "update_time": func.current_timestamp()
        }

        # Build the update statement
        stmt = update(ModelRecord).where(
            ModelRecord.model_id == model_id
        ).values(update_data)

        stmt = stmt.values(tenant_id=tenant_id)

        # Execute the update statement
        result = session.execute(stmt)

        # Check if any rows were affected
        return result.rowcount > 0


def get_model_records(filters: Optional[Dict[str, Any]], tenant_id: str) -> List[Dict[str, Any]]:
    """
    Get a list of model records

    Args:
        filters: Dictionary of filter conditions, optional parameter

    Returns:
        List[Dict[str, Any]]: List of model records
    """
    with get_db_session() as session:
        # Base query
        stmt = select(ModelRecord).where(ModelRecord.delete_flag == 'N')

        if tenant_id:
            stmt = stmt.where(ModelRecord.tenant_id == tenant_id)

        # Add filter conditions
        if filters:
            conditions = []
            for key, value in filters.items():
                if value is None:
                    conditions.append(getattr(ModelRecord, key).is_(None))
                else:
                    conditions.append(getattr(ModelRecord, key) == value)
            stmt = stmt.where(and_(*conditions))

        # Execute the query
        records = session.scalars(stmt).all()

        # Convert SQLAlchemy model instances to dictionaries
        return [as_dict(record) for record in records]


def get_model_by_display_name(display_name: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a model record by display name

    Args:
        display_name: Model display name
        tenant_id: 
    """
    filters = {'display_name': display_name}

    records = get_model_records(filters, tenant_id)
    if not records:
        return None

    model = records[0]
    return model

def get_model_id_by_display_name(display_name: str, tenant_id: str) -> Optional[int]:
    """
    Get a model ID by display name

    Args:
        display_name: Model display name 
        tenant_id: tenant_id

    Returns:
        Optional[int]: Model ID
    """
    model = get_model_by_display_name(display_name, tenant_id)
    return model["model_id"] if model else None


def get_model_by_model_id(model_id: int, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get a model record using native SQLAlchemy query

    Args:
        model_id (int): Model ID
        tenant_id (Optional[str]): Tenant ID, optional

    Returns:
        Optional[Dict[str, Any]]: Model record as a dictionary, or None if not found
    """
    with get_db_session() as session:
        # Build base query
        stmt = select(ModelRecord).where(
            ModelRecord.model_id == model_id,
            ModelRecord.delete_flag == 'N'
        )
        
        # If tenant ID is provided, add tenant filter
        if tenant_id:
            stmt = stmt.where(ModelRecord.tenant_id == tenant_id)
            
        # Execute query
        result = session.scalars(stmt).first()
        
        # If no record is found, return None
        if result is None:
            return None
            
        # Convert SQLAlchemy model object to dictionary
        result_dict = {key: value for key, value in result.__dict__.items() 
                      if not key.startswith('_')}
        
        return result_dict
