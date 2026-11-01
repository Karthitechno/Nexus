"""Redis-backed CheckpointSaver for LangGraph State Machines.

Persists LangGraph thread states, channel blobs, and pending writes in Redis
using standard Redis hash/binary keys (no Redis Stack / C-modules required).
Falls back to MemorySaver if Redis is unavailable.
"""
import pickle
import logging
from typing import Dict, Any, Optional, Iterator, Sequence, Tuple
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    get_checkpoint_id,
    get_checkpoint_metadata,
    WRITES_IDX_MAP,
)
from langgraph.checkpoint.memory import MemorySaver
from nexus.storage.redis_client import RedisManager

logger = logging.getLogger("nexus.checkpointer")

CHECKPOINT_TTL = 7 * 86400  # 7 days


class RedisCheckpointSaver(BaseCheckpointSaver):
    """Durable Redis checkpointer for standard Redis (no Redis Stack required)."""

    def __init__(self, redis_mgr: Optional[RedisManager] = None):
        super().__init__()
        self.redis_mgr = redis_mgr or RedisManager.get_instance()
        self.fallback = MemorySaver(serde=self.serde)

    def _redis_client(self):
        # We need raw bytes connection for serialized state blobs
        if not self.redis_mgr.is_available():
            return None
        import redis
        return redis.Redis.from_url(self.redis_mgr.redis_url, decode_responses=False)

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        client = self._redis_client()
        if not client:
            return self.fallback.get_tuple(config)

        try:
            thread_id: str = config["configurable"]["thread_id"]
            checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
            cp_hash_key = f"nexus:checkpoints:{thread_id}:{checkpoint_ns}"

            checkpoint_id = get_checkpoint_id(config)
            if not checkpoint_id:
                # Find latest checkpoint_id from Redis hash keys
                all_ids = [k.decode() if isinstance(k, bytes) else k for k in client.hkeys(cp_hash_key)]
                if not all_ids:
                    return None
                checkpoint_id = max(all_ids)

            raw_saved = client.hget(cp_hash_key, checkpoint_id)
            if not raw_saved:
                return None

            checkpoint_data, metadata_data, parent_checkpoint_id = pickle.loads(raw_saved)
            checkpoint_: Checkpoint = self.serde.loads_typed(checkpoint_data)

            # Load channel blobs from Redis
            channel_values = self._load_blobs_redis(client, thread_id, checkpoint_ns, checkpoint_["channel_versions"])

            # Load pending writes from Redis
            writes_hash_key = f"nexus:writes:{thread_id}:{checkpoint_ns}:{checkpoint_id}"
            raw_writes = client.hgetall(writes_hash_key)
            writes = [pickle.loads(v) for v in raw_writes.values()]

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint={
                    **checkpoint_,
                    "channel_values": channel_values,
                },
                metadata=self.serde.loads_typed(metadata_data),
                pending_writes=[
                    (id, c, self.serde.loads_typed(v)) for id, c, v, _ in writes
                ],
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_checkpoint_id,
                        }
                    }
                    if parent_checkpoint_id
                    else None
                ),
            )
        except Exception as e:
            logger.warning("Redis get_tuple failed, falling back to memory: %s", e)
            return self.fallback.get_tuple(config)

    def _load_blobs_redis(self, client, thread_id: str, checkpoint_ns: str, versions: ChannelVersions) -> Dict[str, Any]:
        blobs_hash_key = f"nexus:blobs:{thread_id}:{checkpoint_ns}"
        if not versions:
            return {}
        fields = [f"{k}:{v}" for k, v in versions.items()]
        raw_vals = client.hmget(blobs_hash_key, fields)
        out = {}
        for (k, v), raw_bytes in zip(versions.items(), raw_vals):
            if raw_bytes is not None:
                typed_data = pickle.loads(raw_bytes)
                if isinstance(typed_data, tuple) and typed_data[0] != "empty":
                    out[k] = self.serde.loads_typed(typed_data)
        return out

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        client = self._redis_client()
        if not client:
            return self.fallback.put(config, checkpoint, metadata, new_versions)

        try:
            c = checkpoint.copy()
            thread_id: str = config["configurable"]["thread_id"]
            checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
            checkpoint_id = checkpoint["id"]

            values: Dict[str, Any] = c.pop("channel_values")

            # 1. Store blobs in Redis
            blobs_hash_key = f"nexus:blobs:{thread_id}:{checkpoint_ns}"
            blob_mapping = {}
            for k, v in new_versions.items():
                typed_val = self.serde.dumps_typed(values[k]) if k in values else ("empty", b"")
                blob_mapping[f"{k}:{v}"] = pickle.dumps(typed_val)

            if blob_mapping:
                client.hset(blobs_hash_key, mapping=blob_mapping)
                client.expire(blobs_hash_key, CHECKPOINT_TTL)

            # 2. Store checkpoint in Redis
            cp_hash_key = f"nexus:checkpoints:{thread_id}:{checkpoint_ns}"
            saved_tuple = (
                self.serde.dumps_typed(c),
                self.serde.dumps_typed(get_checkpoint_metadata(config, metadata)),
                config["configurable"].get("checkpoint_id"),
            )
            client.hset(cp_hash_key, checkpoint_id, pickle.dumps(saved_tuple))
            client.expire(cp_hash_key, CHECKPOINT_TTL)

            return {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            }
        except Exception as e:
            logger.warning("Redis put failed, saving to memory fallback: %s", e)
            return self.fallback.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        client = self._redis_client()
        if not client:
            return self.fallback.put_writes(config, writes, task_id, task_path)

        try:
            thread_id: str = config["configurable"]["thread_id"]
            checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
            checkpoint_id = config["configurable"]["checkpoint_id"]
            writes_hash_key = f"nexus:writes:{thread_id}:{checkpoint_ns}:{checkpoint_id}"

            writes_mapping = {}
            for idx, (c, v) in enumerate(writes):
                field_idx = WRITES_IDX_MAP.get(c, idx)
                field_key = f"{task_id}:{field_idx}"
                item = (
                    task_id,
                    c,
                    self.serde.dumps_typed(v),
                    task_path,
                )
                writes_mapping[field_key] = pickle.dumps(item)

            if writes_mapping:
                client.hset(writes_hash_key, mapping=writes_mapping)
                client.expire(writes_hash_key, CHECKPOINT_TTL)
        except Exception as e:
            logger.warning("Redis put_writes failed: %s", e)
            self.fallback.put_writes(config, writes, task_id, task_path)

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        # For listing, fall back to in-memory or query Redis keys
        client = self._redis_client()
        if not client:
            yield from self.fallback.list(config, filter=filter, before=before, limit=limit)
            return

        try:
            thread_id = config["configurable"]["thread_id"] if config else None
            checkpoint_ns = config["configurable"].get("checkpoint_ns", "") if config else ""
            if not thread_id:
                yield from self.fallback.list(config, filter=filter, before=before, limit=limit)
                return

            cp_hash_key = f"nexus:checkpoints:{thread_id}:{checkpoint_ns}"
            raw_all = client.hgetall(cp_hash_key)
            sorted_keys = sorted(
                [k.decode() if isinstance(k, bytes) else k for k in raw_all.keys()],
                reverse=True
            )

            count = 0
            for cid in sorted_keys:
                if limit is not None and count >= limit:
                    break
                tup = self.get_tuple({
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": cid,
                    }
                })
                if tup:
                    yield tup
                    count += 1
        except Exception as e:
            logger.warning("Redis list failed, falling back to memory: %s", e)
            yield from self.fallback.list(config, filter=filter, before=before, limit=limit)
