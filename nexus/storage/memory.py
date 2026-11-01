"""NEXUS Inter-Agent Entity Memory Blackboard & Pass-by-Reference Store.

Provides:
1. Deterministic Entity Extraction & Hot Blackboard:
   Stores primary IDs (invoice_id, dispute_id, order_id, amount, recipient)
   per thread_id with O(1) <1ms retrieval via Redis (with local dict fallback).
2. Pass-by-Reference Payload Store:
   Prevents LLM token explosion by offloading large tool outputs to Redis/blobs
   and passing lightweight reference tokens (ref:blob_...).
3. Recency Decay & Cross-Agent Variable Binding:
   Allows follow-up turns ("now send it", "dispute that payment") to bind
   target entities without prompting for clarification or re-asking the user.
"""
import uuid
import json
import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from nexus.storage.redis_client import RedisManager

logger = logging.getLogger("nexus.storage.memory")

# Common PayPal / API ID Regex patterns
INVOICE_ID_PATTERN = re.compile(r"(INV2-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})", re.IGNORECASE)
DISPUTE_ID_PATTERN = re.compile(r"(PP-D-[0-9]+|PP-R-[0-9]+)", re.IGNORECASE)
ORDER_ID_PATTERN = re.compile(r"([0-9A-Z]{17})")


class EntityMemoryStore:
    """Inter-agent blackboard maintaining entity context and reference pointers."""

    _instance: Optional["EntityMemoryStore"] = None

    def __init__(self, redis_mgr: Optional[RedisManager] = None):
        self.redis = redis_mgr or RedisManager.get_instance()
        # In-memory fast fallback when Redis is offline
        self._local_entities: Dict[str, Dict[str, Any]] = {}
        self._local_blobs: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls, redis_mgr: Optional[RedisManager] = None) -> "EntityMemoryStore":
        if cls._instance is None:
            cls._instance = cls(redis_mgr=redis_mgr)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    # --- 1. Deterministic Entity Blackboard (O(1) Redis / In-Memory) ---

    def set_entity(self, thread_id: str, key: str, value: Any, ttl: int = 7200) -> None:
        """Set a single entity in thread blackboard."""
        if not thread_id or not key or value is None:
            return

        # Always update local memory
        if thread_id not in self._local_entities:
            self._local_entities[thread_id] = {}
        self._local_entities[thread_id][key] = value

        # Sync to Redis if available
        if self.redis.is_available():
            try:
                redis_key = f"nexus:context:{thread_id}"
                self.redis.hset(redis_key, {key: json.dumps(value)})
                self.redis.expire(redis_key, ttl)
            except Exception as e:
                logger.warning("Redis set_entity failed for %s.%s: %s", thread_id, key, e)

    def get_entity(self, thread_id: str, key: str) -> Optional[Any]:
        """Get an entity from thread blackboard."""
        if not thread_id or not key:
            return None

        # Check Redis first if available
        if self.redis.is_available():
            try:
                redis_key = f"nexus:context:{thread_id}"
                raw = self.redis.hgetall(redis_key)
                if key in raw:
                    return json.loads(raw[key])
            except Exception as e:
                logger.warning("Redis get_entity failed for %s.%s: %s", thread_id, key, e)

        # Fallback to local memory
        return self._local_entities.get(thread_id, {}).get(key)

    def get_entity_context(self, thread_id: str) -> Dict[str, Any]:
        """Fetch complete active entity context for a thread."""
        if not thread_id:
            return {}

        context: Dict[str, Any] = {}

        # 1. Local memory base
        if thread_id in self._local_entities:
            context.update(self._local_entities[thread_id])

        # 2. Redis overlay
        if self.redis.is_available():
            try:
                redis_key = f"nexus:context:{thread_id}"
                raw = self.redis.hgetall(redis_key)
                for k, v in raw.items():
                    try:
                        context[k] = json.loads(v)
                    except Exception:
                        context[k] = v
            except Exception as e:
                logger.warning("Redis get_entity_context failed for %s: %s", thread_id, e)

        return context

    def clear_context(self, thread_id: str) -> None:
        """Clear blackboard context for a thread."""
        if thread_id in self._local_entities:
            del self._local_entities[thread_id]
        if self.redis.is_available():
            try:
                self.redis.delete(f"nexus:context:{thread_id}")
            except Exception:
                pass

    # --- 2. Deterministic Tool Output Entity Harvester ---

    def extract_and_record_entities(
        self,
        thread_id: str,
        tool_id: str,
        result_data: Dict[str, Any],
        ttl: int = 7200,
    ) -> Dict[str, Any]:
        """Deterministically extracts primary domain entities from execution output.
        
        Zero LLM latency: analyzes structured response dict and regex-matches IDs.
        Records into blackboard and returns the newly harvested entities.
        """
        if not thread_id or not isinstance(result_data, dict):
            return {}

        resp = result_data.get("response") or {}
        extracted: Dict[str, Any] = {}

        # Universal Dynamic Entity Harvester: scans any API dictionary for IDs, emails, and amounts
        if isinstance(resp, dict):
            for k, v in resp.items():
                if isinstance(v, (str, int)) and v:
                    val_str = str(v).strip()
                    if k.endswith("_id") or k == "id" or k.endswith("Id"):
                        extracted[k] = val_str
                        extracted[f"last_{k}"] = val_str
                        extracted["last_active_id"] = val_str
                    elif k in ("email", "recipient", "recipient_email", "username", "user_id"):
                        extracted[k] = val_str
                        extracted[f"last_{k}"] = val_str
                    elif k in ("amount", "total", "price", "value") and not isinstance(v, bool):
                        extracted["last_amount"] = val_str
                        extracted[k] = val_str
            
            # Dynamic URI path segment extractor (e.g., https://.../resource/ID)
            for uri_key in ("href", "url", "link"):
                if uri_key in resp and isinstance(resp[uri_key], str):
                    seg = resp[uri_key].rstrip("/").split("/")[-1]
                    if seg and "?" not in seg and len(seg) > 3:
                        extracted["last_active_id"] = seg
                        extracted["resource_id"] = seg

        # 1. Direct Invoice ID extraction
        # PayPal returns either {"id": "INV2-..."} or {"href": ".../invoices/INV2-..."}
        inv_id = None
        if isinstance(resp, dict):
            if "id" in resp and str(resp["id"]).startswith("INV2-"):
                inv_id = str(resp["id"])
            elif "href" in resp:
                m = INVOICE_ID_PATTERN.search(str(resp["href"]))
                if m:
                    inv_id = m.group(1)

        if not inv_id and isinstance(result_data.get("message"), str):
            m = INVOICE_ID_PATTERN.search(result_data["message"])
            if m:
                inv_id = m.group(1)

        if inv_id:
            extracted["last_invoice_id"] = inv_id
            extracted["invoice_id"] = inv_id
            extracted["last_active_id"] = inv_id

        # 2. Dispute ID extraction
        dispute_id = None
        if isinstance(resp, dict):
            if "dispute_id" in resp:
                dispute_id = str(resp["dispute_id"])
            elif "id" in resp and str(resp["id"]).startswith("PP-"):
                dispute_id = str(resp["id"])

        if not dispute_id and isinstance(result_data.get("message"), str):
            m = DISPUTE_ID_PATTERN.search(result_data["message"])
            if m:
                dispute_id = m.group(1)

        if dispute_id:
            extracted["last_dispute_id"] = dispute_id
            extracted["dispute_id"] = dispute_id
            extracted["last_active_id"] = dispute_id

        # 3. Order / Payment Capture ID extraction
        order_id = None
        if isinstance(resp, dict):
            if "order_id" in resp:
                order_id = str(resp["order_id"])
            elif "capture_id" in resp:
                extracted["last_capture_id"] = str(resp["capture_id"])
                extracted["capture_id"] = str(resp["capture_id"])
                extracted["last_active_id"] = str(resp["capture_id"])
            elif "id" in resp and not inv_id and not dispute_id:
                # Top level generic ID
                extracted["last_active_id"] = str(resp["id"])

        if order_id:
            extracted["last_order_id"] = order_id
            extracted["order_id"] = order_id
            extracted["last_active_id"] = order_id

        # 4. Amount extraction
        amount = None
        if isinstance(resp, dict):
            amt_obj = resp.get("amount")
            if isinstance(amt_obj, dict) and "value" in amt_obj:
                amount = amt_obj["value"]
            elif isinstance(amt_obj, (int, float, str)):
                amount = str(amt_obj)

        if amount:
            extracted["last_amount"] = amount

        # 5. Recipient extraction
        recipient = None
        if isinstance(resp, dict):
            primary_recipients = resp.get("primary_recipients")
            if isinstance(primary_recipients, list) and primary_recipients:
                b_info = primary_recipients[0].get("billing_info", {})
                recipient = b_info.get("email_address")
            elif "recipient_email" in resp:
                recipient = resp["recipient_email"]

        if recipient:
            extracted["last_recipient"] = recipient

        # 6. Service / Tool provenance
        extracted["last_tool_executed"] = tool_id

        # Save all extracted entities to blackboard
        for k, v in extracted.items():
            self.set_entity(thread_id, k, v, ttl=ttl)

        logger.info(
            "Harvested entities for thread '%s' from %s: %s",
            thread_id, tool_id, list(extracted.keys())
        )
        return extracted

    # --- 3. Pass-by-Reference Store for Large Payloads ---

    def store_payload(
        self,
        thread_id: str,
        payload: Any,
        summary: Optional[str] = None,
        ttl: int = 3600,
    ) -> Dict[str, Any]:
        """Stores large payloads in blob store and returns a lightweight reference pointer.
        
        Prevents LLM prompt context explosion.
        """
        blob_id = f"ref:blob_{uuid.uuid4().hex[:12]}"
        serialized = json.dumps(payload)

        # Store in local memory
        self._local_blobs[blob_id] = payload

        # Store in Redis if available
        if self.redis.is_available():
            try:
                self.redis.set(f"nexus:blob:{blob_id}", serialized, ex=ttl)
            except Exception as e:
                logger.warning("Failed to store blob in Redis: %s", e)

        # Store pointer in thread context
        self.set_entity(thread_id, "last_payload_ref", blob_id, ttl=ttl)

        return {
            "reference": blob_id,
            "size_bytes": len(serialized),
            "summary": summary or f"Stored payload reference ({len(serialized)} bytes)",
        }

    def resolve_payload(self, reference: str) -> Optional[Any]:
        """Dereferences a pass-by-reference token into its full payload."""
        if not reference or not isinstance(reference, str) or not reference.startswith("ref:"):
            return None

        # Check local memory
        if reference in self._local_blobs:
            return self._local_blobs[reference]

        # Check Redis
        if self.redis.is_available():
            try:
                raw = self.redis.get(f"nexus:blob:{reference}")
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning("Failed to resolve payload reference from Redis: %s", e)

        return None

