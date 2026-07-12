"""Integration load testing for Cinemory.

Verifies concurrent pipeline processing under load using a thread pool.
Measures latency and thread safety across multiple parallel generations.
"""
import concurrent.futures
import time

import pytest

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.models import Bridge
from cinemory.pipeline import ReelPipeline
from cinemory.synthetic import synth_reel_spec


def run_single_pipeline(worker_id):
    storage = FakeStorage(bucket=f"cinemory-load-bucket-{worker_id}")
    spec = synth_reel_spec(f"load-reel-{worker_id}", chapters=2, per_chapter=1)
    
    # Add a bridge
    spec.bridges.append(Bridge(spec.chapters[0].id, spec.chapters[1].id, "cross dissolve"))
    
    pipeline = ReelPipeline(FakeMediaProvider(), storage)
    
    start_time = time.time()
    result = pipeline.run(spec)
    duration = time.time() - start_time
    
    return duration, result

def test_concurrent_pipeline_generation_load():
    concurrency_level = 20
    durations = []
    
    # Execute 20 pipelines concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run_single_pipeline, i): i for i in range(concurrency_level)}
        
        for future in concurrent.futures.as_completed(futures):
            worker_id = futures[future]
            try:
                duration, result = future.result()
                durations.append(duration)
                # Verify result contains the generated steps
                assert len(result.steps) == 3 # 2 chapters + 1 bridge
            except Exception as e:
                pytest.fail(f"Worker {worker_id} failed with exception: {e}")
                
    avg_duration = sum(durations) / len(durations)
    print(f"\nAverage generation duration under load: {avg_duration:.3f}s")
    
    assert len(durations) == concurrency_level
    assert avg_duration < 2.0 # Average pipeline compilation must be fast
