"""
test_longevity_benchmark.py - Longevity & Memory Leak Operational Test Suite
"""

import pytest
from longevity_benchmark import LongevityBenchmark


def test_short_longevity_burn_in_memory_stability():
    """
    Executes a 50,000 frame burn-in run.
    Verifies memory drift stays under 50 KB total and drift-per-frame is effectively sub-byte.
    """
    target_frames = 50_000
    report = LongevityBenchmark.run_benchmark(total_frames=target_frames, sample_interval=10_000)

    assert report.total_frames == target_frames
    # Realistic throughput bound under active tracemalloc profiling
    assert report.frames_per_second > 100.0, f"Throughput too low: {report.frames_per_second:.2f} FPS"
    
    # Enforce strict memory bounds (under 50KB drift over 50k frames)
    assert report.memory_drift_kb < 50.0, f"Excessive memory drift detected: {report.memory_drift_kb:.2f} KB"
    
    # Sub-byte allocation drift per frame
    assert report.bytes_per_frame_drift < 1.0, f"Memory leak detected: {report.bytes_per_frame_drift:.4f} B/frame"


def test_full_longevity_burn_in_100k():
    """
    Executes a 100,000 frame high-volume longevity test.
    Ensures O(1) memory footprint and reports metrics.
    """
    target_frames = 100_000
    report = LongevityBenchmark.run_benchmark(total_frames=target_frames, sample_interval=20_000)

    print(f"\n--- Longevity Benchmark Metrics ({target_frames:,} frames) ---")
    print(f"Duration          : {report.duration_seconds:.2f} seconds")
    print(f"Throughput        : {report.frames_per_second:,.2f} frames/sec")
    print(f"Initial Memory    : {report.initial_memory_kb:.2f} KB")
    print(f"Final Memory      : {report.final_memory_kb:.2f} KB")
    print(f"Memory Drift      : {report.memory_drift_kb:.2f} KB")
    print(f"Peak Allocation   : {report.peak_memory_kb:.2f} KB")
    print(f"Drift per Frame   : {report.bytes_per_frame_drift:.6f} bytes/frame")
    print("-------------------------------------------------------")

    assert report.memory_drift_kb < 100.0
    assert report.bytes_per_frame_drift < 1.0