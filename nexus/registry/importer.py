"""Postman Collection Importer and Request Normalizer."""
import re
from typing import List, Dict, Any, Optional, Tuple
from nexus.models.tool import ToolDefinition


def clean_id(text: str) -> str:
    """Generate clean snake_case identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def derive_risk_level(method: str, endpoint: str) -> str:
    """Derive risk level based on HTTP method and endpoint semantics."""
    method = method.upper()
    if method in ["GET", "HEAD", "OPTIONS"]:
        return "LOW"
    # Mutations, payouts, cancellations, deletions are high risk
    return "HIGH"


class PostmanImporter:
    """Imports Postman v2/v2.1 collections and normalizes requests into ToolDefinitions."""

    def __init__(self, service_override: Optional[str] = None):
        self.service_override = service_override

    def import_collection(self, collection_data: Dict[str, Any]) -> List[ToolDefinition]:
        """Walk through nested items and parse all API requests."""
        tools: List[ToolDefinition] = []
        info = collection_data.get("info", {})
        coll_name = info.get("name", "api")
        default_service = clean_id(self.service_override or coll_name)

        items = collection_data.get("item", [])
        self._traverse_items(items, [default_service], tools)
        return tools

    def _traverse_items(self, items: List[Dict[str, Any]], folder_path: List[str], tools: List[ToolDefinition]):
        for item in items:
            name = item.get("name", "Unnamed Request")
            # If it has sub-items, it's a folder
            if "item" in item and isinstance(item["item"], list):
                sub_folder = clean_id(name)
                self._traverse_items(item["item"], folder_path + [sub_folder], tools)
            elif "request" in item:
                tool = self._parse_request_item(item, folder_path)
                if tool:
                    tools.append(tool)

    def _parse_request_item(self, item: Dict[str, Any], folder_path: List[str]) -> Optional[ToolDefinition]:
        name = item.get("name", "Unnamed Tool")
        request = item.get("request", {})
        if not request:
            return None

        method = request.get("method", "GET").upper()
        raw_url, path, query_params = self._parse_url(request.get("url", {}))

        # Folder hierarchy mapping: folder_path[0] is service, folder_path[1] is category
        service = folder_path[0] if len(folder_path) > 0 else "general"
        category = folder_path[1] if len(folder_path) > 1 else (folder_path[0] if folder_path else "general")

        # Description
        description = ""
        raw_desc = request.get("description", item.get("description", ""))
        if isinstance(raw_desc, str):
            description = raw_desc.strip()
        elif isinstance(raw_desc, dict):
            description = raw_desc.get("content", "").strip()

        if not description:
            description = f"{method} {path} - {name}"

        # Build clean tool_id
        tool_id_base = f"{service}_{clean_id(name)}"
        if not tool_id_base.startswith("paypal_") and "paypal" in service:
            pass  # keep existing
        tool_id = tool_id_base

        # Parameters extraction
        properties: Dict[str, Any] = {}
        required: List[str] = []

        # 1. Path parameters
        path_vars = re.findall(r"\{([^}]+)\}|:([a-zA-Z0-9_]+)", path)
        for var_tuple in path_vars:
            var_name = var_tuple[0] or var_tuple[1]
            properties[var_name] = {
                "type": "string",
                "description": f"URL path parameter: {var_name}",
            }
            required.append(var_name)

        # 2. Query parameters
        for qp in query_params:
            q_key = qp.get("key")
            if not q_key:
                continue
            desc = qp.get("description", "")
            if isinstance(desc, dict):
                desc = desc.get("content", "")
            properties[q_key] = {
                "type": "string",
                "description": str(desc) or f"Query parameter {q_key}",
            }
            if not qp.get("disabled", False) and qp.get("value") is not None:
                # If marked required or has essential value
                pass

        # 3. Body schema
        body = request.get("body", {})
        request_schema = {}
        if body and body.get("mode") == "raw":
            raw_text = body.get("raw", "")
            if raw_text:
                request_schema = {"type": "object", "raw_example": raw_text}
                # Extract top-level keys if JSON
                import json
                try:
                    parsed_body = json.loads(raw_text)
                    if isinstance(parsed_body, dict):
                        for b_key, b_val in parsed_body.items():
                            val_type = "string"
                            if isinstance(b_val, (int, float)):
                                val_type = "number"
                            elif isinstance(b_val, bool):
                                val_type = "boolean"
                            elif isinstance(b_val, list):
                                val_type = "array"
                            elif isinstance(b_val, dict):
                                val_type = "object"
                            
                            properties[b_key] = {
                                "type": val_type,
                                "description": f"Request body field {b_key}",
                            }
                except Exception:
                    pass

        parameters_schema = {
            "type": "object",
            "properties": properties,
            "required": sorted(list(set(required))),
        }

        risk_level = derive_risk_level(method, path)

        return ToolDefinition(
            tool_id=tool_id,
            name=name,
            service=service,
            category=category,
            description=description,
            method=method,
            endpoint=path,
            parameters=parameters_schema,
            request_schema=request_schema,
            permission=f"{service}.{method.lower()}",
            risk_level=risk_level,
            is_active=True,
            example_queries=[],
            is_generated=False,
            original_definition=item,
        )

    def _parse_url(self, url_obj: Any) -> Tuple[str, str, List[Dict[str, Any]]]:
        if isinstance(url_obj, str):
            raw = url_obj
            path = "/" + "/".join(url_obj.split("?")[0].split("/")[3:]) if "://" in url_obj else url_obj
            return raw, path, []

        if isinstance(url_obj, dict):
            raw = url_obj.get("raw", "")
            path_segments = url_obj.get("path", [])
            path = "/" + "/".join(str(p) for p in path_segments)
            query = url_obj.get("query", [])
            return raw, path, query

        return "", "/", []


class OpenApiImporter:
    """Parses OpenAPI 3.0/3.1 and Swagger 2.0 specifications into normalized ToolDefinitions."""

    def __init__(self, service_override: Optional[str] = None):
        self.service_override = service_override

    def import_spec(self, spec_data: Dict[str, Any]) -> List[ToolDefinition]:
        """Convert OpenAPI spec paths and methods into ToolDefinitions."""
        tools: List[ToolDefinition] = []
        info = spec_data.get("info", {})
        title = info.get("title", "external_api")
        service = clean_id(self.service_override or title)
        paths = spec_data.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method in ["get", "post", "put", "delete", "patch"]:
                if method not in path_item:
                    continue
                op = path_item[method]
                if not isinstance(op, dict):
                    continue

                tool = self._parse_operation(path, method.upper(), op, service, path_item)
                if tool:
                    tools.append(tool)

        return tools

    def _parse_operation(
        self,
        path: str,
        method: str,
        op: Dict[str, Any],
        service: str,
        path_item: Dict[str, Any],
    ) -> Optional[ToolDefinition]:
        summary = op.get("summary") or op.get("description") or f"{method} {path}"
        name = summary.split("\n")[0][:60].strip()
        tags = op.get("tags", [])
        category = clean_id(tags[0]) if tags else "general"

        # Unique tool ID
        raw_op_id = op.get("operationId") or f"{service}_{method.lower()}_{clean_id(path)}"
        tool_id = clean_id(raw_op_id)

        # Merge path-level and operation-level parameters
        all_params = list(path_item.get("parameters", [])) + list(op.get("parameters", []))
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for p in all_params:
            if not isinstance(p, dict):
                continue
            p_name = p.get("name")
            if not p_name:
                continue
            p_in = p.get("in", "query")
            p_schema = p.get("schema", {})
            p_type = p_schema.get("type", "string")
            p_desc = p.get("description", f"{p_in.title()} parameter: {p_name}")

            properties[p_name] = {
                "type": p_type,
                "description": p_desc,
            }
            if p.get("required") is True:
                required.append(p_name)

        # Request body (OpenAPI 3.x)
        req_body = op.get("requestBody", {})
        if isinstance(req_body, dict):
            content = req_body.get("content", {})
            json_media = content.get("application/json", {})
            body_schema = json_media.get("schema", {})
            if isinstance(body_schema, dict):
                body_props = body_schema.get("properties", {})
                for b_name, b_val in body_props.items():
                    if isinstance(b_val, dict):
                        properties[b_name] = {
                            "type": b_val.get("type", "string"),
                            "description": b_val.get("description", f"Body field: {b_name}"),
                        }
                for r in body_schema.get("required", []):
                    if r not in required:
                        required.append(r)

        parameters_schema = {
            "type": "object",
            "properties": properties,
            "required": sorted(list(set(required))),
        }

        risk_level = derive_risk_level(method, path)

        return ToolDefinition(
            tool_id=tool_id,
            name=name,
            service=service,
            category=category,
            description=op.get("description") or summary,
            method=method,
            endpoint=path,
            parameters=parameters_schema,
            request_schema=req_body,
            permission=f"{service}.{method.lower()}",
            risk_level=risk_level,
            is_active=True,
            example_queries=[],
            is_generated=False,
            original_definition=op,
        )


class UniversalSpecImporter:
    """Universal auto-detecting importer supporting OpenAPI 3.x, Swagger 2.0, and Postman v2/2.1."""

    def __init__(self, service_override: Optional[str] = None):
        self.service_override = service_override
        self.postman_importer = PostmanImporter(service_override=service_override)
        self.openapi_importer = OpenApiImporter(service_override=service_override)

    def import_any(self, spec_data: Any) -> List[ToolDefinition]:
        """Detect format and parse into ToolDefinitions."""
        if isinstance(spec_data, list):
            # Already a list of tool dicts
            return [ToolDefinition.model_validate(t) if isinstance(t, dict) else t for t in spec_data]

        if not isinstance(spec_data, dict):
            raise ValueError("Specification must be a JSON object or array.")

        # OpenAPI / Swagger detection
        if "openapi" in spec_data or "swagger" in spec_data or "paths" in spec_data:
            return self.openapi_importer.import_spec(spec_data)

        # Postman Collection detection
        if "item" in spec_data or ("info" in spec_data and "_postman_id" in spec_data.get("info", {})):
            return self.postman_importer.import_collection(spec_data)

        # Default fallback: check if dictionary of paths or single tool
        if "endpoint" in spec_data and "method" in spec_data:
            return [ToolDefinition.model_validate(spec_data)]

        raise ValueError("Unrecognized specification format. Expected OpenAPI 3.x/Swagger or Postman Collection.")

