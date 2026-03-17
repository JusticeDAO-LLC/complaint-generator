"""
Performance Benchmarking Suite for MCP++ Observability

Measures and profiles:
- Metrics collection latency and throughput
- Trace generation and export performance
- Circuit breaker decision latency
- Memory footprint under load
- Concurrent scaling characteristics

Usage:
    python observability_benchmarks.py
    Or import specific benchmark functions
"""

import time
import statistics
import json
import threading
from collections import defaultdict
from typing import Dict, List, Tuple, Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import tracemalloc

from ipfs_datasets_py.logic.security.llm_circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
)
from ipfs_datasets_py.logic.observability.metrics_prometheus import (
    get_prometheus_collector,
)
from ipfs_datasets_py.logic.observability.otel_integration import (
    get_otel_tracer,
)


# ============================================================================
# Utilities
# ============================================================================

class BenchmarkResult:
    """Stores and displays benchmark results."""
    
    def __init__(self, name: str):
        self.name = name
        self.times: List[float] = []
        self.errors = 0
        self.memory_start = 0
        self.memory_end = 0
    
    def add(self, elapsed: float):
        self.times.append(elapsed)
    
    def error(self):
        self.errors += 1
    
    @property
    def count(self) -> int:
        return len(self.times)
    
    @property
    def total(self) -> float:
        return sum(self.times)
    
    @property
    def mean(self) -> float:
        return statistics.mean(self.times) if self.times else 0.0
    
    @property
    def median(self) -> float:
        return statistics.median(self.times) if self.times else 0.0
    
    @property
    def stdev(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0.0
    
    @property
    def min(self) -> float:
        return min(self.times) if self.times else 0.0
    
    @property
    def max(self) -> float:
        return max(self.times) if self.times else 0.0
    
    @property
    def p95(self) -> float:
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]
    
    @property
    def p99(self) -> float:
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[idx]
    
    @property
    def throughput(self) -> float:
        """Operations per second."""
        if self.total == 0:
            return 0.0
        return self.count / self.total
    
    @property
    def memory_delta_mb(self) -> float:
        """Change in memory in MB."""
        return (self.memory_end - self.memory_start) / 1e6
    
    def print_summary(self):
        print(f"\n{self.name}")
        print(f"  Count:     {self.count:,}")
        print(f"  Total:     {self.total:.3f}s")
        print(f"  Throughput: {self.throughput:,.0f} ops/sec")
        print(f"  Mean:      {self.mean*1000:.2f}ms")
        print(f"  Median:    {self.median*1000:.2f}ms")
        print(f"  Stdev:     {self.stdev*1000:.2f}ms")
        print(f"  Min:       {self.min*1000:.2f}ms")
        print(f"  Max:       {self.max*1000:.2f}ms")
        print(f"  P95:       {self.p95*1000:.2f}ms")
        print(f"  P99:       {self.p99*1000:.2f}ms")
        if self.errors:
            print(f"  Errors:    {self.errors}")
        if self.memory_delta_mb != 0:
            print(f"  Memory Δ:  {self.memory_delta_mb:+.1f}MB")


# ============================================================================
# Benchmark 1: Metrics Recording Latency
# ============================================================================

def benchmark_metrics_recording_latency(iterations: int = 10000) -> BenchmarkResult:
    """
    Measure latency of recording a single metric.
    
    Expected: <1ms per operation
    """
    result = BenchmarkResult("Metrics Recording Latency")
    metrics = get_prometheus_collector()
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    start_time = time.time()
    
    for i in range(iterations):
        op_start = time.time()
        metrics.record_circuit_breaker_call("benchmark_service", 0.05, success=True)
        elapsed = time.time() - op_start
        result.add(elapsed)
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    return result


# ============================================================================
# Benchmark 2: Metrics Export Performance
# ============================================================================

def benchmark_metrics_export(iterations: int = 100) -> BenchmarkResult:
    """
    Measure latency of exporting metrics to Prometheus format.
    
    Expected: <10ms for 10-50 components
    """
    result = BenchmarkResult("Metrics Export Performance")
    metrics = get_prometheus_collector()
    
    # Pre-populate metrics
    for i in range(50):
        component = f"service_{i}"
        for j in range(20):
            metrics.record_circuit_breaker_call(component, 0.05, success=j % 5 != 0)
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    for _ in range(iterations):
        op_start = time.time()
        export_text = metrics.export_prometheus_format()
        elapsed = time.time() - op_start
        result.add(elapsed)
        assert len(export_text) > 0, "Export returned empty"
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    return result


# ============================================================================
# Benchmark 3: Trace Creation and Completion
# ============================================================================

def benchmark_trace_creation(iterations: int = 1000) -> BenchmarkResult:
    """
    Measure latency of creating and completing a trace with spans.
    
    Expected: <5ms per trace (with 5 spans)
    """
    result = BenchmarkResult("Trace Creation (5 spans)")
    tracer = get_otel_tracer()
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    for i in range(iterations):
        op_start = time.time()
        
        # Create a trace with 5 spans
        root_span = tracer.start_span("root_operation")
        
        for j in range(4):
            child_span = tracer.start_span(f"sub_operation_{j}")
            child_span.set_attribute("index", j)
            child_span.end(success=True)
        
        root_span.set_attribute("total_children", 4)
        root_span.end(success=True)
        
        elapsed = time.time() - op_start
        result.add(elapsed)
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    return result


# ============================================================================
# Benchmark 4: Trace Export to Jaeger Format
# ============================================================================

def benchmark_trace_export(num_traces: int = 100) -> BenchmarkResult:
    """
    Measure latency of exporting traces to Jaeger JSON format.
    
    Expected: <50ms for 100 traces
    """
    result = BenchmarkResult("Trace Export to Jaeger JSON")
    tracer = get_otel_tracer()
    
    # Generate traces
    for i in range(num_traces):
        span = tracer.start_span(f"operation_{i}")
        span.set_attribute("iteration", i)
        span.end(success=i % 10 != 0)
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    # Export operation (typically done once at end, so we time it multiple iterations)
    for _ in range(10):
        op_start = time.time()
        jaeger_json = tracer.export_to_jaeger_json()
        elapsed = time.time() - op_start
        result.add(elapsed)
        assert len(jaeger_json) > 0, "Export returned empty"
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    return result


# ============================================================================
# Benchmark 5: Circuit Breaker Decision Latency
# ============================================================================

def benchmark_circuit_breaker_decision(iterations: int = 10000) -> BenchmarkResult:
    """
    Measure latency of circuit breaker state checking and decisions.
    
    Expected: <0.1ms per operation
    """
    result = BenchmarkResult("Circuit Breaker Decision Latency")
    cb = get_circuit_breaker("benchmark_cb")
    
    def fast_service():
        return "ok"
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    for _ in range(iterations):
        op_start = time.time()
        try:
            cb.call(fast_service)
        except CircuitBreakerOpenError:
            pass
        elapsed = time.time() - op_start
        result.add(elapsed)
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    return result


# ============================================================================
# Benchmark 6: Concurrent Metrics Recording
# ============================================================================

def benchmark_concurrent_metrics(num_threads: int = 50, ops_per_thread: int = 1000) -> BenchmarkResult:
    """
    Measure throughput of concurrent metrics recording.
    
    Expected: >50,000 ops/sec across 50 threads
    """
    result = BenchmarkResult(f"Concurrent Metrics ({num_threads} threads)")
    metrics = get_prometheus_collector()
    
    def worker():
        for i in range(ops_per_thread):
            component = f"worker_{threading.current_thread().ident}"
            metrics.record_circuit_breaker_call(component, 0.01, success=i % 10 != 0)
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    bench_start = time.time()
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for future in as_completed(futures):
            future.result()
    
    total_elapsed = time.time() - bench_start
    
    # Each thread did ops_per_thread operations
    total_ops = num_threads * ops_per_thread
    result.times = [total_elapsed]  # Simulate single operation
    result.metrics_count = total_ops  # Custom tracking
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    # Custom print for concurrent benchmark
    print(f"\n{result.name}")
    print(f"  Total ops:     {total_ops:,}")
    print(f"  Total time:    {total_elapsed:.3f}s")
    print(f"  Throughput:    {total_ops / total_elapsed:,.0f} ops/sec")
    print(f"  Per thread:    {result.name.split('(')[1].split(')')[0]}")
    print(f"  Memory Δ:      {result.memory_delta_mb:+.1f}MB")
    
    return result


# ============================================================================
# Benchmark 7: Concurrent Trace Creation
# ============================================================================

def benchmark_concurrent_tracing(num_threads: int = 20, traces_per_thread: int = 100) -> BenchmarkResult:
    """
    Measure thread safety and performance of concurrent trace creation.
    
    Expected: >5,000 traces/sec across 20 threads
    """
    result = BenchmarkResult(f"Concurrent Tracing ({num_threads} threads)")
    tracer = get_otel_tracer()
    
    def worker():
        for i in range(traces_per_thread):
            span = tracer.start_span(f"concurrent_op")
            span.set_attribute("thread_id", threading.current_thread().ident)
            span.set_attribute("iteration", i)
            span.end(success=True)
    
    tracemalloc.start()
    result.memory_start = tracemalloc.get_traced_memory()[0]
    
    bench_start = time.time()
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker) for _ in range(num_threads)]
        for future in as_completed(futures):
            future.result()
    
    total_elapsed = time.time() - bench_start
    total_traces = num_threads * traces_per_thread
    
    result.times = [total_elapsed]
    
    result.memory_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    
    # Custom print
    print(f"\n{result.name}")
    print(f"  Total traces:  {total_traces:,}")
    print(f"  Total time:    {total_elapsed:.3f}s")
    print(f"  Throughput:    {total_traces / total_elapsed:,.0f} traces/sec")
    print(f"  Memory Δ:      {result.memory_delta_mb:+.1f}MB")
    
    return result


# ============================================================================
# Benchmark 8: Memory Growth Under Load
# ============================================================================

def benchmark_memory_growth(duration_seconds: int = 10, ops_per_second: int = 1000) -> Dict[str, Any]:
    """
    Measure memory growth over time under sustained load.
    
    Expected: <10MB growth over 10 seconds at 1000 ops/sec
    """
    metrics = get_prometheus_collector()
    tracer = get_otel_tracer()
    
    tracemalloc.start()
    
    memory_over_time = []
    start_time = time.time()
    
    while time.time() - start_time < duration_seconds:
        iteration_start = time.time()
        
        # Record metrics
        for i in range(ops_per_second // 10):
            metrics.record_circuit_breaker_call("memory_test", 0.01, success=True)
        
        # Create traces
        for i in range(100):
            span = tracer.start_span("memory_test_op")
            span.end(success=True)
        
        # Record memory
        current_mem = tracemalloc.get_traced_memory()[0] / 1e6  # MB
        elapsed_overall = time.time() - start_time
        memory_over_time.append((elapsed_overall, current_mem))
        
        # Control loop rate
        iteration_elapsed = time.time() - iteration_start
        if iteration_elapsed < 1.0:
            time.sleep(1.0 - iteration_elapsed)
    
    tracemalloc.stop()
    
    # Analysis
    initial_mem = memory_over_time[0][1]
    final_mem = memory_over_time[-1][1]
    max_mem = max(m for _, m in memory_over_time)
    
    print(f"\nMemory Growth Over {duration_seconds}s")
    print(f"  Initial: {initial_mem:.1f}MB")
    print(f"  Final:   {final_mem:.1f}MB")
    print(f"  Max:     {max_mem:.1f}MB")
    print(f"  Growth:  {final_mem - initial_mem:+.1f}MB")
    print(f"  Rate:    {(final_mem - initial_mem) / duration_seconds:+.3f}MB/s")
    
    return {
        "initial_mb": initial_mem,
        "final_mb": final_mem,
        "max_mb": max_mem,
        "growth_mb": final_mem - initial_mem,
        "growth_rate_mb_per_sec": (final_mem - initial_mem) / duration_seconds,
        "memory_timeline": memory_over_time,
    }


# ============================================================================
# Benchmark 9: Latency Under Load
# ============================================================================

def benchmark_latency_under_load(load_threads: int = 50, test_duration: int = 10) -> Dict[str, Any]:
    """
    Measure metric/trace recording latency while under load.
    
    Expected: <5ms P99 latency with 50 concurrent threads
    """
    metrics = get_prometheus_collector()
    latencies = []
    lock = threading.Lock()
    stop_flag = threading.Event()
    
    def load_worker():
        """Generate background load."""
        while not stop_flag.is_set():
            metrics.record_circuit_breaker_call("load_gen", 0.001, success=True)
    
    def measurement_worker():
        """Measure latency of operations."""
        while not stop_flag.is_set():
            op_start = time.time()
            metrics.record_circuit_breaker_call("measurement", 0.001, success=True)
            elapsed = time.time() - op_start
            with lock:
                latencies.append(elapsed)
            time.sleep(0.001)  # 1000 measurements/sec
    
    print(f"\nLatency Under Load ({load_threads} threads for {test_duration}s)")
    
    # Start load workers
    with ThreadPoolExecutor(max_workers=load_threads) as executor:
        load_futures = [executor.submit(load_worker) for _ in range(load_threads)]
        
        # Start measurement worker
        measurement_future = executor.submit(measurement_worker)
        
        # Run for duration
        time.sleep(test_duration)
        stop_flag.set()
        
        # Wait for completion
        for future in [measurement_future] + load_futures:
            try:
                future.result(timeout=5)
            except:
                pass
    
    # Analysis
    if latencies:
        sorted_latencies = sorted(latencies)
        p50 = sorted_latencies[int(len(sorted_latencies) * 0.50)]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        
        print(f"  Measurements: {len(latencies):,}")
        print(f"  Mean:         {statistics.mean(latencies)*1000:.2f}ms")
        print(f"  P50:          {p50*1000:.2f}ms")
        print(f"  P95:          {p95*1000:.2f}ms")
        print(f"  P99:          {p99*1000:.2f}ms")
        print(f"  Max:          {max(latencies)*1000:.2f}ms")
        
        return {
            "measurements": len(latencies),
            "mean_ms": statistics.mean(latencies) * 1000,
            "p50_ms": p50 * 1000,
            "p95_ms": p95 * 1000,
            "p99_ms": p99 * 1000,
            "max_ms": max(latencies) * 1000,
        }
    
    return {}


# ============================================================================
# Suite Execution
# ============================================================================

def run_all_benchmarks():
    """Run complete benchmark suite."""
    print("="*70)
    print("MCP++ Observability Benchmarking Suite")
    print("="*70)
    
    results = []
    
    # Basic latency benchmarks
    results.append(benchmark_metrics_recording_latency(10000))
    results[0].print_summary()
    
    results.append(benchmark_metrics_export(100))
    results[1].print_summary()
    
    results.append(benchmark_circuit_breaker_decision(10000))
    results[2].print_summary()
    
    results.append(benchmark_trace_creation(1000))
    results[3].print_summary()
    
    results.append(benchmark_trace_export(100))
    results[4].print_summary()
    
    # Concurrent benchmarks
    benchmark_concurrent_metrics(50, 1000)
    benchmark_concurrent_tracing(20, 100)
    
    # Load testing
    benchmark_memory_growth(10)
    benchmark_latency_under_load(50, 10)
    
    # Summary
    print("\n" + "="*70)
    print("Benchmark Summary")
    print("="*70)
    print("\nLatency Benchmarks:")
    for result in results[:5]:
        print(f"  {result.name}: {result.mean*1000:.2f}ms (P99: {result.p99*1000:.2f}ms)")
    
    print("\nAll benchmarks completed!")


if __name__ == "__main__":
    run_all_benchmarks()
