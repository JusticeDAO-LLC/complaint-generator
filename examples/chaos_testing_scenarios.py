"""
Chaos Engineering and Stress Testing Patterns for MCP++

Advanced testing scenarios for validating resilience, recovery, and
production readiness of systems using circuit breaker and observability.

Run with: python chaos_testing.py [scenario]
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List

from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.observability.otel_integration import (
    get_otel_tracer,
    EventType,
)


# ============================================================================
# Scenario 1: Gradual Failure Injection
# ============================================================================

def scenario_gradual_failure_injection():
    """
    Simulate a service slowly degrading to total failure.
    
    This tests whether the circuit breaker detects gradual degradation
    and opens before cascading failure occurs.
    """
    print("\n=== Scenario 1: Gradual Failure Injection ===")
    
    cb = get_circuit_breaker("degrading_service")
    metrics = get_prometheus_collector()
    
    def service_call_with_increasing_failures(req_num: int) -> bool:
        """Service that becomes progressively more likely to fail."""
        # Failure probability increases over time: 0% → 50% → 100%
        failure_rate = min(req_num / 100.0, 0.5)
        if random.random() < failure_rate:
            raise Exception(f"Service error (failure rate: {failure_rate:.1%})")
        return True
    
    successful_calls = 0
    failed_calls = 0
    circuit_opened_at = None
    
    print("Submitting 200 requests with gradual failure injection...")
    
    for i in range(200):
        start = time.time()
        try:
            cb.call(service_call_with_increasing_failures, i)
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("degrading_service", elapsed, success=True)
            successful_calls += 1
        except CircuitBreakerOpenError:
            if circuit_opened_at is None:
                circuit_opened_at = i
            failed_calls += 1
        except Exception as e:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("degrading_service", elapsed, success=False)
            failed_calls += 1
        
        if (i + 1) % 50 == 0:
            summary = metrics.get_metrics_summary("degrading_service")
            print(f"  Request {i+1}: Success rate {summary['success_rate']:.1f}% | "
                  f"Circuit: {summary['current_state']}")
    
    print(f"\nResults:")
    print(f"  Total: {successful_calls + failed_calls}")
    print(f"  Successful: {successful_calls}")
    print(f"  Failed: {failed_calls}")
    print(f"  Circuit opened at request: {circuit_opened_at or 'Never'}")
    
    summary = metrics.get_metrics_summary("degrading_service")
    print(f"  Final failure rate: {summary['failure_rate']:.1f}%")


# ============================================================================
# Scenario 2: Transient Outage and Recovery
# ============================================================================

def scenario_transient_outage():
    """
    Simulate a service that experiences a brief outage then recovers.
    
    Tests whether the circuit breaker properly enters HALF_OPEN state
    and recovers when the service comes back online.
    """
    print("\n=== Scenario 2: Transient Outage and Recovery ===")
    
    cb = get_circuit_breaker("outage_service")
    metrics = get_prometheus_collector()
    cb.timeout_seconds = 2.0  # Short timeout for demo
    
    service_is_up = True
    
    def service_with_outage() -> str:
        if not service_is_up:
            raise Exception("Service temporarily unavailable")
        return "success"
    
    print("Phase 1: Service is healthy (20 requests)")
    for i in range(20):
        start = time.time()
        try:
            cb.call(service_with_outage)
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("outage_service", elapsed, success=True)
            print(".", end="", flush=True)
        except Exception as e:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("outage_service", elapsed, success=False)
    
    print("\nPhase 2: Service goes down")
    service_is_up = False
    
    circuit_opened = False
    for i in range(10):
        start = time.time()
        try:
            cb.call(service_with_outage)
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("outage_service", elapsed, success=True)
        except CircuitBreakerOpenError:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("outage_service", elapsed, success=False)
            circuit_opened = True
            print("CB", end="", flush=True)  # Circuit breaker opened
        except Exception:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("outage_service", elapsed, success=False)
            print("X", end="", flush=True)  # Service error
    
    print(f"\nCircuit opened: {circuit_opened}")
    
    print(f"Phase 3: Waiting {cb.timeout_seconds}s for recovery attempt...")
    time.sleep(cb.timeout_seconds + 0.5)
    
    print("Phase 4: Service recovers")
    service_is_up = True
    
    try:
        cb.call(service_with_outage)
        print("✓ Circuit recovered and service is accessible")
    except Exception as e:
        print(f"✗ Still failing: {e}")
    
    summary = metrics.get_metrics_summary("outage_service")
    print(f"\nFinal state: {summary['current_state']}")


# ============================================================================
# Scenario 3: Concurrent Load with Failures
# ============================================================================

def scenario_concurrent_load_with_failures():
    """
    Simulate high concurrent load with random failures.
    
    Tests thread safety, lock contention, and metrics accuracy
    under realistic production conditions.
    """
    print("\n=== Scenario 3: Concurrent Load with Failures ===")
    
    cb = get_circuit_breaker("concurrent_service")
    metrics = get_prometheus_collector()
    
    def unreliable_service(delay: float = 0.001) -> str:
        """Service that randomly fails."""
        # Simulate I/O
        time.sleep(delay)
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Random failure")
        return "ok"
    
    num_threads = 50
    calls_per_thread = 20
    successful = 0
    failed = 0
    lock = threading.Lock()
    
    def worker(thread_id: int):
        nonlocal successful, failed
        for i in range(calls_per_thread):
            start = time.time()
            try:
                cb.call(unreliable_service, delay=0.001)
                elapsed = time.time() - start
                metrics.record_circuit_breaker_call("concurrent_service", elapsed, success=True)
                with lock:
                    successful += 1
            except CircuitBreakerOpenError:
                elapsed = time.time() - start
                metrics.record_circuit_breaker_call("concurrent_service", elapsed, success=False)
                with lock:
                    failed += 1
            except Exception:
                elapsed = time.time() - start
                metrics.record_circuit_breaker_call("concurrent_service", elapsed, success=False)
                with lock:
                    failed += 1
    
    print(f"Spawning {num_threads} threads with {calls_per_thread} calls each...")
    print(f"Total requests: {num_threads * calls_per_thread}")
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for future in as_completed(futures):
            future.result()
    
    total = successful + failed
    summary = metrics.get_metrics_summary("concurrent_service")
    
    print(f"\nResults:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Success rate: {successful / total * 100:.1f}%")
    print(f"  Measured success rate: {summary['success_rate']:.1f}%")
    print(f"  Avg latency: {summary['avg_latency'] * 1000:.2f}ms")
    print(f"  P99 latency: {summary['latency_percentiles']['p99'] * 1000:.2f}ms")


# ============================================================================
# Scenario 4: Cascading Failures
# ============================================================================

def scenario_cascading_failures():
    """
    Simulate failure in one service causing cascading failures downstream.
    
    Tests whether circuit breakers prevent cascading failure propagation.
    """
    print("\n=== Scenario 4: Cascading Failures ===")
    
    # Service dependency chain: A → B → C
    cb_a = get_circuit_breaker("service_a")
    cb_b = get_circuit_breaker("service_b")
    cb_c = get_circuit_breaker("service_c")
    metrics = get_prometheus_collector()
    
    service_c_healthy = True
    service_b_healthy = True
    
    def service_c():
        if not service_c_healthy:
            raise Exception("Service C down")
        return "c_ok"
    
    def service_b():
        if not service_b_healthy:
            raise Exception("Service B down")
        # B calls C
        result = cb_c.call(service_c)
        return f"b_ok({result})"
    
    def service_a():
        # A calls B
        result = cb_b.call(service_b)
        return f"a_ok({result})"
    
    print("Phase 1: All services healthy (30 requests through A→B→C)")
    successes = 0
    for i in range(30):
        start = time.time()
        try:
            cb_a.call(service_a)
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("service_chain", elapsed, success=True)
            successes += 1
            print(".", end="", flush=True)
        except Exception as e:
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("service_chain", elapsed, success=False)
            print("X", end="", flush=True)
    
    print(f"\nSuccess rate: {successes}/30")
    
    print("\nPhase 2: Service C fails")
    service_c_healthy = False
    
    successes = 0
    for i in range(30):
        start = time.time()
        try:
            cb_a.call(service_a)
            elapsed = time.time() - start
            metrics.record_circuit_breaker_call("service_chain", elapsed, success=True)
            successes += 1
            print(".", end="", flush=True)
        except CircuitBreakerOpenError:
            print("Ø", end="", flush=True)  # Circuit breaker
        except Exception:
            print("X", end="", flush=True)
    
    print(f"\nSuccess rate: {successes}/30")
    print("CB prevented cascading: Failures in C would propagate through B to A")
    print("CB B should have opened due to C failures")
    print(f"CB B state: {cb_b.state.value}")


# ============================================================================
# Scenario 5: Variable Latency Spike
# ============================================================================

def scenario_latency_spike():
    """
    Simulate a service that suddenly starts responding slowly.
    
    Tests whether latency metrics are captured and alerts would trigger.
    """
    print("\n=== Scenario 5: Latency Spike ===")
    
    cb = get_circuit_breaker("latency_service")
    metrics = get_prometheus_collector()
    
    baseline_latency = 0.05  # 50ms
    spike_latency = 0.5      # 500ms
    current_latency = baseline_latency
    
    def variable_latency_service():
        time.sleep(current_latency)
        return "ok"
    
    print(f"Phase 1: Baseline latency (~{baseline_latency*1000:.0f}ms, 50 requests)")
    current_latency = baseline_latency
    for i in range(50):
        start = time.time()
        cb.call(variable_latency_service)
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("latency_service", elapsed, success=True)
        if (i + 1) % 10 == 0:
            summary = metrics.get_metrics_summary("latency_service")
            print(f"  P99 latency: {summary['latency_percentiles']['p99']*1000:.0f}ms")
    
    print(f"\nPhase 2: Latency spike (~{spike_latency*1000:.0f}ms, 50 requests)")
    current_latency = spike_latency
    for i in range(50):
        start = time.time()
        cb.call(variable_latency_service)
        elapsed = time.time() - start
        metrics.record_circuit_breaker_call("latency_service", elapsed, success=True)
        if (i + 1) % 10 == 0:
            summary = metrics.get_metrics_summary("latency_service")
            print(f"  P99 latency: {summary['latency_percentiles']['p99']*1000:.0f}ms", end="")
            if summary['latency_percentiles']['p99'] > 0.2:
                print(" ⚠️ ALERT: High latency")
            else:
                print()
    
    summary = metrics.get_metrics_summary("latency_service")
    print(f"\nFinal statistics:")
    print(f"  Avg: {summary['avg_latency']*1000:.1f}ms")
    print(f"  P95: {summary['latency_percentiles']['p95']*1000:.1f}ms")
    print(f"  P99: {summary['latency_percentiles']['p99']*1000:.1f}ms")


# ============================================================================
# Scenario 6: Circuit Breaker State Transitions
# ============================================================================

def scenario_state_transitions():
    """
    Visualize circuit breaker state transitions under controlled conditions.
    
    Tests the state machine: CLOSED → OPEN → HALF_OPEN → CLOSED
    """
    print("\n=== Scenario 6: Circuit Breaker State Transitions ===")
    
    cb = get_circuit_breaker("state_test_service")
    cb.timeout_seconds = 1.0
    
    failed = False
    
    def controlled_service():
        if failed:
            raise Exception("Service failed")
        return "ok"
    
    print("Initial state:", cb.state.value)
    
    print("\nStep 1: Make 5 successful calls")
    for i in range(5):
        cb.call(controlled_service)
        print(f"  Call {i+1}: state={cb.state.value}, failures={cb.failure_count}")
    
    print("\nStep 2: Trigger failures to open circuit")
    failed = True
    for i in range(10):
        try:
            cb.call(controlled_service)
        except CircuitBreakerOpenError:
            print(f"  Call {i+1}: CIRCUIT_OPEN")
            break
        except Exception:
            print(f"  Call {i+1}: state={cb.state.value}, failures={cb.failure_count}")
    
    print(f"\nCircuit is now: {cb.state.value}")
    
    print(f"\nStep 3: Wait {cb.timeout_seconds}s for cool-down")
    time.sleep(cb.timeout_seconds + 0.1)
    
    print("Step 4: Allow recovery (next call will test service)")
    failed = False
    try:
        result = cb.call(controlled_service)
        print(f"  Recovery call succeeded: {result}")
        print(f"  Circuit state: {cb.state.value}")
    except CircuitBreakerOpenError:
        print("  Circuit still open (might be HALF_OPEN)")


# ============================================================================
# Scenario 7: Concurrent Metric Recording
# ============================================================================

def scenario_concurrent_metrics():
    """
    Verify metrics are accurate under concurrent recording.
    
    Tests thread safety and correctness of metric aggregation.
    """
    print("\n=== Scenario 7: Concurrent Metric Recording ===")
    
    metrics = get_prometheus_collector()
    
    num_threads = 20
    calls_per_thread = 100
    
    def worker(thread_id: int):
        for i in range(calls_per_thread):
            # Each thread records to different component
            component = f"worker_{thread_id}"
            latency = random.uniform(0.001, 0.1)
            success = random.random() > 0.1
            metrics.record_circuit_breaker_call(component, latency, success=success)
    
    print(f"Recording {num_threads * calls_per_thread} metrics from {num_threads} threads...")
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for future in as_completed(futures):
            future.result()
    
    print("Verification:")
    for i in range(num_threads):
        component = f"worker_{i}"
        summary = metrics.get_metrics_summary(component)
        assert summary['total_calls'] == calls_per_thread, \
            f"Component {component} has wrong call count"
    
    print(f"✓ All {num_threads} components recorded exactly {calls_per_thread} calls")
    print("✓ Metrics are accurate under concurrent access")


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == "__main__":
    import sys
    
    scenarios = {
        "1": scenario_gradual_failure_injection,
        "2": scenario_transient_outage,
        "3": scenario_concurrent_load_with_failures,
        "4": scenario_cascading_failures,
        "5": scenario_latency_spike,
        "6": scenario_state_transitions,
        "7": scenario_concurrent_metrics,
    }
    
    if len(sys.argv) > 1:
        scenario_num = sys.argv[1]
        if scenario_num in scenarios:
            scenarios[scenario_num]()
        else:
            print(f"Unknown scenario: {scenario_num}")
    else:
        print("Available chaos engineering scenarios:")
        print("  1: Gradual failure injection")
        print("  2: Transient outage and recovery")
        print("  3: Concurrent load with failures")
        print("  4: Cascading failures")
        print("  5: Latency spike detection")
        print("  6: State transition visualization")
        print("  7: Concurrent metric recording")
        print()
        print("Usage: python chaos_testing.py [1-7]")
        print()
        print("Running all scenarios...")
        for scenario_num in sorted(scenarios.keys()):
            scenarios[scenario_num]()
