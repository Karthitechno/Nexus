"""Generic API Executor for NEXUS - resolves endpoint from registry, never from LLM."""
import os, uuid, time, logging, json
import httpx
from typing import Any, Dict, Optional

from nexus.registry.repository import IToolRepository
from nexus.executor.oauth import PayPalOAuthManager
from nexus.executor.logs import ExecutionLogRepository, ExecutionLog
from nexus.storage.redis_client import RedisManager
from nexus.storage.memory import EntityMemoryStore

logger = logging.getLogger("nexus.executor")

IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT"}
MAX_RETRIES = 3
BACKOFF_BASE = 1.0


class GenericExecutor:
    def __init__(
        self,
        repository: IToolRepository,
        log_repo: ExecutionLogRepository = None,
        redis_mgr: RedisManager = None,
        memory_store: EntityMemoryStore = None,
    ):
        self.repository = repository
        self.log_repo = log_repo or ExecutionLogRepository()
        self.redis = redis_mgr or RedisManager.get_instance()
        self.oauth = PayPalOAuthManager(redis_mgr=self.redis)
        self.memory_store = memory_store or EntityMemoryStore.get_instance(redis_mgr=self.redis)

    def execute(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        request_id: str = None,
        thread_id: str = None,
    ) -> Dict[str, Any]:
        request_id = request_id or str(uuid.uuid4())
        start = time.time()

        # 1. Resolve tool from registry (endpoint from registry, not LLM)
        tool = self.repository.get(tool_id)
        if not tool:
            return self._error_result(tool_id, request_id, "TOOL_NOT_FOUND",
                                      f"Tool '{tool_id}' not found in registry.", start)
        if not tool.is_active:
            return self._error_result(tool_id, request_id, "TOOL_DISABLED",
                                      f"Tool '{tool_id}' is currently disabled.", start)

        # 2. Check credentials
        if not self.oauth.is_configured():
            latency = (time.time() - start) * 1000
            result = {
                "tool_id": tool_id,
                "status": "NOT_CONFIGURED",
                "response": None,
                "message": "Live execution not configured: PayPal credentials absent from environment.",
                "request_id": request_id,
                "latency_ms": latency,
            }
            self._log(tool_id, request_id, "NOT_CONFIGURED", latency, "credentials_missing")
            return result

        # 3. Build URL (endpoint from registry, base URL from env)
        base_url = self.oauth.base_url.rstrip("/")
        endpoint = tool.endpoint
        # Resolve path parameters
        path_params = {k: v for k, v in parameters.items()
                       if f"{{{k}}}" in endpoint}
        for key, val in path_params.items():
            endpoint = endpoint.replace(f"{{{key}}}", str(val))

        url = base_url + endpoint
        method = tool.method.upper()

        # 4. Split params into query vs body
        props = tool.parameters.get("properties", {}) if isinstance(tool.parameters, dict) else {}
        query_params = {}
        body_params = {}
        for k, v in parameters.items():
            if k in path_params:
                continue
            p_def = props.get(k, {})
            location = p_def.get("location") if isinstance(p_def, dict) else None
            if method in ("POST", "PUT", "PATCH"):
                if location == "query":
                    query_params[k] = v
                else:
                    body_params[k] = v
            elif method == "GET":
                query_params[k] = v
            else:
                body_params[k] = v

        # Payload normalizer for standard PayPal workflows
        if endpoint == "/v2/invoicing/invoices" and method == "POST":
            # 1. detail
            if "detail" not in body_params or not isinstance(body_params["detail"], dict):
                cur = body_params.pop("currency", "USD")
                body_params["detail"] = {
                    "currency_code": cur,
                    "invoice_number": f"INV-{uuid.uuid4().hex[:8]}",
                    "invoice_date": time.strftime("%Y-%m-%d"),
                }
            else:
                detail = body_params["detail"]
                detail.setdefault("currency_code", "USD")
                detail.setdefault("invoice_number", f"INV-{uuid.uuid4().hex[:8]}")
                detail.setdefault("invoice_date", time.strftime("%Y-%m-%d"))

            # 2. primary_recipients
            if "primary_recipients" not in body_params:
                email = body_params.pop("recipient_email", None) or body_params.pop("recipient", "customer@example.com")
                body_params["primary_recipients"] = [
                    {"billing_info": {"email_address": email}}
                ]

            # 3. items
            cur = body_params.get("detail", {}).get("currency_code", "USD")
            if "items" not in body_params or not body_params["items"]:
                amt = body_params.pop("amount", 50.0)
                body_params["items"] = [
                    {
                        "name": "Services",
                        "quantity": "1",
                        "unit_amount": {
                            "currency_code": cur,
                            "value": f"{float(amt):.2f}"
                        }
                    }
                ]
            else:
                # Sanitize existing items: PayPal requires name, quantity, unit_amount
                for item in body_params["items"]:
                    if "name" not in item:
                        item["name"] = "Services"
                    if "quantity" not in item:
                        item["quantity"] = "1"
                    if "unit_amount" not in item:
                        amt_val = item.pop("amount", None)
                        if isinstance(amt_val, dict):
                            val = amt_val.get("value", 50.0)
                            c = amt_val.get("currency_code", cur)
                            item["unit_amount"] = {"currency_code": c, "value": f"{float(val):.2f}"}
                        elif amt_val is not None:
                            item["unit_amount"] = {"currency_code": cur, "value": f"{float(amt_val):.2f}"}
                        else:
                            item["unit_amount"] = {"currency_code": cur, "value": "50.00"}
                    else:
                        ua = item["unit_amount"]
                        if isinstance(ua, dict):
                            ua.setdefault("currency_code", cur)
                            if "value" in ua:
                                ua["value"] = f"{float(ua['value']):.2f}"
        elif "/v2/invoicing/invoices/" in endpoint and endpoint.endswith("/send") and method == "POST":
            if not body_params:
                body_params = {"send_to_recipient": True}

        # 5. Build headers
        try:
            token = self.oauth.get_token()
        except Exception as e:
            return self._error_result(tool_id, request_id, "AUTH_ERROR", str(e), start)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Idempotency key for supported writes
        if method in ("POST", "PATCH"):
            headers["PayPal-Request-Id"] = request_id

        # Idempotency check for mutating operations (POST, PATCH, PUT)
        is_write = method in ("POST", "PATCH", "PUT")
        idem_key = f"nexus:idempotency:{request_id}"
        if is_write and request_id:
            cached_data = self.redis.get(idem_key)
            if cached_data:
                try:
                    cached_res = json.loads(cached_data)
                    logger.info("Idempotent replay served for request_id '%s' (tool: %s)", request_id, tool_id)
                    cached_res["idempotent_replay"] = True
                    return cached_res
                except Exception:
                    pass

        # 6. Execute with retry
        result = self._execute_with_retry(
            tool_id=tool_id,
            method=method,
            url=url,
            headers=headers,
            query_params=query_params,
            body_params=body_params,
            request_id=request_id,
            start=start,
        )

        # Cache successful write under idempotency key for 24 hours
        if is_write and request_id and result.get("status") == "SUCCESS":
            try:
                self.redis.set(idem_key, json.dumps(result), ex=86400)
            except Exception as e:
                logger.warning("Failed to cache idempotency result in Redis: %s", e)

        # Harvest entities into inter-agent memory blackboard
        if self.memory_store and result.get("status") == "SUCCESS":
            try:
                ctx_id = thread_id or request_id
                harvested = self.memory_store.extract_and_record_entities(ctx_id, tool_id, result)
                if harvested:
                    result["extracted_entities"] = harvested
            except Exception as e:
                logger.warning("Failed to harvest entities into memory blackboard: %s", e)

        return result

    def _execute_with_retry(self, tool_id, method, url, headers, query_params,
                             body_params, request_id, start) -> Dict[str, Any]:
        is_idempotent = method in IDEMPOTENT_METHODS or method == "POST"  # POST with idempotency key
        max_attempts = MAX_RETRIES if is_idempotent else 1

        last_error = None
        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=30.0) as client:
                    if method == "GET":
                        resp = client.get(url, headers=headers, params=query_params)
                    elif method == "POST":
                        resp = client.post(url, headers=headers, params=query_params, json=body_params or None)
                    elif method == "PUT":
                        resp = client.put(url, headers=headers, params=query_params, json=body_params or None)
                    elif method == "PATCH":
                        resp = client.patch(url, headers=headers, params=query_params, json=body_params or None)
                    elif method == "DELETE":
                        resp = client.delete(url, headers=headers, params=query_params)
                    else:
                        resp = client.request(method, url, headers=headers, params=query_params, json=body_params or None)

                # Handle 401 → refresh token once
                if resp.status_code == 401 and attempt == 0:
                    self.oauth.invalidate()
                    try:
                        new_token = self.oauth.get_token()
                        headers["Authorization"] = f"Bearer {new_token}"
                    except Exception as e:
                        return self._error_result(tool_id, request_id, "AUTH_ERROR", str(e), start)
                    continue

                # Handle 429 / 5xx with backoff (reads/idempotent only)
                if resp.status_code in (429,) or (500 <= resp.status_code < 600):
                    if resp.status_code == 429:
                        try:
                            self.redis.set("nexus:backoff:paypal", "1", ex=30)
                            logger.warning("PayPal returned 429 Too Many Requests; activated 30s Redis backoff lock.")
                        except Exception:
                            pass
                    if is_idempotent and attempt < max_attempts - 1:
                        wait = BACKOFF_BASE * (2 ** attempt)
                        logger.warning("HTTP %d on attempt %d, retrying in %.1fs", resp.status_code, attempt + 1, wait)
                        time.sleep(wait)
                        continue

                # Success
                latency = (time.time() - start) * 1000
                try:
                    body = resp.json()
                except Exception:
                    body = {"raw": resp.text[:2000]}

                if resp.status_code < 400:
                    summary = str(body)[:200]
                    if isinstance(body, dict) and "href" in body and "id" not in body:
                        inv_id = body["href"].rstrip("/").split("/")[-1]
                        body["id"] = inv_id
                        body["invoice_id"] = inv_id
                    self._log(tool_id, request_id, "SUCCESS", latency, response_summary=summary)
                    return {
                        "tool_id": tool_id,
                        "status": "SUCCESS",
                        "response": body,
                        "message": f"Completed successfully ({resp.status_code}).",
                        "request_id": request_id,
                        "latency_ms": latency,
                    }
                else:
                    err_msg = body.get("message", resp.text[:500]) if isinstance(body, dict) else resp.text[:500]
                    self._log(tool_id, request_id, "API_ERROR", latency, error=err_msg)
                    return {
                        "tool_id": tool_id,
                        "status": "API_ERROR",
                        "response": body,
                        "message": f"API returned {resp.status_code}: {err_msg}",
                        "request_id": request_id,
                        "latency_ms": latency,
                    }

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                if is_idempotent and attempt < max_attempts - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                    continue
                break
            except httpx.NetworkError as e:
                last_error = f"NetworkError: {e}"
                break
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                break

        latency = (time.time() - start) * 1000
        self._log(tool_id, request_id, "NETWORK_ERROR", latency, error=last_error)
        return {
            "tool_id": tool_id,
            "status": "NETWORK_ERROR",
            "response": None,
            "message": last_error or "Request failed after retries.",
            "request_id": request_id,
            "latency_ms": latency,
        }

    def _error_result(self, tool_id, request_id, status, message, start):
        latency = (time.time() - start) * 1000
        self._log(tool_id, request_id, status, latency, error=message)
        return {
            "tool_id": tool_id,
            "status": status,
            "response": None,
            "message": message,
            "request_id": request_id,
            "latency_ms": latency,
        }

    def _log(self, tool_id, request_id, status, latency_ms, error=None, response_summary=None):
        try:
            self.log_repo.append(ExecutionLog(
                request_id=request_id,
                tool_id=tool_id,
                status=status,
                latency_ms=latency_ms,
                error=error,
                response_summary=response_summary,
            ))
        except Exception as e:
            logger.error("Failed to write execution log: %s", e)
