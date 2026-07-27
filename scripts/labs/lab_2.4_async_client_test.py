"""
Lab 2.4: AsyncHttpClient Test Script
Tests single fetch, batch processing, error handling, and rate limiting.
Includes benchmarking and visualization.
"""
import asyncio
import logging
import time
import sys
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

# === FIX THE IMPORT PATH ===
# Add project root (ai-platform/) to Python's search path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
# === END FIX ===

from core.clients.async_http_client import AsyncHttpClient

# Configure logging to see progress messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

async def test_single_fetch():
    """Test fetching a single URL."""
    print("\n" + "="*50)
    print("Test 1: Single Fetch")
    print("="*50)
    
    async with AsyncHttpClient() as client:
        url = "https://jsonplaceholder.typicode.com/posts/1"
        result = await client.fetch(url)
        
        if 'error' in result:
            print(f"❌ Failed: {result['error']}")
        else:
            print(f"✅ Success! Got post with title: {result.get('title', 'N/A')}")
            print(f"   Full result: {result}")

async def test_batch_fetch():
    """Test fetching multiple URLs concurrently."""
    print("\n" + '.'*50)
    print("Test 2: Batch Fetch (10 URLs)")
    print('.'*50)
    
    # Create 10 URLs
    urls = [f"https://jsonplaceholder.typicode.com/posts/{i}" for i in range(1, 11)]
    
    start_time = time.time()
    async with AsyncHttpClient(max_concurrent=5) as client:
        results = await client.fetch_batch(urls)
    elapsed = time.time() - start_time
    
    # Count successes
    successes = sum(1 for r in results if 'error' not in r)
    
    print(f"\n📊 Results:")
    print(f"   Total URLs: {len(urls)}")
    print(f"   Successes: {successes}")
    print(f"   Failures: {len(urls) - successes}")
    print(f"   Time: {elapsed:.2f}s")
    print(f"   Throughput: {len(urls)/elapsed:.2f} req/s")

async def test_error_handling():
    """Test with invalid URLs to verify error handling."""
    print("\n" + '.'*50)
    print("Test 3: Error Handling (Mixed Valid/Invalid)")
    print('.'*50)
    
    urls = [
        "https://jsonplaceholder.typicode.com/posts/1",  # Valid
        "https://jsonplaceholder.typicode.com/posts/2",  # Valid
        "https://this-url-does-not-exist-12345.com/test",  # Invalid
        "https://jsonplaceholder.typicode.com/posts/999999",  # Valid URL, but 404
        "https://invalid-domain-xyz.com/api",  # Invalid
    ]
    
    async with AsyncHttpClient(max_concurrent=3, max_retries=2) as client:
        results = await client.fetch_batch(urls)
    
    print(f"\n📊 Results:")
    for i, result in enumerate(results, 1):
        if 'error' in result:
            print(f"   {i}. ❌ Error: {result['error'][:50]} | URL: {result['url'][:40]}")
        else:
            print(f"   {i}. ✅ Success: {result.get('title', 'N/A')[:50]}")

async def test_rate_limiting():
    """Test that semaphore actually limits concurrency."""
    print("\n" + '.'*50)
    print("Test 4: Rate Limiting (20 URLs, max_concurrent=5)")
    print('.'*50)
    print("Watch the logs - requests should process in waves of 5\n")
    
    # Create 20 URLs
    urls = [f"https://jsonplaceholder.typicode.com/posts/{i}" for i in range(1, 21)]
    
    start_time = time.time()
    async with AsyncHttpClient(max_concurrent=5, timeout=10) as client:
        results = await client.fetch_batch(urls)
    elapsed = time.time() - start_time
    
    successes = sum(1 for r in results if 'error' not in r)
    
    print(f"\n📊 Results:")
    print(f"   Total URLs: {len(urls)}")
    print(f"   Successes: {successes}")
    print(f"   Time: {elapsed:.2f}s")
    print(f"   Average: {elapsed/len(urls):.2f}s per request")

async def test_retry_logic():
    """Test retry with exponential backoff on a flaky endpoint."""
    print("\n" + '.'*50)
    print("Test 5: Retry Logic")
    print('.'*50)
    
    url = "https://httpstat.us/500"  # Always returns 500
    
    print(f"Attempting to fetch URL that returns HTTP 500...")
    print(f"Should retry 3 times with exponential backoff (1s, 2s)")
    
    start_time = time.time()
    async with AsyncHttpClient(max_concurrent=1, max_retries=3, timeout=5) as client:
        result = await client.fetch(url)
    elapsed = time.time() - start_time
    
    print(f"\n📊 Result:")
    if 'error' in result:
        print(f"   ❌ All retries failed (expected): {result['error']}")
        print(f"   Total time: {elapsed:.2f}s (should be ~3-4s with backoff)")
    else:
        print(f"   ✅ Unexpected success: {result}")

# ============================================================================
# BENCHMARKING FUNCTIONS
# ============================================================================

async def benchmark_concurrency_scaling():
    """Benchmark different concurrency levels."""
    print("\n" + '.'*60)
    print("BENCHMARK 1: Concurrency Scaling")
    print('.'*60)
    
    concurrency_levels = [5, 10, 25, 50]
    num_requests = 50
    results = []
    
    for max_concurrent in concurrency_levels:
        print(f"\n🔄 Testing max_concurrent={max_concurrent}...")
        
        # Create URLs (cycle through available posts)
        urls = [f"https://jsonplaceholder.typicode.com/posts/{i % 100 + 1}" for i in range(num_requests)]
        
        start_time = time.time()
        async with AsyncHttpClient(max_concurrent=max_concurrent, timeout=10) as client:
            batch_results = await client.fetch_batch(urls)
        elapsed = time.time() - start_time
        
        # Calculate metrics
        successes = sum(1 for r in batch_results if 'error' not in r)
        throughput = num_requests / elapsed
        success_rate = (successes / num_requests) * 100
        
        result = {
            'max_concurrent': max_concurrent,
            'total_requests': num_requests,
            'time': round(elapsed, 2),
            'throughput': round(throughput, 2),
            'success_rate': round(success_rate, 1),
            'successes': successes
        }
        results.append(result)
        
        print(f"   ✅ Time: {elapsed:.2f}s | Throughput: {throughput:.2f} req/s | Success: {success_rate:.1f}%")
    
    return results

async def benchmark_retry_effectiveness():
    """Compare performance with different retry counts."""
    print("\n" + '.'*60)
    print("BENCHMARK 2: Retry Effectiveness")
    print('.'*60)
    
    retry_configs = [0, 1, 2, 3]
    results = []
    
    # Mix of good and potentially flaky URLs
    urls = [
        "https://jsonplaceholder.typicode.com/posts/1",
        "https://jsonplaceholder.typicode.com/posts/2",
        "https://jsonplaceholder.typicode.com/posts/3",
        "https://jsonplaceholder.typicode.com/posts/999999",  # 404
        "https://jsonplaceholder.typicode.com/posts/4",
    ]
    
    for max_retries in retry_configs:
        print(f"\n🔄 Testing max_retries={max_retries}...")
        
        start_time = time.time()
        async with AsyncHttpClient(max_concurrent=5, max_retries=max_retries, timeout=5) as client:
            batch_results = await client.fetch_batch(urls)
        elapsed = time.time() - start_time
        
        # Calculate metrics
        successes = sum(1 for r in batch_results if 'error' not in r)
        success_rate = (successes / len(urls)) * 100
        avg_time = elapsed / len(urls)
        
        result = {
            'max_retries': max_retries,
            'total_requests': len(urls),
            'successes': successes,
            'success_rate': round(success_rate, 1),
            'total_time': round(elapsed, 2),
            'avg_time_per_request': round(avg_time, 2)
        }
        results.append(result)
        
        print(f"   ✅ Successes: {successes}/{len(urls)} | Success Rate: {success_rate:.1f}% | Avg Time: {avg_time:.2f}s")
    
    return results

def save_benchmarks(benchmark_data, filename="lab_2.4_async_client_benchmarks.json"):
    """Save benchmark results to JSON file."""
    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
    benchmarks_dir.mkdir(exist_ok=True)
    
    filepath = benchmarks_dir / filename
    
    with open(filepath, 'w') as f:
        json.dump(benchmark_data, f, indent=2)
    
    print(f"\n💾 Benchmarks saved to: {filepath}")
    return filepath

def visualize_benchmarks(benchmark_data, filename="lab_2.4_async_client_benchmarks.png"):
    """Create visualization of benchmark results."""
    print("\n📊 Creating visualizations...")
    
    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
    benchmarks_dir.mkdir(exist_ok=True)
    filepath = benchmarks_dir / filename
    
    # Create figure with 2 subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle('Lab 2.4: AsyncHttpClient Benchmarks', fontsize=16, fontweight='bold')
    
    # ============ Plot 1: Concurrency Scaling ============
    concurrency_data = benchmark_data['concurrency_scaling']
    
    max_concurrent_vals = [d['max_concurrent'] for d in concurrency_data]
    throughput_vals = [d['throughput'] for d in concurrency_data]
    success_rates = [d['success_rate'] for d in concurrency_data]
    
    # Dual y-axis for throughput and success rate
    ax1_twin = ax1.twinx()
    
    # Throughput bars
    bars = ax1.bar(range(len(max_concurrent_vals)), throughput_vals, 
                   alpha=0.7, color='steelblue', label='Throughput')
    ax1.set_xlabel('Max Concurrent Requests', fontweight='bold')
    ax1.set_ylabel('Throughput (req/s)', color='steelblue', fontweight='bold')
    ax1.set_xticks(range(len(max_concurrent_vals)))
    ax1.set_xticklabels(max_concurrent_vals)
    ax1.tick_params(axis='y', labelcolor='steelblue')
    ax1.grid(axis='y', alpha=0.3)
    
    # Success rate line
    line = ax1_twin.plot(range(len(max_concurrent_vals)), success_rates, 
                         color='green', marker='o', linewidth=2, markersize=8, label='Success Rate')
    ax1_twin.set_ylabel('Success Rate (%)', color='green', fontweight='bold')
    ax1_twin.tick_params(axis='y', labelcolor='green')
    ax1_twin.set_ylim([0, 105])
    
    # Add value labels on bars
    for i, (bar, val) in enumerate(zip(bars, throughput_vals)):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{val:.1f}',
                ha='center', va='bottom', fontsize=9)
    
    ax1.set_title('Concurrency Scaling Performance', fontweight='bold')
    
    # ============ Plot 2: Retry Effectiveness ============
    retry_data = benchmark_data['retry_effectiveness']
    
    retry_vals = [d['max_retries'] for d in retry_data]
    success_rates_retry = [d['success_rate'] for d in retry_data]
    avg_times = [d['avg_time_per_request'] for d in retry_data]
    
    # Dual y-axis
    ax2_twin = ax2.twinx()
    
    # Success rate bars
    bars2 = ax2.bar(range(len(retry_vals)), success_rates_retry,
                    alpha=0.7, color='lightgreen', label='Success Rate')
    ax2.set_xlabel('Max Retries', fontweight='bold')
    ax2.set_ylabel('Success Rate (%)', color='green', fontweight='bold')
    ax2.set_xticks(range(len(retry_vals)))
    ax2.set_xticklabels(retry_vals)
    ax2.tick_params(axis='y', labelcolor='green')
    ax2.set_ylim([0, 105])
    ax2.grid(axis='y', alpha=0.3)
    
    # Average time line
    line2 = ax2_twin.plot(range(len(retry_vals)), avg_times,
                          color='coral', marker='s', linewidth=2, markersize=8, label='Avg Time')
    ax2_twin.set_ylabel('Avg Time per Request (s)', color='coral', fontweight='bold')
    ax2_twin.tick_params(axis='y', labelcolor='coral')
    
    # Add value labels
    for i, (bar, val) in enumerate(zip(bars2, success_rates_retry)):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{val:.1f}%',
                ha='center', va='bottom', fontsize=9)
    
    ax2.set_title('Retry Logic Effectiveness', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    print(f"📈 Visualization saved to: {filepath}")
    
    return filepath

async def run_benchmarks():
    """Run all benchmarks and save results."""
    print("\n" + '.'*60)
    print("RUNNING BENCHMARKS")
    print('.'*60)
    
    # Run benchmarks
    concurrency_results = await benchmark_concurrency_scaling()
    retry_results = await benchmark_retry_effectiveness()
    
    # Prepare data
    benchmark_data = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'concurrency_scaling': concurrency_results,
        'retry_effectiveness': retry_results
    }
    
    # Save to JSON
    save_benchmarks(benchmark_data)
    
    # Create visualization
    visualize_benchmarks(benchmark_data)
    
    return benchmark_data

# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Run all tests and benchmarks."""
    print("\n" + '.'*60)
    print("AsyncHttpClient - Comprehensive Test Suite")
    print('.'*60)
    
    # Run functional tests
    await test_single_fetch()
    await test_batch_fetch()
    await test_error_handling()
    await test_rate_limiting()
    await test_retry_logic()
    
    print("\n" + '.'*60)
    print("✅ All functional tests complete!")
    print('.'*60)
    
    # Run benchmarks
    benchmark_data = await run_benchmarks()
    
    # Print summary
    print("\n" + '.'*60)
    print("📊 BENCHMARK SUMMARY")
    print('.'*60)
    
    print("\n🚀 Concurrency Scaling:")
    for result in benchmark_data['concurrency_scaling']:
        print(f"   max_concurrent={result['max_concurrent']:3d} → "
              f"{result['throughput']:6.2f} req/s, "
              f"{result['success_rate']:5.1f}% success, "
              f"{result['time']:5.2f}s total")
    
    print("\n🔄 Retry Effectiveness:")
    for result in benchmark_data['retry_effectiveness']:
        print(f"   max_retries={result['max_retries']} → "
              f"{result['success_rate']:5.1f}% success, "
              f"{result['avg_time_per_request']:4.2f}s avg per request")
    
    print("\n" + '.'*60)
    print("🎉 All tests and benchmarks complete!")
    print('.'*60)

if __name__ == "__main__":
    asyncio.run(main())