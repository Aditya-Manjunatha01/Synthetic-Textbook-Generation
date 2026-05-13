# Synthetic Textbook Generation Pipeline — Reference Document

> **Status:** Current as of May 2026. Supersedes all earlier design documents.  
> This document, the code files, and the prompt files together form the complete specification.

---

## 1. Overview

The pipeline generates a complete, pedagogically structured synthetic textbook for any physics or science domain. It uses two LLM models in a teacher–auditor pattern across three phases:

- **Teacher model** (`google/gemma-4-31B-it`) — generates content, outlines, retrieval requests
- **Auditor model** (`Qwen/Qwen3-32B`) — reviews, critiques, maintains state files (STM, registry, concept index, summaries)

The pipeline is fully resumable — every stage checkpoints to disk. Re-running the same command picks up exactly where it left off.

---

## 2. High-Level Architecture

```
Phase 1   →  Chapter names                          (Prompt 1)
Phase 1.1 →  Section names per chapter              (Prompt 2)
Phase 2   →  Subsection names per section           (Prompt 3)
                        ↓
Phase 3   →  Content generation per subsection      (Prompts 4–9, 6 turns each)
```

**Phase 3 turn sequence (per subsection):**

```
Turn 1  (Prompt 4) — Teacher:  retrieval request (which summaries + concept sections to fetch)
Turn 2a (Prompt 5) — Teacher:  chain-of-thought outline
Turn 3a (Prompt 6) — Auditor:  outline review and annotation
Turn 2b (Prompt 7) — Teacher:  full content generation
Turn 3b (Prompt 8) — Auditor:  STM update + subsection summary file
Turn 3c (Prompt 9) — Auditor:  notation registry delta + concept index delta
```

---

## 3. Configuration (`config.py`)

All pipeline-wide settings live here. No CLI arguments are used.

| Setting | Purpose |
|---|---|
| `TOPIC` | The textbook subject (e.g. `"thermodynamics"`) |
| `USER_LEVEL` | Audience calibration (see §11) |
| `TEACHER_MODEL` | Gemma 4-31B — content generation |
| `AUDITOR_MODEL` | Qwen3-32B — review and state maintenance |
| `API_HOST / API_PORT / API_KEY` | Local OpenAI-compatible inference endpoint |
| `MAX_TOKENS` | 4096 — Phase 3 content calls |
| `SKELETON_MAX_TOKENS` | 16384 — Phase 1/1.1/2 calls (large JSON outputs) |
| `MAX_RETRIEVAL_REQUESTS` | 10 — cap on summary IDs the teacher can request per turn |
| `KB_RAG_PLACEHOLDER` | Stub for future knowledge-base RAG integration |
| `OUTPUT_DIR` | Root output directory (`textbook_output/`) |

---

## 4. Output Directory Structure

```
textbook_output/
├── skeleton.json              # Full structural skeleton with resume markers
├── stm.txt                    # Current short-term memory (updated each subsection)
├── registry/
│   └── registry_sec_{sec_id}.txt   # Per-section notation registry (e.g. registry_sec_1_2.txt)
├── concepts/
│   └── concepts_sec_{sec_id}.txt   # Per-section concept index (e.g. concepts_sec_1_2.txt)
├── summaries/
│   └── {sub_id}.txt           # One summary file per completed subsection
├── content/
│   └── {sub_id}.md            # One content file per completed subsection
└── logs/
    └── pipeline.log
```

---

## 5. Phase 1 — Chapter Names (Prompt 1)

**Model:** Teacher  
**Input variables:** `{{topic_name}}`, `{{user_level}}`  
**Output:** JSON object `{"1": "Chapter Name", "2": "Chapter Name", ...}`

The teacher generates the full chapter list for the textbook in one shot. Integer keys are chapter IDs. Output is validated — keys must be integers, values must be non-empty strings and not placeholder garbage values.

**Resume:** Skipped entirely if `skeleton.json` already contains a non-empty `chapters` list.

**Retry logic:** Up to 3 retries with feedback. On each failure the model receives its previous response and a specific description of the validation error. Falls back to best-effort parse on exhaustion rather than crashing.

---

## 6. Phase 1.1 — Section Names (Prompt 2)

**Model:** Teacher  
**Input variables:** `{{topic_name}}`, `{{chapter_list}}`, `{{chapter_id}}`, `{{chapter_name}}`, `{{previous_chapters_sections}}`, `{{user_level}}`  
**Output:** JSON object `{"1.1": "Section Name", "1.2": "Section Name", ...}`

One LLM call per chapter. Keys must follow `chapter_id.section_num` format (e.g. `"1.1"`, `"1.2"`). The `{{previous_chapters_sections}}` context uses a **lookback window of 2 chapters** — older chapters show only their name (sections omitted) to control context size.

**Chapter cap:** Maximum 10 chapters enforced in the prompt.  
**Section cap:** 4–6 sections per chapter enforced in the prompt.

**Resume:** Each chapter is tracked in `skeleton["_sections_done"]`. Chapters already in this set are skipped.

**Checkpoint:** Written to `skeleton.json` after each chapter completes.

---

## 7. Phase 2 — Subsection Names (Prompt 3)

**Model:** Teacher  
**Input variables:** `{{topic_name}}`, `{{chapter_list}}`, `{{previous_chapter_sections}}`, `{{chapter_id}}`, `{{chapter_name}}`, `{{section_list}}`, `{{current_chapter_subsections_so_far}}`, `{{section_id}}`, `{{section_name}}`, `{{user_level}}`  
**Output:** JSON object `{"1.2": [{"id": "1.2.1", "name": "...", "type": "...", "difficulty": "..."}, ...]}`

**Critical design decision — per-section calls, not per-chapter:**  
Earlier designs called Prompt 3 once per chapter producing all subsections at once. This caused JSON truncation failures for large chapters. The current design calls Prompt 3 **once per section**, asking only for that section's subsections. The output is a single-key JSON object whose key is the current `section_id`.

**Subsection cap:** Each section must have **between 5 and 10 subsections**. This is enforced both in the prompt instruction and in `_validate_section_subsections` which raises a `ValueError` if the count is outside this range.

**Context passed:**
- `{{previous_chapter_sections}}` — sections of the immediately preceding chapter only (not a sliding window — just one chapter back)
- `{{current_chapter_subsections_so_far}}` — subsections of sections already completed in the current chapter, used to ensure narrative flow within a chapter

**Resume:** Sections already in `skeleton["_subsections_done"]` for a chapter are skipped. Within a chapter, sections with non-empty `subsections` lists are also skipped. The chapter is marked done in `_subsections_done` only after all its sections complete.

**Checkpoint:** Written to `skeleton.json` after every section (not just every chapter).

**Entry normalisation:** Subsection entries may arrive as full dicts or plain strings. `_parse_subsection_list` handles both, synthesising an `id` for plain strings.

---

## 8. The Condensed Skeleton Format

Throughout Phase 3, instead of passing `json.dumps(skeleton)` (which explodes in size), a condensed flat-text representation is generated by `_fmt_skeleton_condensed(skeleton)`:

```
Chapter 1: Thermodynamic Systems
  1.1 System Types and Boundaries
    1.1.1 Open Systems [theory, foundational]
    1.1.2 Closed Systems [theory, foundational]
    1.1.3 Exercise: Identifying System Types [exercise, foundational]
  1.2 State Variables
    ...
Chapter 2: Laws of Thermodynamics
  ...
```

This is ~8× smaller than pretty-printed JSON and contains all the structural information the model actually needs. The `type` and `difficulty` fields are inlined in brackets.

---

## 9. State Files Explained

### 9.1 Short-Term Memory (`stm.txt`)

A rolling prose summary updated by the auditor after every subsection (Turn 3b). It captures:
- Key concepts just introduced
- Open threads to continue
- What the next 1–2 subsections should build on

On resume, `stm.txt` is read from disk to restore continuity. Bootstrap value is used for the very first subsection.

### 9.2 Subsection Summaries (`summaries/{sub_id}.txt`)

Each summary is a structured record of one subsection — key definitions, results, notation introduced. Used by the teacher in Turn 1 when it requests context about earlier subsections.

### 9.3 Notation Registry — Section-Scoped

**File:** `registry_sec_{ch_id}_{sec_id}.txt`  
**Written by:** Turn 3c (auditor delta), appended/updated after each subsection.  
**Format:** `<<SYMBOL: \vec{F}>>` ... `<</SYMBOL>>` blocks.

**Scope design:**

| Scope | File | Used when |
|---|---|---|
| Section-local | `registry_sec_{ch}_{sec}.txt` | Passed to Turn 3c so the auditor knows what symbols already exist in this section |
| Global | `registry_global.txt` | Populated during post-processing resolution only — not used during generation |

**During generation:** The auditor receives only the current section's registry. Cross-section symbol conflicts are tolerated and resolved in a separate post-processing step after the full textbook is generated.

**Post-processing resolution:** A separate script walks all section registry files, identifies semantic duplicates (same meaning, different symbol), picks canonical symbols, and patches the relevant `content/{sub_id}.md` files.

**Why not pass the full registry:** A registry that spans all prior sections explodes to tens of thousands of tokens by Chapter 3. Section-scoping keeps each file to the size of one section's notation — typically 20–40 entries.

### 9.4 Concept Index — Section-Scoped

**File:** `concepts_ch{ch_id}_sec{sec_id}.txt`  
**Written by:** Turn 3c (auditor), appended after each subsection without being given the existing file (auditor emits freely — see rationale below).  
**Format:** `<<CONCEPT: concept name>>` ... `<</CONCEPT>>` blocks.

**Retrieval pattern:** The teacher requests specific sections' concept files in Turn 1 (same prompt as summary retrieval). The pipeline fetches the requested concept files and injects them into Prompts 5 and 7 as `{{fetched_concepts}}` alongside `{{fetched_summaries}}`.

**Why auditor doesn't see existing concept file in Turn 3c:** Small within-section concept redundancy is tolerable. Keeping the concept file out of Turn 3c's context reduces prompt size for every subsection. Symbol conflicts are more critical (mathematical notation must be consistent); concept prose duplication is harmless.

---

## 10. Phase 3 — Content Generation (Prompts 4–9)

Phase 3 iterates over all subsections in document order (chapter → section → subsection). The flat ordered list is produced by `get_all_subsections(skeleton)`.

### Resume Logic

For each subsection, before any LLM call:

1. **Both files exist and non-empty** (`content/{id}.md` AND `summaries/{id}.txt`) → fully skip, reload STM from disk.
2. **Content exists, summary missing/empty** → Turn 3b crashed last time. Re-run Turn 3b + Turn 3c only, skip Turns 1, 2a, 3a, 2b.
3. **Neither or content missing** → run all 6 turns.

### 10.1 Turn 1 — Teacher Retrieval Request (Prompt 4)

**Model:** Teacher  
**Variables:** `{{subsection_id}}`, `{{subsection_name}}`, `{{skeleton_past}}` (condensed format), `{{stm}}`, `{{rag_chunks}}`, `{{user_level}}`

The teacher reads the condensed skeleton and current STM, then decides what context it needs. It emits:

```xml
<RETRIEVAL_REQUEST>
{
  "summaries": ["1.1.3", "1.2.1"],
  "concept_sections": ["1.1", "1.2"]
}
</RETRIEVAL_REQUEST>
```

**Validation:**
- `summaries` IDs must be in `subsections[:current_index]` — only already-completed subsections are valid. The immediately preceding subsection is excluded (its content is already in the STM).
- `concept_sections` IDs must refer to fully completed sections (earlier chapters or earlier sections in the current chapter).
- Total summary IDs capped at `MAX_RETRIEVAL_REQUESTS` (10).

The pipeline then fetches the requested summary files and concept files from disk and builds `fetched_summaries` and `fetched_concepts` strings.

**Note:** `{{rag_chunks}}` is currently `KB_RAG_PLACEHOLDER` — a stub for future knowledge-base integration.

### 10.2 Turn 2a — Teacher CoT Outline (Prompt 5)

**Model:** Teacher  
**Variables:** `{{subsection_id}}`, `{{subsection_name}}`, `{{skeleton}}`, `{{stm}}`, `{{registry_txt}}` (current section registry), `{{fetched_summaries}}`, `{{fetched_concepts}}`, `{{rag_chunks}}`, `{{user_level}}`

The teacher produces a chain-of-thought outline for the subsection — the pedagogical plan, notation to introduce, concepts to cover, connections to prior material. Output is extracted from `<OUTLINE>...</OUTLINE>`.

### 10.3 Turn 3a — Auditor Outline Review (Prompt 6)

**Model:** Auditor  
**Variables:** `{{subsection_id}}`, `{{subsection_name}}`, `{{cot_outline}}`, `{{registry_txt}}` (current section registry), `{{user_level}}`

The auditor reviews the teacher's outline for consistency, coverage, notation correctness, and level-appropriateness. It annotates the outline with comments and suggestions. Output extracted from `<ANNOTATED_OUTLINE>...</ANNOTATED_OUTLINE>`.

### 10.4 Turn 2b — Teacher Content Generation (Prompt 7)

**Model:** Teacher  
**Variables:** `{{subsection_id}}`, `{{subsection_name}}`, `{{skeleton}}`, `{{stm}}`, `{{registry_txt}}`, `{{fetched_summaries}}`, `{{fetched_concepts}}`, `{{rag_chunks}}`, `{{annotated_outline}}`, `{{user_level}}`

The teacher writes the full subsection content as Markdown, incorporating the auditor's feedback on the outline. Output extracted from `<CONTENT>...</CONTENT>` and written to `content/{sub_id}.md`.

### 10.5 Turn 3b — Auditor STM + Summary (Prompt 8)

**Model:** Auditor  
**Variables:** `{{subsection_id}}`, `{{subsection_name}}`, `{{subsection_content}}`, `{{next_subsection_name}}`, `{{subsection_after_next_name}}`, `{{user_level}}`

The auditor reads the completed content and produces:
- `<STM>...</STM>` — updated short-term memory for the next subsection
- `<SUMMARY>...</SUMMARY>` — archival summary written to `summaries/{sub_id}.txt`

**Retry logic:** Uses `_call_auditor_with_retry`. Both tags must be present and non-empty. On failure, the auditor receives its previous response and specific feedback naming the missing tags. Up to 3 retries before falling back gracefully.

**On STM failure:** If STM is empty after all retries, the previous `stm.txt` is kept (not overwritten). Pipeline continues.

### 10.6 Turn 3c — Auditor Registry + Concept Delta (Prompt 9)

**Model:** Auditor  
**Variables:** `{{subsection_id}}`, `{{subsection_name}}`, `{{subsection_content}}`, `{{registry_txt}}` (current section registry), `{{user_level}}`

The auditor emits:
- `<REGISTRY_DELTA>...</REGISTRY_DELTA>` — `<<SYMBOL: ...>>` blocks for new or updated notation
- `<CONCEPT_DELTA>...</CONCEPT_DELTA>` — `<<CONCEPT: ...>>` blocks for new concepts

**Registry delta** is applied to `registry/registry_sec_{sec_id}.txt` via `apply_delta("SYMBOL")` — upserts by symbol key.  
**Concept delta** is applied to `concepts/concepts_sec_{sec_id}.txt` via `apply_delta("CONCEPT")` — upserts by concept name.

**Note:** REGISTRY_DELTA and CONCEPT_DELTA missing blocks are logged at DEBUG — a subsection may legitimately introduce no new notation or concepts.

---

## 11. Difficulty / Audience Level (`USER_LEVEL`)

Set in `config.py`. Threaded into all 9 prompts via `{{user_level}}`.

**Instruction line in every `system.md`:**
```
This textbook is written for a **{{user_level}}** audience. Calibrate your vocabulary,
assumed prerequisites, mathematical depth, and the rigour of derivations to match
exactly this level — neither oversimplify nor assume knowledge beyond it.
```

**Recommended values:**

| `USER_LEVEL` | Typical audience |
|---|---|
| `"middle school student"` | Ages 11–14, arithmetic and basic algebra only |
| `"high school student"` | Pre-calculus, introductory physics |
| `"undergraduate (first year)"` | Calculus started, basic mechanics just beginning |
| `"undergraduate (third year)"` | Full calculus, linear algebra, classical mechanics complete |
| `"postgraduate"` | Masters level, comfortable with graduate-level texts |
| `"PhD researcher"` | Deep domain familiarity; focus on precision and nuance |

---

## 12. Key Utilities

### `parse_json_response` (`disk_utils.py`)
Strips markdown code fences, finds the first `{` or `[`, bracket-walks to find the matching closer, returns parsed JSON. Handles preamble text before the JSON object.

### `parse_block` (`disk_utils.py`)
Extracts content between `<TAG>...</TAG>` XML-style delimiters. Returns empty string if not found (never raises).

### `apply_delta` (`disk_utils.py`)
Upserts `<<TAG: key>>...</TAG>` blocks into a target file. If the key exists, replaces the whole block; if not, appends it. The replacement uses a `lambda` in `re.sub` to avoid backslash interpretation of LaTeX symbols (e.g. `\delta`, `\vec{F}`).

### `load_prompt` (`prompts.py`)
Reads `prompt_{n}/system.md` and `prompt_{n}/user.md` from `PROMPTS_DIR`. Substitutes all `{{placeholder}}` tokens. Warns if any placeholders remain unfilled after substitution.

### `_call_with_retry` (`skeleton_builder.py`)
Retry+feedback loop for skeleton phases (Prompts 1–3). Appends the model's failed response and a specific error description to the message history, then calls again. Multi-turn correction rather than a fresh start.

### `_call_auditor_with_retry` (`phase3_loop.py`)
Used for Turn 3b. Checks that all required XML tags are present and non-empty before accepting the response. On failure, sends the model its previous response with specific tag-level feedback. Up to 3 retries before falling back gracefully.

---

## 13. Token Budget Management

Context size is managed through several design decisions:

| Problem | Solution |
|---|---|
| Full skeleton JSON too large | Condensed flat-text format (~8× smaller) |
| Global registry explodes across chapters | Per-section registry files; only current section passed |
| Global concept index explodes | Per-section concept files; model requests specific sections on demand |
| Previous chapters' sections too large in Phase 1.1 | Lookback window of 2 chapters; older chapters show name only |
| Summaries could be requested excessively | Capped at `MAX_RETRIEVAL_REQUESTS = 10` |
| Concept files could be large | Model requests by section granularity, not subsection; sections are bounded |

---

## 14. Error Handling and Robustness

| Failure mode | How handled |
|---|---|
| LLM returns non-JSON for skeleton prompts | `parse_json_response` strips fences, bracket-walks; retry loop on failure |
| Skeleton validation fails (wrong keys, garbage values) | Retry with feedback describing exact error |
| Auditor omits required `<TAG>` | `_call_auditor_with_retry` retries with specific tag-level feedback |
| STM missing after retries | Previous `stm.txt` retained; pipeline continues |
| Summary missing after retries | Empty file written; logged as error; resume logic detects and re-runs Turn 3b |
| `re.sub` backslash error on LaTeX symbols in registry | Replacement passed as `lambda m, e=entry: e` — never interpreted as regex template |
| Crash mid-subsection (after content, before summary) | Resume logic detects content-without-summary; re-runs Turn 3b+3c only |
| API HTTP error | `RuntimeError` raised with status code and body |

---

## 15. Post-Processing (Registry Resolution)

After the full textbook is generated, a separate offline script handles global symbol conflicts:

1. Walk all `registry_sec_*.txt` files
2. Identify semantic duplicates (same physical quantity, different symbol across sections)
3. Pick canonical symbol for each quantity
4. Patch all relevant `content/{sub_id}.md` files with the canonical symbol
5. Write consolidated `registry_global.txt`

This step is **not part of the main pipeline** and runs once after generation is complete.

---

## 16. Prompt File Map

| Prompt | File location | Model | Phase | Purpose |
|---|---|---|---|---|
| 1 | `prompt_1/` | Teacher | Phase 1 | Generate chapter names |
| 2 | `prompt_2/` | Teacher | Phase 1.1 | Generate section names for one chapter |
| 3 | `prompt_3/` | Teacher | Phase 2 | Generate subsection names for one section (3–5 max) |
| 4 | `prompt_4/` | Teacher | Phase 3 Turn 1 | Retrieval request: which summaries + concept sections to fetch |
| 5 | `prompt_5/` | Teacher | Phase 3 Turn 2a | Chain-of-thought outline |
| 6 | `prompt_6/` | Auditor | Phase 3 Turn 3a | Outline review and annotation |
| 7 | `prompt_7/` | Teacher | Phase 3 Turn 2b | Full content generation |
| 8 | `prompt_8/` | Auditor | Phase 3 Turn 3b | STM update + subsection summary |
| 9 | `prompt_9/` | Auditor | Phase 3 Turn 3c | Notation registry delta + concept index delta |

Each prompt directory contains:
- `system.md` — system role and standing instructions (includes `{{user_level}}` directive)
- `user.md` — user turn with `{{placeholder}}` variables for runtime values

---

## 17. Known Gaps and Future Work

| Feature | Status |
|---|---|
| Knowledge-base RAG | Stubbed — `{{rag_chunks}}` receives `KB_RAG_PLACEHOLDER` in all prompts |
| Global registry resolution script | Designed (§15), not yet implemented — post-processing step after full generation |
| Book-level parallelism | Designed, not yet implemented — run N books concurrently via process pool |
| Current-section partial concept availability | The current section's concept file is partially populated during writing but not yet offered to the model as a special case |
| Turn 3b+3c merge | Attempted — reverted. Auditor attention dilutes across 4 tasks; REGISTRY_DELTA and CONCEPT_DELTA consistently empty when merged. Split calls (Prompts 8 and 9) remain the correct design. |
