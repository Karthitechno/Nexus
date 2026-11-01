"""Live Scenarios Verification Script for NEXUS.
Executes the 5 canonical test scenarios against the real orchestrator and PayPal Sandbox.
Records real pass/fail results, timings, and exact outputs according to the Output Contract.
"""
import os
import sys
import json
import time
import uuid

# Ensure workspace root is in sys.path
sys.path.insert(0, r"d:\Nexus")

from dotenv import load_dotenv
load_dotenv(r"d:\Nexus\.env")

from nexus.registry.repository import JsonToolRepository
from nexus.retrieval.hybrid import HybridRetriever
from nexus.executor.oauth import PayPalOAuthManager
from nexus.executor.logs import ExecutionLogRepository
from nexus.executor.executor import GenericExecutor
from nexus.rag.pipeline import RAGPipeline
from nexus.rag.system_search import SystemSearch
from nexus.orchestration.graph import NexusOrchestrator
from langgraph.types import Command

def run_tests():
    print("=" * 80)
    print("NEXUS CANONICAL SCENARIO EXECUTION & VERIFICATION")
    print("=" * 80)

    # 1. Initialize components
    tools_path = r"d:\Nexus\data\registry\tools.json"
    repo = JsonToolRepository(tools_path)
    retriever = HybridRetriever(repository=repo)
    
    oauth = PayPalOAuthManager()
    log_repo = ExecutionLogRepository(r"d:\Nexus\data\logs\executions.json")
    executor = GenericExecutor(repository=repo, log_repo=log_repo)
    rag_pipe = RAGPipeline()
    sys_search = SystemSearch(repository=repo, log_repo=log_repo)

    orchestrator = NexusOrchestrator(
        repository=repo,
        retriever=retriever,
        executor=executor,
        rag_pipeline=rag_pipe,
        system_search=sys_search,
    )

    test_results = {}

    # -------------------------------------------------------------
    # TEST 1: Safe Read Query ("List all my invoices")
    # -------------------------------------------------------------
    print("\n--- RUNNING TEST 1: Safe Read Query ---")
    t1_thread = f"test1-read-{uuid.uuid4().hex[:6]}"
    t1_query = "List all my invoices"
    t1_config = {"configurable": {"thread_id": t1_thread}}
    t1_start = time.time()
    
    # Stream events to check for interrupts
    events = list(orchestrator.graph.stream({"query": t1_query, "thread_id": t1_thread}, config=t1_config))
    t1_elapsed = (time.time() - t1_start) * 1000
    snapshot = orchestrator.graph.get_state(t1_config)
    t1_state = snapshot.values

    t1_has_interrupt = any(t.interrupts for t in snapshot.tasks) if snapshot.tasks else False
    t1_final_resp = t1_state.get("final_response", "")
    t1_exec_results = t1_state.get("execution_results", [])
    t1_tool_id = t1_exec_results[0].get("tool_id") if t1_exec_results else None
    t1_status = t1_exec_results[0].get("status") if t1_exec_results else None

    t1_pass = (
        not t1_has_interrupt
        and t1_status == "SUCCESS"
        and "invoice" in t1_final_resp.lower()
        and "Request ID:" in t1_final_resp
    )
    test_results["test_1"] = {
        "scenario": "Safe Read (List Invoices)",
        "query": t1_query,
        "passed": t1_pass,
        "latency_ms": round(t1_elapsed, 1),
        "approval_required": t1_has_interrupt,
        "tool_used": t1_tool_id,
        "status": t1_status,
        "response_preview": t1_final_resp.split("\n\n<small")[0],
        "request_id": t1_state.get("request_id"),
    }
    print(f"Test 1 Passed: {t1_pass} (Elapsed: {t1_elapsed:.1f}ms, Tool: {t1_tool_id})")

    # -------------------------------------------------------------
    # TEST 2: Mutating Write ("Create an invoice for $50 to bob@example.com")
    # -------------------------------------------------------------
    print("\n--- RUNNING TEST 2: Mutating Write with Approval ---")
    t2_thread = f"test2-create-{uuid.uuid4().hex[:6]}"
    t2_query = "Create an invoice for $50 to bob@example.com"
    t2_config = {"configurable": {"thread_id": t2_thread}}
    t2_start = time.time()

    list(orchestrator.graph.stream({"query": t2_query, "thread_id": t2_thread}, config=t2_config))
    snapshot_2a = orchestrator.graph.get_state(t2_config)
    t2_interrupted = any(t.interrupts for t in snapshot_2a.tasks) if snapshot_2a.tasks else False
    interrupt_val = snapshot_2a.tasks[0].interrupts[0].value if (snapshot_2a.tasks and snapshot_2a.tasks[0].interrupts) else {}

    # Resume with approval
    resumed_state = orchestrator.graph.invoke(
        Command(resume={"approved": True}),
        config=t2_config,
    )
    t2_elapsed = (time.time() - t2_start) * 1000

    t2_exec_results = resumed_state.get("execution_results", [])
    t2_raw_resp = (t2_exec_results[0].get("response") or {}) if t2_exec_results else {}
    t2_final_resp = resumed_state.get("final_response", "")
    t2_status = t2_exec_results[0].get("status") if t2_exec_results else None

    # Check that PayPal returned href and that invoice_id was extracted
    t2_href = t2_raw_resp.get("href", "")
    t2_has_href = "https://api.sandbox.paypal.com/v2/invoicing/invoices/INV2-" in t2_href
    t2_extracted_id = t2_href.rstrip("/").split("/")[-1] if t2_has_href else ""

    t2_pass = (
        t2_interrupted
        and t2_status == "SUCCESS"
        and t2_has_href
        and t2_extracted_id in t2_final_resp
    )
    test_results["test_2"] = {
        "scenario": "Mutating Write (Create Invoice)",
        "query": t2_query,
        "passed": t2_pass,
        "latency_ms": round(t2_elapsed, 1),
        "approval_triggered": t2_interrupted,
        "interrupt_details": interrupt_val.get("details", {}),
        "paypal_href": t2_href,
        "extracted_invoice_id": t2_extracted_id,
        "response_preview": t2_final_resp.split("\n\n<small")[0],
        "request_id": resumed_state.get("request_id"),
    }
    print(f"Test 2 Passed: {t2_pass} (Elapsed: {t2_elapsed:.1f}ms, Created ID: {t2_extracted_id})")

    # -------------------------------------------------------------
    # TEST 3: Missing Required Parameter ("Send an invoice")
    # -------------------------------------------------------------
    print("\n--- RUNNING TEST 3: Missing Parameter Clarification ---")
    t3_thread = f"test3-missing-{uuid.uuid4().hex[:6]}"
    t3_query = "Send an invoice"
    t3_config = {"configurable": {"thread_id": t3_thread}}
    t3_start = time.time()

    list(orchestrator.graph.stream({"query": t3_query, "thread_id": t3_thread}, config=t3_config))
    t3_elapsed = (time.time() - t3_start) * 1000
    snapshot_3 = orchestrator.graph.get_state(t3_config)
    t3_state = snapshot_3.values
    t3_final_resp = t3_state.get("final_response", "")
    t3_clarification = t3_state.get("clarification_prompt")
    t3_execs = t3_state.get("execution_results", [])

    # Must ask for invoice_id, no execution results, no guess
    t3_pass = (
        t3_clarification is not None
        and ("invoice" in t3_clarification.lower() or "id" in t3_clarification.lower())
        and len(t3_execs) == 0
    )
    test_results["test_3"] = {
        "scenario": "Clarification for Missing Parameter",
        "query": t3_query,
        "passed": t3_pass,
        "latency_ms": round(t3_elapsed, 1),
        "clarification_prompt": t3_clarification,
        "executed_tools_count": len(t3_execs),
    }
    print(f"Test 3 Passed: {t3_pass} (Prompt: '{t3_clarification}')")

    # -------------------------------------------------------------
    # TEST 4: System Search ("Show all available tools in the registry")
    # -------------------------------------------------------------
    print("\n--- RUNNING TEST 4: System Search Registry Query ---")
    t4_thread = f"test4-sys-{uuid.uuid4().hex[:6]}"
    t4_query = "Show all available tools in the registry"
    t4_config = {"configurable": {"thread_id": t4_thread}}
    t4_start = time.time()

    list(orchestrator.graph.stream({"query": t4_query, "thread_id": t4_thread}, config=t4_config))
    t4_elapsed = (time.time() - t4_start) * 1000
    snapshot_4 = orchestrator.graph.get_state(t4_config)
    t4_state = snapshot_4.values
    t4_final_resp = t4_state.get("final_response", "")
    t4_intent = t4_state.get("intent")
    t4_execs = t4_state.get("execution_results", [])

    # Verify counts match repository at runtime
    current_repo_count = repo.count()
    t4_pass = (
        t4_intent == "SYSTEM_SEARCH"
        and len(t4_execs) == 0  # 0 external API calls
        and str(current_repo_count) in t4_final_resp
    )
    test_results["test_4"] = {
        "scenario": "System Search (Runtime Registry Introspection)",
        "query": t4_query,
        "passed": t4_pass,
        "latency_ms": round(t4_elapsed, 1),
        "intent": t4_intent,
        "repo_tool_count": current_repo_count,
        "external_api_calls": len(t4_execs),
        "response_preview": t4_final_resp.split("\n\n<small")[0],
    }
    print(f"Test 4 Passed: {t4_pass} (Intent: {t4_intent}, Repo Count: {current_repo_count}, Calls: {len(t4_execs)})")

    # -------------------------------------------------------------
    # TEST 5: Multi-Step DAG ("Create an invoice for $60 to test@example.com and send it")
    # -------------------------------------------------------------
    print("\n--- RUNNING TEST 5: Multi-Step DAG (Create then Send) ---")
    t5_thread = f"test5-multi-{uuid.uuid4().hex[:6]}"
    t5_query = "Create an invoice for $60 to test@example.com and send it"
    t5_config = {"configurable": {"thread_id": t5_thread}}
    t5_start = time.time()

    list(orchestrator.graph.stream({"query": t5_query, "thread_id": t5_thread}, config=t5_config))
    snapshot_5a = orchestrator.graph.get_state(t5_config)
    t5_interrupted = any(t.interrupts for t in snapshot_5a.tasks) if snapshot_5a.tasks else False
    t5_interrupt_val = snapshot_5a.tasks[0].interrupts[0].value if (snapshot_5a.tasks and snapshot_5a.tasks[0].interrupts) else {}
    t5_steps_in_modal = t5_interrupt_val.get("details", {}).get("steps", [])

    # Resume with approval
    resumed_5 = orchestrator.graph.invoke(
        Command(resume={"approved": True}),
        config=t5_config,
    )
    t5_elapsed = (time.time() - t5_start) * 1000
    t5_exec_results = resumed_5.get("execution_results", [])
    t5_final_resp = resumed_5.get("final_response", "")

    step1_res = t5_exec_results[0] if len(t5_exec_results) > 0 else {}
    step2_res = t5_exec_results[1] if len(t5_exec_results) > 1 else {}
    
    step1_href = step1_res.get("response", {}).get("href", "")
    created_id_step1 = step1_href.rstrip("/").split("/")[-1] if "INV2-" in step1_href else ""
    step2_status = step2_res.get("status")

    t5_pass = (
        t5_interrupted
        and len(t5_steps_in_modal) >= 2  # Shows both steps in modal
        and len(t5_exec_results) == 2
        and step1_res.get("status") == "SUCCESS"
        and step2_status == "SUCCESS"
        and created_id_step1 != ""
    )
    test_results["test_5"] = {
        "scenario": "Multi-Step DAG (Create & Send)",
        "query": t5_query,
        "passed": t5_pass,
        "latency_ms": round(t5_elapsed, 1),
        "steps_in_approval_modal": len(t5_steps_in_modal),
        "steps_executed": len(t5_exec_results),
        "step_1_tool": step1_res.get("tool_id"),
        "step_1_invoice_id": created_id_step1,
        "step_2_tool": step2_res.get("tool_id"),
        "step_2_status": step2_status,
        "response_preview": t5_final_resp.split("\n\n<small")[0],
        "request_id": resumed_5.get("request_id"),
    }
    print(f"Test 5 Passed: {t5_pass} (Steps in modal: {len(t5_steps_in_modal)}, Created & Sent: {created_id_step1})")

    # Save results to data/test_results.json
    out_path = r"d:\Nexus\data\test_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=2)

    print("\n" + "=" * 80)
    print(f"ALL 5 CANONICAL TESTS EXECUTED. RESULTS WRITTEN TO: {out_path}")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()
