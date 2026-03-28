#!/usr/bin/env python3
"""
Ollama Synthesis Evaluation Script

Evaluates Ollama-based semantic synthesis for Osk observations.
Compares accuracy and latency against the heuristic baseline.

Usage:
    python scripts/ollama_synthesis_test.py --model llama3.2:3b
    python scripts/ollama_synthesis_test.py --compare  # Test all models
    python scripts/ollama_synthesis_test.py --json-output results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

# Test dataset: observations with expected classifications
TEST_OBSERVATIONS = [
    {
        "kind": "TRANSCRIPT",
        "summary": "Police officers are advancing on the crowd with batons drawn",
        "expected_category": "police_action",
        "expected_severity": "warning",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "I see an ambulance and medical personnel treating someone on the ground",
        "expected_category": "medical",
        "expected_severity": "warning",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "The main entrance is completely blocked with barriers",
        "expected_category": "blocked_route",
        "expected_severity": "advisory",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "People are running and screaming, there's a stampede forming",
        "expected_category": "escalation",
        "expected_severity": "critical",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "A large group is marching down Main Street with banners",
        "expected_category": "crowd_movement",
        "expected_severity": "info",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Police are helping redirect traffic and keeping people safe",
        "expected_category": "community",
        "expected_severity": "info",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Someone is bleeding from the head and needs help",
        "expected_category": "medical",
        "expected_severity": "critical",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "The road is closed ahead, find another route",
        "expected_category": "blocked_route",
        "expected_severity": "advisory",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Fights breaking out near the south entrance",
        "expected_category": "escalation",
        "expected_severity": "critical",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Law enforcement is standing by observing",
        "expected_category": "police_action",
        "expected_severity": "info",
    },
    # Edge cases
    {
        "kind": "TRANSCRIPT",
        "summary": "It's a nice day for a peaceful protest",
        "expected_category": "community",
        "expected_severity": "info",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Help needed urgently, emergency situation",
        "expected_category": "medical",  # Ambiguous - could be anything
        "expected_severity": "critical",
    },
    {
        "kind": "VISION",
        "summary": "Frame shows police line with shields",
        "expected_category": "police_action",
        "expected_severity": "warning",
    },
    {
        "kind": "VISION",
        "summary": "Frame shows empty street with debris",
        "expected_category": "community",
        "expected_severity": "info",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Fire trucks and ambulance arriving at scene",
        "expected_category": "medical",  # Emergency services
        "expected_severity": "warning",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Crowd chanting slogans, peaceful atmosphere",
        "expected_category": "crowd_movement",
        "expected_severity": "info",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Tear gas deployed, people coughing and running",
        "expected_category": "escalation",
        "expected_severity": "critical",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Barricades being set up at intersection",
        "expected_category": "blocked_route",
        "expected_severity": "advisory",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Officer down, requesting immediate backup",
        "expected_category": "police_action",  # Police-related emergency
        "expected_severity": "critical",
    },
    {
        "kind": "TRANSCRIPT",
        "summary": "Group moving toward city hall",
        "expected_category": "crowd_movement",
        "expected_severity": "info",
    },
]


@dataclass
class TestResult:
    """Result for a single test case."""

    observation: dict[str, Any]
    predicted_category: str | None
    predicted_severity: str | None
    category_correct: bool
    severity_correct: bool
    latency_ms: float
    error: str | None = None


@dataclass
class EvaluationReport:
    """Full evaluation report."""

    model: str
    timestamp: str
    total_tests: int
    category_accuracy: float
    severity_accuracy: float
    combined_accuracy: float  # Both category AND severity correct
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def call_ollama(
    prompt: str,
    model: str,
    base_url: str = "http://localhost:11434",
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Call Ollama API with structured JSON output."""

    system_prompt = """You are an AI assistant analyzing observations from a civilian situational awareness system.
Your task is to classify observations into categories and assess severity.

Respond ONLY in valid JSON format with these fields:
- category: One of [police_action, blocked_route, medical, escalation, crowd_movement, community, null]
- severity: One of [critical, warning, advisory, info, null]
- reasoning: Brief explanation (1 sentence)
- confidence: Number between 0.0 and 1.0

If the observation is not operationally relevant, use null for category and severity."""

    response = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,  # Low temperature for consistent outputs
                "num_predict": 200,  # Limit token generation
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def parse_response(response_text: str) -> dict[str, Any] | None:
    """Parse Ollama JSON response."""

    try:
        # Try direct JSON parse
        data = json.loads(response_text)
        return {
            "category": data.get("category"),
            "severity": data.get("severity"),
            "reasoning": data.get("reasoning", ""),
            "confidence": data.get("confidence", 0.0),
        }
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re

        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return {
                    "category": data.get("category"),
                    "severity": data.get("severity"),
                    "reasoning": data.get("reasoning", ""),
                    "confidence": data.get("confidence", 0.0),
                }
            except json.JSONDecodeError:
                pass

        return None


def heuristic_classify(summary: str) -> tuple[str | None, str | None]:
    """Simple heuristic baseline for comparison."""

    summary_lower = summary.lower()

    # Category detection
    if any(word in summary_lower for word in ["police", "officer", "law enforcement"]):
        category = "police_action"
    elif any(word in summary_lower for word in ["block", "barrier", "closed", "sealed"]):
        category = "blocked_route"
    elif any(word in summary_lower for word in ["medical", "injury", "bleeding", "ambulance", "hurt", "treating"]):
        category = "medical"
    elif any(word in summary_lower for word in ["fight", "stampede", "violence", "panic", "tear gas"]):
        category = "escalation"
    elif any(word in summary_lower for word in ["march", "crowd", "group", "gathering"]):
        category = "crowd_movement"
    else:
        category = "community"

    # Severity detection
    if any(word in summary_lower for word in ["critical", "severe", "bleeding", "stampede", "tear gas", "urgent", "emergency"]):
        severity = "critical"
    elif any(word in summary_lower for word in ["warning", "advancing", "blocked", "barrier", "ambulance"]):
        severity = "warning"
    elif any(word in summary_lower for word in ["advisory", "notable", "closed"]):
        severity = "advisory"
    else:
        severity = "info"

    return category, severity


def evaluate_model(
    model: str,
    base_url: str = "http://localhost:11434",
    test_cases: list[dict] | None = None,
) -> EvaluationReport:
    """Evaluate a single model."""

    if test_cases is None:
        test_cases = TEST_OBSERVATIONS

    results: list[TestResult] = []
    errors: list[str] = []
    latencies: list[float] = []

    print(f"\nEvaluating model: {model}")
    print("=" * 60)

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}/{len(test_cases)}: {test['kind']}")
        print(f"  Summary: {test['summary'][:60]}...")

        prompt = f"""Observation Type: {test['kind']}
Summary: {test['summary']}

Classify this observation."""

        start_time = time.perf_counter()

        try:
            response = call_ollama(prompt, model, base_url)
            latency_ms = (time.perf_counter() - start_time) * 1000
            latencies.append(latency_ms)

            parsed = parse_response(response["response"])

            if parsed is None:
                errors.append(f"Test {i}: Failed to parse response")
                results.append(
                    TestResult(
                        observation=test,
                        predicted_category=None,
                        predicted_severity=None,
                        category_correct=False,
                        severity_correct=False,
                        latency_ms=latency_ms,
                        error="Parse error",
                    )
                )
                print(f"  ❌ Parse error")
                continue

            pred_cat = parsed.get("category")
            pred_sev = parsed.get("severity")

            cat_correct = pred_cat == test["expected_category"]
            sev_correct = pred_sev == test["expected_severity"]

            results.append(
                TestResult(
                    observation=test,
                    predicted_category=pred_cat,
                    predicted_severity=pred_sev,
                    category_correct=cat_correct,
                    severity_correct=sev_correct,
                    latency_ms=latency_ms,
                )
            )

            status = "✓" if (cat_correct and sev_correct) else "✗"
            print(f"  {status} Category: {pred_cat} ({'✓' if cat_correct else '✗'})")
            print(f"  {status} Severity: {pred_sev} ({'✓' if sev_correct else '✗'})")
            print(f"  Latency: {latency_ms:.1f}ms")

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            errors.append(f"Test {i}: {e}")
            results.append(
                TestResult(
                    observation=test,
                    predicted_category=None,
                    predicted_severity=None,
                    category_correct=False,
                    severity_correct=False,
                    latency_ms=latency_ms,
                    error=str(e),
                )
            )
            print(f"  ❌ Error: {e}")

    # Calculate metrics
    total = len(results)
    cat_correct = sum(1 for r in results if r.category_correct)
    sev_correct = sum(1 for r in results if r.severity_correct)
    both_correct = sum(1 for r in results if r.category_correct and r.severity_correct)

    return EvaluationReport(
        model=model,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_tests=total,
        category_accuracy=cat_correct / total if total > 0 else 0,
        severity_accuracy=sev_correct / total if total > 0 else 0,
        combined_accuracy=both_correct / total if total > 0 else 0,
        avg_latency_ms=statistics.mean(latencies) if latencies else 0,
        p95_latency_ms=statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0),
        p99_latency_ms=statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else (max(latencies) if latencies else 0),
        results=[asdict(r) for r in results],
        errors=errors,
    )


def evaluate_heuristic(test_cases: list[dict] | None = None) -> EvaluationReport:
    """Evaluate heuristic baseline."""

    if test_cases is None:
        test_cases = TEST_OBSERVATIONS

    results: list[TestResult] = []
    latencies: list[float] = []

    print("\nEvaluating: Heuristic Baseline")
    print("=" * 60)

    for i, test in enumerate(test_cases, 1):
        start_time = time.perf_counter()
        pred_cat, pred_sev = heuristic_classify(test["summary"])
        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies.append(latency_ms)

        cat_correct = pred_cat == test["expected_category"]
        sev_correct = pred_sev == test["expected_severity"]

        results.append(
            TestResult(
                observation=test,
                predicted_category=pred_cat,
                predicted_severity=pred_sev,
                category_correct=cat_correct,
                severity_correct=sev_correct,
                latency_ms=latency_ms,
            )
        )

        status = "✓" if (cat_correct and sev_correct) else "✗"
        print(f"\nTest {i}: {status}")
        print(f"  Category: {pred_cat} ({'✓' if cat_correct else '✗'})")
        print(f"  Severity: {pred_sev} ({'✓' if sev_correct else '✗'})")

    total = len(results)
    cat_correct = sum(1 for r in results if r.category_correct)
    sev_correct = sum(1 for r in results if r.severity_correct)
    both_correct = sum(1 for r in results if r.category_correct and r.severity_correct)

    return EvaluationReport(
        model="heuristic",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_tests=total,
        category_accuracy=cat_correct / total if total > 0 else 0,
        severity_accuracy=sev_correct / total if total > 0 else 0,
        combined_accuracy=both_correct / total if total > 0 else 0,
        avg_latency_ms=statistics.mean(latencies) if latencies else 0,
        p95_latency_ms=0,  # Too fast to measure meaningfully
        p99_latency_ms=0,
        results=[asdict(r) for r in results],
        errors=[],
    )


def print_report(report: EvaluationReport) -> None:
    """Print evaluation report."""

    print("\n" + "=" * 60)
    print(f"EVALUATION REPORT: {report.model}")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Total Tests: {report.total_tests}")
    print()
    print("ACCURACY:")
    print(f"  Category Accuracy:   {report.category_accuracy:.1%}")
    print(f"  Severity Accuracy:   {report.severity_accuracy:.1%}")
    print(f"  Combined Accuracy:   {report.combined_accuracy:.1%}")
    print()
    print("LATENCY:")
    print(f"  Average: {report.avg_latency_ms:.1f}ms")
    print(f"  P95:     {report.p95_latency_ms:.1f}ms")
    print(f"  P99:     {report.p99_latency_ms:.1f}ms")

    if report.errors:
        print()
        print(f"ERRORS: {len(report.errors)}")
        for error in report.errors[:5]:  # Show first 5
            print(f"  - {error}")

    print()

    # Compare to target
    if report.combined_accuracy >= 0.80:
        print("✓ PASS: Combined accuracy meets 80% target")
    else:
        print("✗ FAIL: Combined accuracy below 80% target")

    if report.avg_latency_ms <= 3000:
        print("✓ PASS: Average latency meets 3s target")
    else:
        print("✗ FAIL: Average latency exceeds 3s target")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Ollama synthesis for Osk",
    )
    parser.add_argument(
        "--model",
        default="llama3.2:3b",
        help="Ollama model to test (default: llama3.2:3b)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare all available models",
    )
    parser.add_argument(
        "--heuristic",
        action="store_true",
        help="Include heuristic baseline",
    )
    parser.add_argument(
        "--json-output",
        help="Save results to JSON file",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server URL",
    )

    args = parser.parse_args()

    # Check Ollama is reachable
    try:
        response = requests.get(f"{args.ollama_url}/api/tags", timeout=5)
        response.raise_for_status()
        models_data = response.json()
        available_models = [m["name"] for m in models_data.get("models", [])]
        print(f"Connected to Ollama. Available models: {', '.join(available_models)}")
    except Exception as e:
        print(f"Error connecting to Ollama at {args.ollama_url}: {e}")
        print("Make sure Ollama is running: ollama serve")
        return 1

    all_reports: list[EvaluationReport] = []

    if args.compare:
        # Test all available models
        models_to_test = [m for m in available_models if ":" in m]
        # Prefer smaller models for testing
        priority_models = ["llama3.2:3b", "phi4-mini", "qwen2.5:3b", "gemma3:4b"]
        for pm in priority_models:
            if pm in available_models and pm not in models_to_test:
                models_to_test.insert(0, pm)

        for model in models_to_test[:4]:  # Test up to 4 models
            if model not in available_models:
                print(f"\nSkipping {model} (not pulled)")
                continue
            report = evaluate_model(model, args.ollama_url)
            print_report(report)
            all_reports.append(report)
    else:
        # Test single model
        if args.model not in available_models:
            print(f"Model {args.model} not found. Pulling...")
            import subprocess

            subprocess.run(["ollama", "pull", args.model], check=True)

        report = evaluate_model(args.model, args.ollama_url)
        print_report(report)
        all_reports.append(report)

    if args.heuristic:
        report = evaluate_heuristic()
        print_report(report)
        all_reports.append(report)

    # Save JSON output
    if args.json_output:
        output = {
            "reports": [asdict(r) for r in all_reports],
            "summary": {
                "best_model": max(all_reports, key=lambda r: r.combined_accuracy).model,
                "best_accuracy": max(r.combined_accuracy for r in all_reports),
            },
        }
        with open(args.json_output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {args.json_output}")

    # Return exit code based on success
    best_accuracy = max(r.combined_accuracy for r in all_reports if r.model != "heuristic")
    return 0 if best_accuracy >= 0.80 else 1


if __name__ == "__main__":
    sys.exit(main())
