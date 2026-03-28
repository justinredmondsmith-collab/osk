#!/usr/bin/env python3
"""
Evaluation script for Ollama semantic synthesis.

Tests that semantic synthesis correctly distinguishes between contextually
different observations that would trigger the same alert with keyword-only
heuristic synthesis.

Usage:
    python scripts/evaluate_semantic_synthesis.py [--model MODEL] [--url URL]

Examples:
    # Test with default model
    python scripts/evaluate_semantic_synthesis.py
    
    # Test with specific model
    python scripts/evaluate_semantic_synthesis.py --model llama3.2:3b
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from uuid import uuid4

# Add src to path
sys.path.insert(0, "/var/home/bazzite/osk/src")

from osk.intelligence_contracts import IntelligenceObservation, ObservationKind
from osk.models import EventCategory, EventSeverity
from osk.ollama_synthesis import OllamaObservationSynthesizer


@dataclass
class TestCase:
    """A test case for semantic synthesis evaluation."""
    name: str
    description: str
    observation: IntelligenceObservation
    expected_category: EventCategory | None
    expected_severity: EventSeverity | None


TEST_CASES = [
    TestCase(
        name="Police helping (low severity)",
        description="Police providing assistance should be INFO/ADVISORY, not WARNING",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="Police officers are helping protesters find water and medical supplies.",
            confidence=0.9,
        ),
        expected_category=EventCategory.POLICE_ACTION,
        expected_severity=EventSeverity.INFO,  # Should NOT be WARNING
    ),
    TestCase(
        name="Police charging (high severity)",
        description="Police charging crowd should be WARNING",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="Police officers are charging into the crowd with batons raised.",
            confidence=0.9,
        ),
        expected_category=EventCategory.POLICE_ACTION,
        expected_severity=EventSeverity.WARNING,
    ),
    TestCase(
        name="Police observing (neutral)",
        description="Police just observing should be INFO",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="Police vehicles parked nearby, officers observing from a distance.",
            confidence=0.85,
        ),
        expected_category=EventCategory.POLICE_ACTION,
        expected_severity=EventSeverity.INFO,
    ),
    TestCase(
        name="Medical emergency",
        description="Medical emergency should be WARNING",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="Someone is injured and bleeding, needs medical attention immediately.",
            confidence=0.9,
        ),
        expected_category=EventCategory.MEDICAL,
        expected_severity=EventSeverity.WARNING,
    ),
    TestCase(
        name="Medical all clear",
        description="Medical situation resolved should be INFO",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="Medical team has arrived and the injured person is stable now.",
            confidence=0.85,
        ),
        expected_category=EventCategory.MEDICAL,
        expected_severity=EventSeverity.INFO,
    ),
    TestCase(
        name="Blocked route",
        description="Route blocked should be ADVISORY",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="The north entrance is blocked by police barricades.",
            confidence=0.9,
        ),
        expected_category=EventCategory.BLOCKED_ROUTE,
        expected_severity=EventSeverity.ADVISORY,
    ),
    TestCase(
        name="Escalation detected",
        description="Fighting and violence should be WARNING",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="People are fighting near the stage, situation escalating quickly.",
            confidence=0.88,
        ),
        expected_category=EventCategory.ESCALATION,
        expected_severity=EventSeverity.WARNING,
    ),
    TestCase(
        name="Weather (irrelevant)",
        description="Weather info should not trigger event",
        observation=IntelligenceObservation(
            kind=ObservationKind.TRANSCRIPT,
            source_member_id=uuid4(),
            summary="The weather is sunny and warm today, nice day for a protest.",
            confidence=0.95,
        ),
        expected_category=None,
        expected_severity=None,
    ),
]


def check_result(
    test_case: TestCase,
    category: EventCategory | None,
    severity: EventSeverity | None,
) -> tuple[bool, str]:
    """Check if result matches expected. Returns (passed, message)."""
    if test_case.expected_category is None:
        if category is not None:
            return False, f"Expected no event, got {category.value}/{severity.value if severity else 'None'}"
        return True, "Correctly ignored"
    
    if category != test_case.expected_category:
        return False, f"Expected {test_case.expected_category.value}, got {category.value if category else 'None'}"
    
    if severity != test_case.expected_severity:
        return False, f"Expected {test_case.expected_severity.value}, got {severity.value if severity else 'None'}"
    
    return True, "Correct"


async def evaluate_synthesizer(
    synthesizer: OllamaObservationSynthesizer,
    test_cases: list[TestCase],
) -> dict:
    """Run evaluation and return results."""
    results = []
    latencies = []
    
    for test in test_cases:
        print(f"\n  Testing: {test.name}")
        print(f"    Input: {test.observation.summary[:60]}...")
        
        start = time.monotonic()
        decision = await synthesizer.synthesize(test.observation)
        latency = time.monotonic() - start
        latencies.append(latency)
        
        category = decision.events[0].category if decision.events else None
        severity = decision.events[0].severity if decision.events else None
        
        passed, message = check_result(test, category, severity)
        status = "✓ PASS" if passed else "✗ FAIL"
        
        print(f"    Expected: {test.expected_category.value if test.expected_category else 'None'}/"
              f"{test.expected_severity.value if test.expected_severity else 'None'}")
        print(f"    Got: {category.value if category else 'None'}/"
              f"{severity.value if severity else 'None'}")
        print(f"    {status}: {message} ({latency:.2f}s)")
        
        results.append({
            "test": test.name,
            "passed": passed,
            "expected": f"{test.expected_category.value if test.expected_category else 'None'}/"
                       f"{test.expected_severity.value if test.expected_severity else 'None'}",
            "got": f"{category.value if category else 'None'}/"
                  f"{severity.value if severity else 'None'}",
            "latency": latency,
        })
    
    return {
        "results": results,
        "latencies": latencies,
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
    }


async def main():
    parser = argparse.ArgumentParser(description="Evaluate semantic synthesis")
    parser.add_argument("--model", default="llama3.2:3b", help="Ollama model to use")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama base URL")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout")
    args = parser.parse_args()
    
    print("=" * 60)
    print("OSK Semantic Synthesis Evaluation")
    print("=" * 60)
    print(f"Model: {args.model}")
    print(f"URL: {args.url}")
    print(f"Test cases: {len(TEST_CASES)}")
    
    # Check Ollama availability
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{args.url}/api/tags", timeout=5.0)
            if response.status_code != 200:
                print(f"\n✗ Ollama not responding (status {response.status_code})")
                return 1
            
            models = response.json().get("models", [])
            model_names = [m.get("name", m.get("model", "")) for m in models]
            
            if args.model not in model_names:
                print(f"\n⚠ Model '{args.model}' not found in Ollama")
                print(f"  Available models: {', '.join(model_names[:5])}...")
                print(f"  Pull with: ollama pull {args.model}")
                return 1
            
            print(f"✓ Ollama available, model found")
    except Exception as exc:
        print(f"\n✗ Cannot connect to Ollama: {exc}")
        print(f"  Make sure Ollama is running: ollama serve")
        return 1
    
    # Create synthesizer
    synthesizer = OllamaObservationSynthesizer(
        base_url=args.url,
        model=args.model,
        timeout_seconds=args.timeout,
    )
    
    print("\n" + "-" * 60)
    print("Running evaluation...")
    print("-" * 60)
    
    try:
        results = await evaluate_synthesizer(synthesizer, TEST_CASES)
    except Exception as exc:
        print(f"\n✗ Evaluation failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await synthesizer.close()
    
    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    accuracy = results["passed"] / results["total"] * 100
    avg_latency = sum(results["latencies"]) / len(results["latencies"])
    max_latency = max(results["latencies"])
    
    print(f"Accuracy: {results['passed']}/{results['total']} ({accuracy:.0f}%)")
    print(f"Avg latency: {avg_latency:.2f}s")
    print(f"Max latency: {max_latency:.2f}s")
    
    if accuracy >= 80:
        print(f"\n✓ Target accuracy met (≥80%)")
    else:
        print(f"\n✗ Below target accuracy (<80%)")
    
    if max_latency <= 3.0:
        print(f"✓ Latency target met (≤3s)")
    else:
        print(f"⚠ Latency above target (>3s)")
    
    # Print failed tests
    failed = [r for r in results["results"] if not r["passed"]]
    if failed:
        print(f"\nFailed tests:")
        for r in failed:
            print(f"  - {r['test']}: expected {r['expected']}, got {r['got']}")
    
    return 0 if accuracy >= 80 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
