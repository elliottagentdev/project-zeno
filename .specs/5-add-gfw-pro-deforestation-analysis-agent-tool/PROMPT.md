# Feature Spec: Add GFW Pro deforestation analysis agent tool

## Requirements

## Job Story
As a Zeno user with an AOI selected, when I ask for 'GFW Pro Analytical Results', I want Zeno to run a deforestation and disturbance analysis against my geometry and provide a downloadable CSV — so I can quickly access WRI/GFW Pro metrics without leaving the Zeno interface.

## What to build

### New analysis module: `src/agent/tools/gfw_pro_analysis.py`

Port the core logic from the GFW Pro `query3.py` script (provided externally). This script reads globally pre-computed zarr rasters at 10m resolution from WRI's S3 bucket and clips them to an input geometry to compute deforestation metrics.

**Zarr data sources** (read via `xarray.open_zarr`):
- `s3://gfwpro-users/op-external-user/v2/sbtn.area.zarr`
- `s3://gfwpro-users/op-external-user/v2/jrc.area.zarr`
- `s3://gfwpro-users/op-external-user/v2/mergedLoss.zarr`
- `s3://gfwpro-users/op-external-user/v3/intdist_date_conf.zarr/`

**Config env vars**:
- `GFW_PRO_DATA_PATH`: base path for local zarr files (e.g. `/mnt/e/datasets/gfwpro`). Falls back to S3 URIs above if unset.
- `GFW_PRO_ALERT_START_DATE`: ISO date string (default `2025-01-01`). Alerts on/after this date are counted.
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: for S3 access (already in .env or set externally)

**Output metrics** (per AOI, in hectares, 4 decimal places):
| Column | Description |
|---|---|
| name | AOI name |
| total_area | Total geometry area |
| sbtn_area | SBTN 1.1 natural forest |
| sbtn_loss_area | SBTN forest with TCL loss 2021–2024 |
| jrc_area | JRC 2020.2 forest |
| jrc_loss_area | JRC forest with TCL loss 2021–2024 |
| indig_area | Landmark indigenous/community lands |
| alert_area | High/highest confidence disturbance alerts since alert_start_date |
| sbtn_alert_area | alert_area ∩ SBTN forest |
| jrc_alert_area | alert_area ∩ JRC forest |

**Core functions**:
- `get_datasets() -> dict[str, xr.Dataset]`: open all 4 zarr files; cache as module-level singleton (open once, reuse)
- `clip_ds_to_geojson(ds, geojson_geom) -> xr.Dataset`: bbox slice + rioxarray clip
- `run_analysis(geojson_geometry: dict, name: str) -> pd.DataFrame`: compute all 9 metrics
- `dataframes_to_csv(dfs: list[pd.DataFrame]) -> str`: concatenate and serialize to CSV string

Run the analysis in `asyncio.to_thread()` so it doesn't block the FastAPI event loop.

**Data versions used** (for CSV header comment):
- TCL 2024 (umd_tree_cover_loss/v1.12)
- SBTN 1.1 (sbtn_natural_forests_map/v202504)
- JRC 2020.2 (jrc_global_forest_cover/v2020.2)
- Landmark (gfw_indigenous_community_and_indicative_lands/v202408)
- Integrated disturbance alerts (gfw_integrated_dist_alerts/v20260208)

### New agent tool: `gfw_pro_analysis`

Following the existing `@tool()` pattern (see `src/agent/tools/pick_dataset.py` for reference):

```python
@tool("gfw_pro_analysis")
async def gfw_pro_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[AgentState, InjectedState],
) -> Command:
    """Run GFW Pro deforestation and disturbance alert analysis for the current AOI.
    Returns SBTN/JRC forest area, tree cover loss 2021-2024, indigenous lands area,
    and integrated disturbance alerts. Results are provided as a downloadable CSV."""
```

The tool should:
1. Read `state["aoi"]` to get `{source, src_id, name}`
2. If `state["aoi_selection"]["aois"]` has multiple AOIs, run analysis for each
3. Call `get_geometry_data(source, src_id)` (from `src/shared/geocoding_helpers.py`) to get GeoJSON
4. Call `run_analysis(geojson, name)` in a thread pool
5. Concatenate results if multi-AOI
6. Return `Command` with `gfw_pro_csv` state key and a `ToolMessage`

### Register the tool
- Add `gfw_pro_analysis` to the `tools` list in `src/agent/graph.py`
- Add `gfw_pro_csv: Optional[str]` to `AgentState` in `src/agent/state.py`

### Dependencies
Add to `Pipfile` if not already present:
`xarray zarr fsspec s3fs rioxarray fiona shapely "dask[array,dataframe]"`

## Acceptance criteria
- [ ] `run_analysis()` produces correct output for the IDN test case from query3.py (sbtn_area ~994.6 ha, sbtn_loss ~59.95 ha, total_area ~1006 ha)
- [ ] Tool is callable from the agent (appears in `tools` list)
- [ ] `gfw_pro_csv` appears in agent state after tool runs
- [ ] Multi-AOI: running with 2 AOIs produces a 2-row CSV
- [ ] Analysis runs in a thread pool (non-blocking)
- [ ] Both S3 streaming and local path modes work based on `GFW_PRO_DATA_PATH`

## Discussion / Context

_No discussion comments yet._
---

## PLANNING METHODOLOGY — MANDATORY INSTRUCTIONS (LITE MODE)

> **YOU ARE THE ORCHESTRATOR. YOU MUST FOLLOW THIS METHODOLOGY EXACTLY.**
>
> When the user says "let's draft this" (or any variation like "draft it", "start planning", "go", etc.),
> you MUST execute the 3-stage lite pipeline described below.
>
> **DO NOT write a plan yourself. DO NOT skip stages. DO NOT summarize instead of launching agents.**
>
> If you write ANY plan content yourself instead of delegating to sub-agents via the Task tool,
> you have FAILED. Your ONLY job is to launch Task agents and wait for them to finish.

> **RULES FOR SUB-AGENTS (include these in every sub-agent prompt):**
>
> - Sub-agents write ALL work to files using Write/Edit tools
> - Sub-agents return ONLY: `Done. Output: [filepath]`
> - Sub-agents MUST write in chunks of ~4000 tokens max (Write tool, then Edit to append)
> - Sub-agents must NEVER return content, summaries, or explanations to the orchestrator
> - Violation of these rules will blow up the orchestrator's context window

> **VISUAL ASSETS:** The GitHub issue may include images (screenshots, mockups, diagrams) downloaded
> to `/mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/images/`. Sub-agents should use the Read tool to examine any images when relevant.

---

### Overview

This is the **lite pipeline** — a faster alternative to the full 6-stage pipeline.
It trades multi-draft competition and adversarial red-teaming for speed while keeping
codebase-grounded recon and dedicated validation.

You MUST execute these 4 stages in order. Each stage MUST use the Task tool to launch sub-agents.
You MUST NOT skip any stage. You MUST NOT combine stages. You MUST NOT do the work yourself.

0. **Stage 0**: YOU launch 3 parallel Task agents → each explores the codebase from a different angle
1. **Stage 1**: YOU launch 1 Task agent → drafts a single comprehensive plan balancing all architectural lenses
2. **Stage 2**: YOU launch 1 Task agent → validates the draft against requirements, codebase facts, ambiguities, and edge cases
3. **Stage 3**: YOU launch 1 Task agent → produces final SPEC.md incorporating validation findings

Total: 6 Task agent launches across 4 stages (Stage 0 through Stage 3). No shortcuts.

---

### Stage 0: Codebase Reconnaissance

YOU MUST launch 3 Task tool calls in a SINGLE message (parallel execution). Use model "sonnet".

**Each agent explores the actual codebase to ground all subsequent work in reality.**

**Agent A — Architecture & Structure:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Architecture Reconnaissance agent. You are a SUB-AGENT, not the orchestrator.
- Read the /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md file that the orchestrator provides in your working directory to understand what feature is being planned.
- Explore the actual codebase using Glob, Grep, and Read tools to understand:
  - Directory layout and project structure
  - Tech stack, frameworks, and languages used
  - Build system and deployment model
  - Key entry points and main modules
  - Database schemas and data layer architecture
  - If /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/images/ exists, use the Read tool to examine any images for visual context (screenshots, mockups, diagrams)
- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/architecture.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Focus on FACTS about the codebase, not opinions. Reference specific file paths.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/architecture.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Agent B — Relevant Code:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Relevant Code Reconnaissance agent. You are a SUB-AGENT, not the orchestrator.
- Read the /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md file that the orchestrator provides in your working directory to understand what feature is being planned.
- Explore the actual codebase using Glob, Grep, and Read tools to identify:
  - Files and modules most likely to be modified for this feature
  - Existing APIs, endpoints, and interfaces relevant to the feature
  - Data models, types, and schemas that would be affected
  - Integration points with external services or systems
  - Related existing functionality that the feature would interact with
- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/relevant_code.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Include actual code snippets, function signatures, and type definitions. Reference specific file paths and line numbers.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/relevant_code.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Agent C — Conventions & Constraints:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Conventions Reconnaissance agent. You are a SUB-AGENT, not the orchestrator.
- Read the /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md file that the orchestrator provides in your working directory to understand what feature is being planned.
- Explore the actual codebase using Glob, Grep, and Read tools to document:
  - Coding style and naming conventions used throughout
  - Error handling patterns (how errors are thrown, caught, reported)
  - Test framework, test file naming, test patterns and helpers
  - CI/CD configuration and quality gates
  - Dependency management approach
  - Existing abstractions and utilities that should be reused
  - Any CLAUDE.md, AGENTS.md, or contributing guidelines
- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/conventions.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Include concrete examples from the codebase. Reference specific file paths.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/conventions.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After all 3 complete:** Confirm all 3 files exist (/mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/relevant_code.md, /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/conventions.md), then proceed to Stage 1. Do NOT read the files.

---

### Stage 1: Comprehensive Draft

YOU MUST launch 1 Task tool call. Use model "opus".

**A single drafter balances all four architectural lenses into one comprehensive plan.**

**Prompt:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Plan Drafter. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md for full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/conventions.md for codebase context.

Draft a comprehensive implementation plan that balances these four perspectives:
  1. **Minimal Surgery**: Touch the fewest files. Reuse everything that exists. Prefer modifying existing code over creating new files.
  2. **Clean Architecture**: Proper separation of concerns, clear interfaces, extensibility where it matters.
  3. **Robustness**: Error handling, validation, edge cases, rollback and recovery paths.
  4. **Developer Experience**: Simplicity over cleverness. Clear naming. Obvious control flow. Minimal cognitive load.

Cover: architecture, specific file changes with file paths and function signatures, data models, API design, error handling, testing strategy, migration plan, and risks.
Be specific — reference actual file paths, function names, and code patterns from the recon documents.

- Write your plan to /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/draft.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/draft.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After completion:** Confirm the file exists, then proceed to Stage 2. Do NOT read the file.

---

### Stage 2: Combined Validation

YOU MUST launch 1 Task tool call. Use model "opus".

**A single validator performs requirements coverage, codebase fact-checking, ambiguity audit, and edge case analysis.**

**Prompt:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Plan Validator. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/conventions.md for codebase context.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/draft.md — this is the plan you must validate.

Perform a combined validation covering four areas:

**1. Requirements Coverage:**
For EACH requirement in /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md:
  - Is it addressed in the plan? WHERE exactly?
  - Is the acceptance criteria testable and specific?
  - What's missing?
Produce a requirements coverage matrix.

**2. Codebase Fact-Check:**
Use Glob, Grep, and Read tools to verify every factual claim in the plan:
  - Do referenced files and directories actually exist?
  - Are function signatures and API contracts correct?
  - Do data models and schemas match what's described?
  - Are there existing utilities the plan reinvents instead of reusing?
Document every factual error: what the plan claims vs what the codebase actually shows.

**3. Ambiguity Audit:**
For each major section:
  - What information is missing that a developer would need?
  - What has multiple valid interpretations?
  - What requires implicit knowledge not stated in the plan?
  - What order-of-operations dependencies are unstated?

**4. Edge Cases & Risks:**
  - Find edge cases NOT handled (empty inputs, concurrent access, partial failures, large data)
  - Find error paths NOT covered (network failures, auth failures, invalid data, timeouts)
  - Find internal contradictions or ordering dependencies that could break
  - Identify security concerns (injection, auth bypass, data exposure)

- Write your validation report to /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/validation.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/validation.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After completion:** Confirm the file exists, then proceed to Stage 3. Do NOT read the file.

---

### Stage 3: Final Spec

YOU MUST launch 1 Task tool call. Use model "opus".

**Prompt:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Final Spec agent. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/recon/conventions.md for codebase context.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/draft.md (the implementation plan).
- Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/validation.md (the validation report).

Produce the FINAL, COMPLETE implementation specification. It MUST include:

1. **Requirements Traceability Matrix**: For each requirement from the original issue, the exact
   section of this spec that addresses it. Any requirement NOT addressed must be flagged as a gap
   with explicit justification for why it was deferred.

2. **Validation Resolution Log**: For each finding from the validation report, document:
   - The finding (one-line summary)
   - Resolution: how it was fixed in this spec, OR why it was deferred (with justification)
   - Deferred items must include severity and recommended follow-up

3. **Implementation Plan**: Step-by-step instructions with:
   - Specific file paths and function signatures
   - Data models and schema changes
   - Implementation order with dependencies between steps
   - Each step must be independently verifiable

4. **Testing Strategy**: Grounded in the actual test framework and patterns found in recon.
   - Unit tests, integration tests, and edge case tests
   - Specific test file locations and naming conventions
   - Test data and fixture requirements

5. **Risk Register**: Unresolved risks with severity, likelihood, and mitigation strategies.

The spec must be ready to be handed to a developer or agent for implementation with ZERO questions.

- Write the final spec to /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/SPEC.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/SPEC.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After completion:** Read /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/SPEC.md and present it to the user. This is the ONLY file you read.

---

### Orchestrator Context Management — CRITICAL

**Your context is precious. Sub-agents have their own 200k token contexts. You do NOT.**

- Your ONLY job is to launch Task agents and confirm they completed. That's it.
- You need ~1k tokens per stage. If your context grows beyond ~15k tokens, you broke a rule.
- NEVER read sub-agent output files yourself (the ONLY exception: /mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/plans/SPEC.md at the very end)
- NEVER consume sub-agent return messages beyond confirming the word "Done"
- NEVER write plan content yourself — that's what the 6 sub-agents are for
- If a sub-agent fails, relaunch it. Do NOT do its work yourself as a fallback.


---

## Completion Protocol

When implementation is complete, the implementing agent must:

1. Create or update `DONE.md` in the spec directory.
2. Include the exact test commands run and their outcomes.
3. Summarize file changes and rationale in concise bullet points.
4. List any follow-up risks or deferred work.
