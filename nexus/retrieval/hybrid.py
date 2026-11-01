"""Hybrid Retrieval Engine with RRF, Cross-Encoder Reranking, and Conditional LLM Disambiguation."""
import os
import json
import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from nexus.models.tool import ToolDefinition
from nexus.registry.repository import IToolRepository
from nexus.retrieval.bm25 import BM25Index
from nexus.retrieval.chroma_index import ChromaToolIndex
from nexus.retrieval.embedder import get_model_manager
from nexus.storage.redis_client import RedisManager

logger = logging.getLogger("nexus.retrieval")

# Precedence cutoffs
DEFAULT_NO_MATCH_THRESHOLD = -10.0  # Cross-encoder MS-Marco logit cutoff (below -10.0 is noise/unrelated)
AMBIGUITY_MARGIN_DELTA = 0.15     # If top-1 and top-2 cross-encoder scores differ by < 0.15


class HybridRetriever:
    """Multi-stage hybrid retrieval engine."""

    def __init__(
        self,
        repository: IToolRepository,
        chroma_index: Optional[ChromaToolIndex] = None,
        no_match_threshold: float = DEFAULT_NO_MATCH_THRESHOLD,
        redis_mgr: Optional[RedisManager] = None,
    ):
        self.repository = repository
        self.chroma_index = chroma_index or ChromaToolIndex()
        self.bm25_index = BM25Index()
        self.model_manager = get_model_manager()
        self.no_match_threshold = no_match_threshold
        self.redis = redis_mgr or RedisManager.get_instance()
        self._sync_indices()

        # Listen to repository changes to keep indices synchronized
        if hasattr(self.repository, "add_change_listener"):
            self.repository.add_change_listener(self._on_repository_change)

    def _sync_indices(self):
        """Index all active tools into Chroma and BM25."""
        tools = self.repository.list()
        active_tools = [t for t in tools if t.is_active]

        # 1. Sync Chroma
        self.chroma_index.index_tools(active_tools)

        # 2. Build BM25 documents
        bm25_docs: List[Tuple[str, str]] = []
        for t in active_tools:
            # Combine searchable text + example queries for full lexical coverage
            queries_text = " ".join(t.example_queries)
            full_lexical_text = f"{t.name} {t.service} {t.category} {t.method} {t.endpoint} {t.description} {queries_text}"
            bm25_docs.append((t.tool_id, full_lexical_text))
            
        self.bm25_index.index(bm25_docs)

    def _on_repository_change(self, tool_id: str, tool: Optional[ToolDefinition], action: str):
        if action == "DELETE":
            self.chroma_index.delete_tool(tool_id)
        elif action in ["CREATE", "UPDATE"] and tool:
            if tool.is_active:
                self.chroma_index.index_tools([tool], force=True)
            else:
                self.chroma_index.delete_tool(tool_id)
        self._sync_indices()

    def route_service(self, query: str) -> Optional[str]:
        """Hierarchical service router: identifies target service domain if clear."""
        q = query.lower()
        if any(w in q for w in ["invoice", "invoices", "invoicing", "billing template"]):
            return "invoicing"
        if any(w in q for w in ["dispute", "disputes", "chargeback", "claim", "complaint", "appeal"]):
            return "disputes"
        if any(w in q for w in ["payout", "payouts", "batch payout"]):
            return "payouts"
        if any(w in q for w in ["order", "orders", "checkout"]):
            return "orders"
        if any(w in q for w in ["transaction", "sales volume", "balance", "reporting"]):
            return "reporting"
        if any(w in q for w in ["webhook", "listener", "notification"]):
            return "notifications"
        if any(w in q for w in ["refund", "authorize", "authorization", "capture", "void"]):
            return "payments"
        return None

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        session_sticky_tools: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute full hybrid retrieval pipeline with Redis result caching."""
        # Check Redis retrieval cache
        repo_hash = getattr(self.repository, "content_hash", "") or str(self.repository.count())
        sticky_str = ",".join(session_sticky_tools or [])
        cache_raw = f"{query.strip().lower()}|{top_k}|{sticky_str}|{repo_hash}"
        cache_key = f"nexus:retrieval:{hashlib.sha256(cache_raw.encode()).hexdigest()}"

        cached_json = self.redis.get(cache_key)
        if cached_json:
            try:
                cached_data = json.loads(cached_json)
                resolved_tools = [self.repository.get(tid) for tid in cached_data.get("tool_ids", [])]
                active_tools = [t for t in resolved_tools if t and t.is_active]
                if active_tools:
                    logger.debug("Redis retrieval cache hit for query '%s'", query[:40])
                    return {
                        "tools": active_tools,
                        "retrieval_scores": cached_data.get("retrieval_scores", {}),
                        "cross_encoder_scores": cached_data.get("cross_encoder_scores", {}),
                        "llm_confidence": cached_data.get("llm_confidence"),
                        "service_routed": cached_data.get("service_routed"),
                        "cached": True,
                    }
            except Exception as e:
                logger.warning("Failed to decode cached retrieval result: %s", e)

        # 1. Service Routing (Hierarchical pruning)
        service_routed = self.route_service(query)

        # 2. Dense Semantic Retrieval (Chroma)
        dense_results = self.chroma_index.query(query, top_k=20, service_filter=service_routed)
        # If service filter pruned too aggressively and gave empty results, retry globally
        if not dense_results and service_routed:
            dense_results = self.chroma_index.query(query, top_k=20, service_filter=None)

        # 3. Sparse Lexical Retrieval (BM25)
        bm25_results = self.bm25_index.search(query, top_k=20)

        # 4. Reciprocal Rank Fusion (RRF with k=60)
        rrf_scores: Dict[str, float] = {}
        k_const = 60.0

        for rank, (tool_id, _) in enumerate(dense_results):
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0.0) + (1.0 / (k_const + rank + 1))

        for rank, (tool_id, _) in enumerate(bm25_results):
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0.0) + (1.0 / (k_const + rank + 1))

        # Boost session-sticky tools if relevant
        if session_sticky_tools:
            for sticky_id in session_sticky_tools:
                if sticky_id in rrf_scores:
                    rrf_scores[sticky_id] += 0.005  # sticky prior boost

        # Sort by RRF score to select top 12 candidates for cross-encoder rerank
        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:15]
        candidate_ids = [t[0] for t in sorted_rrf]

        if not candidate_ids:
            return {
                "tools": [],
                "retrieval_scores": {},
                "cross_encoder_scores": {},
                "llm_confidence": None,
                "service_routed": service_routed,
            }

        # Fetch candidate ToolDefinitions from registry (Registry is Source of Truth)
        candidate_tools: Dict[str, ToolDefinition] = {}
        for cid in candidate_ids:
            t = self.repository.get(cid)
            if t and t.is_active:
                candidate_tools[cid] = t

        # 5. Cross-Encoder Re-Ranking
        candidate_list = list(candidate_tools.values())
        candidate_texts = [f"{t.name}: {t.description} (Method: {t.method} {t.endpoint})" for t in candidate_list]
        ce_scores_list = self.model_manager.rerank(query, candidate_texts)

        ce_scores: Dict[str, float] = {}
        for tool, score in zip(candidate_list, ce_scores_list):
            ce_scores[tool.tool_id] = score

        # Rank candidates by Cross-Encoder score
        ranked_candidates = sorted(candidate_list, key=lambda t: ce_scores[t.tool_id], reverse=True)

        # 6. Conditional Gemini Disambiguation
        llm_confidence: Optional[float] = None
        if len(ranked_candidates) >= 2:
            top1_score = ce_scores[ranked_candidates[0].tool_id]
            top2_score = ce_scores[ranked_candidates[1].tool_id]
            delta = top1_score - top2_score

            # If margin is narrow and above cutoff, disambiguate
            if delta < AMBIGUITY_MARGIN_DELTA and top1_score > self.no_match_threshold:
                disambiguated = self._conditional_gemini_disambiguate(
                    query, ranked_candidates[0], ranked_candidates[1]
                )
                if disambiguated:
                    winner_id, confidence = disambiguated
                    llm_confidence = confidence
                    if winner_id == ranked_candidates[1].tool_id:
                        # Swap top 1 and top 2
                        ranked_candidates[0], ranked_candidates[1] = ranked_candidates[1], ranked_candidates[0]

        # 7. Apply Precedence Rule: No-Match Threshold
        # Any candidate below threshold is discarded
        qualifying_tools: List[ToolDefinition] = []
        for tool in ranked_candidates:
            score = ce_scores.get(tool.tool_id, -999.0)
            if score >= self.no_match_threshold:
                qualifying_tools.append(tool)

        # Return up to top_k (fewer if fewer qualified, never force a selection)
        final_selection = qualifying_tools[:top_k]

        # Candidate Validation: Ensure every returned tool exists in candidate pool
        validated_tools = [
            t for t in final_selection
            if t.tool_id in candidate_tools
        ]

        out = {
            "tools": validated_tools,
            "retrieval_scores": {t[0]: t[1] for t in sorted_rrf},
            "cross_encoder_scores": ce_scores,
            "llm_confidence": llm_confidence,
            "service_routed": service_routed,
            "cached": False,
        }

        # Cache result in Redis for 15 minutes (900 seconds)
        if validated_tools:
            try:
                cache_payload = {
                    "tool_ids": [t.tool_id for t in validated_tools],
                    "retrieval_scores": out["retrieval_scores"],
                    "cross_encoder_scores": ce_scores,
                    "llm_confidence": llm_confidence,
                    "service_routed": service_routed,
                }
                self.redis.set(cache_key, json.dumps(cache_payload), ex=900)
            except Exception as e:
                logger.warning("Failed to store retrieval result in Redis: %s", e)

        return out

    def _conditional_gemini_disambiguate(
        self,
        query: str,
        candidate_a: ToolDefinition,
        candidate_b: ToolDefinition
    ) -> Optional[Tuple[str, float]]:
        """Call Gemini to disambiguate only between top 2 closely competing candidates."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None

        prompt = f"""You are a precise API tool selector. A user submitted the query:
"{query}"

Two tools are closely matched:
1. Tool A: "{candidate_a.tool_id}" - {candidate_a.name} ({candidate_a.method} {candidate_a.endpoint}): {candidate_a.description}
2. Tool B: "{candidate_b.tool_id}" - {candidate_b.name} ({candidate_b.method} {candidate_b.endpoint}): {candidate_b.description}

Which tool is the exact best match for this request?
Respond in JSON:
{{"selected_tool_id": "<tool_id>", "confidence": 0.0 to 1.0}}
"""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                google_api_key=api_key,
                temperature=0.0
            )
            resp = llm.invoke(prompt)
            txt = resp.content.strip()
            if txt.startswith("```json"):
                txt = txt[7:]
            if txt.endswith("```"):
                txt = txt[:-3]
            parsed = json.loads(txt.strip())
            sel_id = parsed.get("selected_tool_id")
            conf = float(parsed.get("confidence", 0.8))
            if sel_id in [candidate_a.tool_id, candidate_b.tool_id]:
                return sel_id, conf
        except Exception as e:
            logger.warning(f"Conditional disambiguation failed: {e}")
        return None

