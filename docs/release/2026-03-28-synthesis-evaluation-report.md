# Osk Synthesis Evaluation Report

**Date:** 2026-03-28  
**Status:** Complete  
**Models Tested:** llama3.2:3b, phi4-mini, qwen3:8b  
**Baseline:** Heuristic keyword matching

---

## Executive Summary

This evaluation tested local LLM (Ollama) based semantic synthesis against the existing heuristic baseline for classifying civilian field observations.

**Key Finding:** The heuristic baseline outperforms all tested LLMs for this specific classification task.

**Recommendation for 1.1:** Keep heuristic as the default production backend. Ollama is available as an experimental option for operators who want to test local LLM capabilities.

---

## Test Methodology

### Dataset
- 20 diverse observation scenarios
- Mix of transcript and vision observations
- Edge cases and ambiguous situations
- Realistic field language

### Models Evaluated
| Model | Size | Hardware |
|-------|------|----------|
| llama3.2:3b | 3B params | RTX 3080 |
| phi4-mini | 3.8B params | RTX 3080 |
| qwen3:8b | 8B params | RTX 3080 |
| heuristic | N/A | CPU only |

### Metrics
- Category accuracy (6 classes)
- Severity accuracy (4 levels)
- Combined accuracy (both correct)
- Latency (P50, P95, P99)

---

## Results

### Accuracy Comparison

| Model | Category | Severity | Combined |
|-------|----------|----------|----------|
| **heuristic** | **85.0%** | **75.0%** | **65.0%** |
| qwen3:8b | 85.0% | 55.0% | 50.0% |
| llama3.2:3b | 65.0% | 60.0% | 35.0% |
| phi4-mini | 65.0% | 55.0% | 35.0% |

### Latency Comparison

| Model | Average | P95 | Status |
|-------|---------|-----|--------|
| heuristic | ~0ms | ~0ms | ✅ |
| llama3.2:3b | 520ms | 2.2s | ✅ |
| phi4-mini | 710ms | 3.2s | ⚠️ |
| qwen3:8b | 837ms | 4.0s | ⚠️ |

*Target: <3s average, <5s P95*

---

## Analysis

### Why Heuristic Wins

The classification task has clear keyword patterns:

| Pattern | Category | Example |
|---------|----------|---------|
| "police", "officer" | police_action | "Police advancing" |
| "block", "barrier" | blocked_route | "Road blocked" |
| "medical", "injury" | medical | "Someone injured" |
| "fight", "stampede" | escalation | "Fights breaking out" |
| "march", "crowd" | crowd_movement | "Group marching" |

These patterns are reliably captured by keyword matching, making the heuristic approach highly effective for this domain.

### LLM Behavior

**Strengths:**
- Better at nuanced language ("officer down" vs "police helping")
- Can infer severity from context
- Handles novel descriptions

**Weaknesses:**
- Over-classifies severity (tends toward "critical")
- Inconsistent with ambiguous inputs
- Higher latency (500ms-4s vs instant)

### Example: Test Case #6

**Input:** "Police are helping redirect traffic and keeping people safe"

| Model | Category | Severity | Correct? |
|-------|----------|----------|----------|
| Expected | community | info | - |
| Heuristic | community | info | ✅✅ |
| llama3.2:3b | police_action | info | ❌✅ |
| qwen3:8b | police_action | info | ❌✅ |

All LLMs fixated on "police" keyword, missing the helping context.

---

## Recommendations

### For Release 1.1

1. **Keep heuristic as default**
   - 85% category accuracy is production-ready
   - Zero latency overhead
   - Deterministic behavior

2. **Ollama as experimental option**
   - Available via config: `synthesis_backend: "ollama"`
   - Documented as "beta - accuracy being improved"
   - Useful for operators wanting local AI capabilities

3. **Future work (1.2+)**
   - Prompt engineering improvements
   - Fine-tuning on field observation corpus
   - Hybrid approach (heuristic + LLM for edge cases)

### Configuration Guidance

```yaml
# Recommended for production (default)
synthesis_backend: "heuristic"

# Experimental - for testing only
synthesis_backend: "ollama"
synthesis_model: "llama3.2:3b"
ollama_url: "http://localhost:11434"
```

### Hardware Requirements (Ollama Experimental)

| Model | Min RAM | GPU | Notes |
|-------|---------|-----|-------|
| llama3.2:3b | 4GB | Optional | Fastest, lowest accuracy |
| phi4-mini | 4GB | Optional | Good reasoning |
| qwen3:8b | 8GB | Recommended | Best LLM accuracy |

---

## Conclusion

The heuristic synthesis approach is validated as the optimal solution for Osk 1.1. The evaluation demonstrates that simple, well-designed heuristics can outperform general-purpose LLMs for narrow, well-defined classification tasks.

Ollama integration remains valuable as:
1. An experimental platform for future improvements
2. A foundation for more complex synthesis tasks (1.2+)
3. A local-first AI option for privacy-conscious deployments

---

## Artifacts

- Test script: `scripts/ollama_synthesis_test.py`
- Raw results: Available via script re-run
- This report: `docs/release/2026-03-28-synthesis-evaluation-report.md`

## Sign-off

| Role | Name | Date | Decision |
|------|------|------|----------|
| Technical Lead | | 2026-03-28 | Ship heuristic as default |
| Product Owner | | | Ollama as experimental |
