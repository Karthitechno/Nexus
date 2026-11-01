"""Dynamic LangChain StructuredTool and Pydantic Schema Generator."""
from typing import Dict, Any, Type, Optional, Callable
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool
from nexus.models.tool import ToolDefinition


PYTHON_TYPE_MAP = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def create_pydantic_schema_from_tool(tool: ToolDefinition) -> Type[BaseModel]:
    """Dynamically generate a Pydantic Model from the tool's JSON Schema."""
    fields: Dict[str, Any] = {}
    
    props = tool.parameters.get("properties", {}) if isinstance(tool.parameters, dict) else {}
    required_set = set(tool.parameters.get("required", [])) if isinstance(tool.parameters, dict) else set()

    for param_name, param_info in props.items():
        json_type = param_info.get("type", "string")
        py_type = PYTHON_TYPE_MAP.get(json_type, str)
        desc = param_info.get("description", "")
        
        is_required = param_name in required_set
        
        if is_required:
            fields[param_name] = (py_type, Field(..., description=desc))
        else:
            default_val = param_info.get("default", None)
            fields[param_name] = (Optional[py_type], Field(default=default_val, description=desc))

    # Fallback if tool had no defined parameters
    if not fields:
        fields["notes"] = (Optional[str], Field(default=None, description="Optional execution notes"))

    model_name = f"{tool.tool_id.title().replace('_', '')}Schema"
    return create_model(model_name, **fields)


def convert_to_structured_tool(
    tool: ToolDefinition,
    executor_func: Optional[Callable[..., Any]] = None,
    schema_cls: Optional[Type[BaseModel]] = None
) -> StructuredTool:
    """Transform ToolDefinition into a LangChain StructuredTool with dynamic schema."""
    args_schema = schema_cls or create_pydantic_schema_from_tool(tool)
    
    def default_run(**kwargs):
        return {"tool_id": tool.tool_id, "status": "prepared", "args": kwargs}

    run_func = executor_func or default_run

    return StructuredTool(
        name=tool.tool_id,
        description=tool.description,
        args_schema=args_schema,
        func=run_func,
    )
