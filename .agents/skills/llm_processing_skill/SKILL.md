---
name: SolarWatch LLM Processing Skill
description: Guide for implementing cognitive analysis with anti-hallucination validation pipeline
---

# SolarWatch LLM Processing Skill

## Scope

This skill covers **Step 3 (Cognitive Processing & Validation)** — the most critical step in the pipeline. It orchestrates LLM analysis of reviews and applies the anti-hallucination validation layer.

## Architecture

```
src/processing/
├── llm_client.py            # LLM API abstraction (Gemini / OpenAI)
├── prompt_templates.py      # System Prompt & User Prompt templates
├── response_parser.py       # JSON parsing + Pydantic validation
├── hallucination_guard.py   # Anti-hallucination: evidence_quote verification
└── processor.py             # Main orchestrator
```

## Processing Flow

```
raw_reviews (is_analyzed=False)
  → Batch Loader (50/batch)
    → Prompt Builder (system + user prompt)
      → LLM API Call (llm_client.py)
        → Response Parser (Pydantic validation)
          → Hallucination Guard ← CRITICAL CHECKPOINT
            ├── PASS → Write to processed_reviews (hallucination_check_passed=True)
            └── FAIL → Write to processed_reviews (hallucination_check_passed=False, business fields=NULL)
  → Mark raw_review.is_analyzed = True
```

## Implementation Rules

### LLM Client (`llm_client.py`)
- Support two providers: `gemini` (via `google-genai`) and `openai`
- Read provider/model/temperature from `settings.yaml → llm` config
- Expose a single async method: `analyze(system_prompt, user_prompt) → str`
- Log every call with model version for reproducibility
- Handle rate limits and transient errors with retry logic

### Prompt Templates (`prompt_templates.py`)
- `SYSTEM_PROMPT`: Defines the analyst role, 4+1 category framework, persona classification, severity assessment, sarcasm detection rules, and evidence_quote VERBATIM extraction rule
- `USER_PROMPT_TEMPLATE`: Formatted with `app_name`, `source_platform`, `region_iso`, `rating`, `version`, `review_date`, `content`
- **Critical rule in SYSTEM_PROMPT:** Evidence quote must be an EXACT substring of the original review text. No translation, no paraphrasing
- Force JSON-only output (no markdown wrapping, no explanatory text)

### Response Parser (`response_parser.py`)
- Parse LLM response string via `json.loads()`
- Validate against a Pydantic model with these fields:
  - `primary_category`: must be in `VALID_CATEGORIES`
  - `user_persona`: must be in `VALID_PERSONAS`
  - `impact_severity`: must be in `VALID_SEVERITIES`
  - `is_sarcasm`: bool
  - `evidence_quote`: str (non-empty)
  - `sentiment_score`: float in [-1.0, 1.0]
  - `root_cause_tag`: str or None
- If JSON parsing fails: log the raw response, return None (skip this review)

### Hallucination Guard (`hallucination_guard.py`) — MOST CRITICAL MODULE
- **Three-level validation strategy:**
  1. **Level 1 — Exact substring:** `normalize_text(quote) in normalize_text(content)` — uses NFKC normalization
  2. **Level 2 — Fuzzy match:** Sliding window with `SequenceMatcher`, threshold ≥ 0.85
  3. **Level 3 — Token overlap:** `len(quote_tokens & content_tokens) / len(quote_tokens)` ≥ 0.85
- **Default mode:** `strict_mode=True` (only Level 1 passes)
- **Never skip this step.** Every record must go through validation

### Sarcasm Correction
- Applied in `processor.py` AFTER hallucination check passes
- Rule: `if is_sarcasm == True and sentiment_score > 0 → sentiment_score = -abs(sentiment_score)`
- Rationale: German/European users frequently use ironic expressions like "Wunderbar, funktioniert gar nicht"

### Processor Orchestrator (`processor.py`)
- Batch size: `settings.llm.batch_size` (default 50)
- For each unprocessed review:
  1. Build prompt → 2. Call LLM → 3. Parse response → 4. Validate evidence → 5. Apply sarcasm correction → 6. Write to DB
- **Hallucination records:** When `hallucination_guard` returns `is_valid=False`, still write the record but with `hallucination_check_passed=False` and business fields set to NULL
- Record `llm_model_version` on every processed review
- Mark `raw_review.is_analyzed = True` regardless of hallucination result

## Constraints

- **Never skip hallucination validation** — this is a hard rule
- **Log raw LLM response** on parse failure — needed for debugging prompt issues
- **Batch commit** — commit to DB after each batch, not after each review
- **Record model version** — `llm_model_version` must be populated on every record
- **Do not translate** review content — evidence_quote matching requires original language

## Acceptance Criteria

1. LLM responds with valid JSON in ≥95% of cases
2. `hallucination_check_passed=True` rate ≥ 95%
3. German sarcasm test cases are correctly detected and sentiment corrected
4. `test_hallucination_guard.py` has ≥ 10 test cases covering all 3 levels
5. Processing 500+ reviews completes without errors

## 💻 Code Examples & Anti-Patterns (CRITICAL FOR AI)

### 🚫 Anti-Patterns
- **NO:** 不要使用 `json.loads(response)` 去手动提取字段。必须先 `json.loads()` 再交给 Pydantic 校验。
- **NO:** 不要在 Prompt 中使用 Markdown 代码块（如 ` ```json ... ``` `），必须要求 LLM 仅输出纯 JSON 字符串。
- **NO:** 不要在 `hallucination_guard.py` 中 import LLM 相关的库，该模块必须保持纯 Python 字符串操作。
- **NO:** 不要把 `is_analyzed = True` 的标记放在 hallucination 校验之前，必须在整条记录完全处理完毕后再标记。

### ✅ Pydantic Model Standard

在 `response_parser.py` 中，必须使用以下结构进行校验：

```python
from pydantic import BaseModel, Field
from typing import Optional
# ⚠️ 枚举定义在 constants.py 中，不是 database.py
from src.config.constants import PrimaryCategory, UserPersona, ImpactSeverity

class LLMResponseSchema(BaseModel):
    primary_category: PrimaryCategory
    user_persona: UserPersona
    impact_severity: ImpactSeverity
    is_sarcasm: bool = Field(..., description="True if irony/sarcasm is detected")
    evidence_quote: str = Field(..., min_length=5, description="VERBATIM substring from original text")
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    root_cause_tag: Optional[str] = None
```

### ✅ Hallucination Guard 调用方式

```python
from src.utils.text_utils import normalize_text

# Level 1: 精确子串匹配 (归一化后)
def check_evidence(content: str, quote: str) -> bool:
    return normalize_text(quote) in normalize_text(content)

# ⚠️ normalize_text 使用 NFKC，不是 NFC
```

### ✅ 反讽修正必须在校验之后

```python
# 正确顺序：先校验，再修正
validation = validate_evidence_quote(content, parsed.evidence_quote)
if validation.is_valid and parsed.is_sarcasm and parsed.sentiment_score > 0:
    parsed.sentiment_score = -abs(parsed.sentiment_score)
```
