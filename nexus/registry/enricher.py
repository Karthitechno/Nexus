"""Tool Ingestion Enrichment with Gemini and Local Caching."""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from nexus.models.tool import ToolDefinition

logger = logging.getLogger("nexus.enricher")


class ToolEnricher:
    """Enriches tool definitions with clean descriptions and 5 to 10 example queries."""

    def __init__(self, cache_file: str = "data/cache/enrichment_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save enrichment cache: {e}")

    def enrich_tools(self, tools: List[ToolDefinition], force: bool = False) -> List[ToolDefinition]:
        """Enrich a batch of tools using Gemini if configured, otherwise using deterministic patterns."""
        api_key = os.getenv("GOOGLE_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        llm = None
        if api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=api_key,
                    temperature=0.0
                )
            except Exception as e:
                logger.warning(f"Failed to initialize ChatGoogleGenerativeAI: {e}")

        for tool in tools:
            # Check if already enriched with queries
            if not force and tool.example_queries and len(tool.example_queries) >= 5:
                continue

            # Check persistent cache
            cache_key = f"{tool.method}_{tool.endpoint}_{tool.name}"
            if not force and cache_key in self._cache:
                cached = self._cache[cache_key]
                tool.description = cached.get("description", tool.description)
                tool.example_queries = cached.get("example_queries", tool.example_queries)
                tool.is_generated = True
                continue

            # If LLM available, call Gemini
            if llm:
                enriched_data = self._enrich_single_gemini(llm, tool)
                if enriched_data:
                    tool.description = enriched_data.get("description", tool.description)
                    tool.example_queries = enriched_data.get("example_queries", [])
                    tool.is_generated = True
                    self._cache[cache_key] = enriched_data
                    continue

            # Deterministic fallback enrichment
            fallback_data = self._enrich_single_deterministic(tool)
            tool.description = fallback_data["description"]
            tool.example_queries = fallback_data["example_queries"]
            tool.is_generated = True
            self._cache[cache_key] = fallback_data

        self._save_cache()
        return tools

    def _enrich_single_gemini(self, llm, tool: ToolDefinition) -> Optional[Dict[str, Any]]:
        prompt = f"""You are an API tool documentation expert. Analyze the following API endpoint and produce a JSON response with:
1. "description": A concise, accurate 1-2 sentence description of what the tool does and when to call it.
2. "example_queries": A list of 6 to 8 realistic, diverse natural language queries that a user or developer would say in a chat to invoke this tool. Include variations (imperative, conversational, specific, with parameters).

Tool Information:
- Tool ID: {tool.tool_id}
- Name: {tool.name}
- Method: {tool.method}
- Endpoint: {tool.endpoint}
- Service: {tool.service}
- Category: {tool.category}
- Existing description: {tool.description}
- Parameter Schema: {json.dumps(tool.parameters)}

Respond ONLY with valid JSON matching:
{{"description": "...", "example_queries": ["...", "..."]}}
"""
        try:
            response = llm.invoke(prompt)
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            parsed = json.loads(content.strip())
            if "description" in parsed and "example_queries" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Gemini enrichment failed for {tool.tool_id}: {e}")
        return None

    def _enrich_single_deterministic(self, tool: ToolDefinition) -> Dict[str, Any]:
        """High-quality deterministic query generation for verified APIs."""
        action = tool.name.lower()
        method = tool.method.upper()
        path = tool.endpoint.lower()
        service = tool.service.lower()
        
        # Build clean description
        clean_desc = tool.description
        if not clean_desc or clean_desc == f"{method} {tool.endpoint} - {tool.name}":
            clean_desc = f"{method} request for {tool.name} within {tool.service} service."

        # Generate realistic user queries based on endpoint structure
        queries: List[str] = []
        clean_name = tool.name.replace("PayPal", "").strip()
        
        queries.append(f"{clean_name}")
        queries.append(f"How do I {action}?")
        queries.append(f"Execute {clean_name} for my account")
        
        if "list" in action or method == "GET":
            queries.append(f"Show all {clean_name.replace('List', '').strip()}")
            queries.append(f"Get a list of {tool.category}")
            queries.append(f"Fetch {clean_name.lower()}")
        elif "create" in action or method == "POST":
            queries.append(f"Create a new {tool.category}")
            queries.append(f"Submit and initiate {clean_name.lower()}")
            queries.append(f"Please generate {tool.category}")
        elif "delete" in action or method == "DELETE":
            queries.append(f"Remove this {tool.category}")
            queries.append(f"Delete {tool.category} by ID")
        elif "update" in action or method == "PUT":
            queries.append(f"Update settings for {tool.category}")
            queries.append(f"Modify existing {tool.category}")

        queries.append(f"Run {method} on {tool.endpoint}")
        return {
            "description": clean_desc,
            "example_queries": queries[:8]
        }

