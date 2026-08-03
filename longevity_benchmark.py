"""
longevity_benchmark.py - High-Volume Longevity & Memory Leak Benchmark
"""

import time
import tracemalloc
from dataclasses import dataclass
from typing import Generator

from vent_adapter_contract import VentAdapterContract, RawVentTelemetryPacket
from bridge_integrator_contract import BridgeIntegrator


@dataclass(frozen=True)
class LongevityReport:
    total_frames: int
    duration_seconds: float
    frames_per_second: float
    initial_memory_kb: float
    final_memory_kb: float
    memory_drift_kb: float
    peak_memory_kb: float
    bytes_per_frame_drift: float


class InfinitePacketGenerator:

    @staticmethod
    def stream_packets(count: int) -> Generator[RawVentTelemetryPacket, None, None]:
        base_time = 1700000000.0
        for i in range(count):
            t_offset = (i % 100) * 0.1
            yield RawVentTelemetryPacket(
                batch_id=f"LONG-{i}",
                timestamp=base_time + t_offset,
                temperature_readings=[150.0 + (i % 5), 250.0 - (i % 5)] * 5,
                seismic_amplitude=[2.5 + (i % 3), 5.0 - (i % 3)] * 5,
                chemical_pH=[7.0 + (i % 2 * 0.1), 7.2 - (i % 2 * 0.1)] * 5
            )


class LongevityBenchmark:

    @classmethod
    def run_benchmark(
        cls, 
        total_frames: int = 1_000_000, 
        sample_interval: int = 100_000
    ) -> LongevityReport:
        adapter = VentAdapterContract()
        
        tracemalloc.start()
        tracemalloc.reset_peak()
        
        initial_size, _ = tracemalloc.get_traced_memory()
        
        start_time = time.perf_counter()
        peak_size_max = initial_size

        for idx, packet in enumerate(InfinitePacketGenerator.stream_packets(total_frames), start=1):
            batch, log_record = adapter.process_raw_packet(packet)
            if not log_record.qa_passed or batch is None:
                tracemalloc.stop()
                raise RuntimeError(f"Ingestion failed at frame {idx}: {log_record.error_message}")

            frame = BridgeIntegrator.verify_and_transform(batch)

            if idx % sample_interval == 0:
                current, peak = tracemalloc.get_traced_memory()
                if peak > peak_size_max:
                    peak_size_max = peak

        end_time = time.perf_counter()
        final_size, peak_size_final = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_size_max = max(peak_size_max, peak_size_final)
        duration = end_time - start_time
        fps = total_frames / duration if duration > 0 else 0.0
        drift_bytes = final_size - initial_size

        return LongevityReport(
            total_frames=total_frames,
            duration_seconds=duration,
            frames_per_second=fps,
            initial_memory_kb=initial_size / 1024.0,
            final_memory_kb=final_size / 1024.0,
            memory_drift_kb=drift_bytes / 1024.0,
            peak_memory_kb=peak_size_max / 1024.0,
            bytes_per_frame_drift=drift_bytes / total_frames if total_frames > 0 else 0.0
        )