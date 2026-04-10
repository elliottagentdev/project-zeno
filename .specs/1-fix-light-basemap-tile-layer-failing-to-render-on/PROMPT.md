# Feature Spec: Fix Light basemap tile layer failing to render on map initialization

## Requirements

## Job Story
When Zeno returns a query result with a map, I want a geographic basemap (country borders, terrain, labels) to be visible by default, so I can orient the data overlay in geographic context without any manual workaround.

## Promise
After this ships: the default map view loads with a functioning basemap visible immediately when any query result renders. The AOI boundary and data layers render on top of the basemap and are not obscured by it. Users do not need to switch to Satellite as a workaround.

## Constraints
- Must not require a paid Mapbox API key — use a reliable free tile provider (e.g., CartoDB Positron or keep OpenStreetMap)
- The existing LayerControl UI for basemap switching (Light/Dark/Satellite) should continue to be user-accessible
- Must not touch the dynamic dataset layer rendering logic
- Layer rendering order must always be: basemap (bottom) → dynamically loaded dataset tile layer(s) → AOI outline(s) (top). This order must hold regardless of which dataset is active or which basemap is selected.

## Acceptance Criteria
- [ ] Running any query renders a visible geographic basemap by default
- [ ] The Light basemap renders country outlines, terrain, and labels over the AOI
- [ ] Satellite imagery option continues to work as it does now
- [ ] No additional API keys or credentials are needed for the default basemap to load
- [ ] The AOI boundary/polygon renders on top of all other layers
- [ ] Layer order is correct for all map renders: basemap at bottom, dataset tile layer(s) in the middle, AOI outline(s) on top

## Context
The map is rendered in `frontend/utils.py` using Folium. The base map is currently hardcoded to `tiles="OpenStreetMap"` in `folium.Map()`. There is a LayerControl with Light/Satellite options visible to the user, but the Light tile layer fails to render — the user sees a blank background and must switch to Satellite as a workaround. The fix should use a reliable free tile provider and ensure correct z-ordering of layers (basemap → dataset tiles → AOI).

## Discussion / Context

_No discussion comments yet._
---

## PLANNING METHODOLOGY — MANDATORY INSTRUCTIONS

> **YOU ARE THE ORCHESTRATOR. YOU MUST FOLLOW THIS METHODOLOGY EXACTLY.**
>
> When the user says "let's draft this" (or any variation like "draft it", "start planning", "go", etc.),
> you MUST execute the 5-stage multi-agent pipeline described below.
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
> to `/mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/images/`. Sub-agents should use the Read tool to examine any images when relevant.

---

### Overview

You MUST execute these 5 stages in order. Each stage MUST use the Task tool to launch sub-agents.
You MUST NOT skip any stage. You MUST NOT combine stages. You MUST NOT do the work yourself.

0. **Stage 0**: YOU launch 3 parallel Task agents → each explores the codebase from a different angle
1. **Stage 1**: YOU launch 4 parallel Task agents → each drafts an independent plan with a distinct architectural lens
2. **Stage 2**: YOU launch 1 Task agent → scores all 4 drafts against a structured rubric
3. **Stage 3**: YOU launch 1 Task agent → synthesizes a master plan using scored drafts
4. **Stage 4**: YOU launch 4 parallel Task agents → each adversarially red-teams the master plan
5. **Stage 5**: YOU launch 1 Task agent → produces final SPEC.md with traceability

Total: 13 Task agent launches across 5 stages (Stage 0 through Stage 5). No shortcuts.

---

### Stage 0: Codebase Reconnaissance

YOU MUST launch 3 Task tool calls in a SINGLE message (parallel execution). Use model "opus".

**Each agent explores the actual codebase to ground all subsequent work in reality.**

**Agent A — Architecture & Structure:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Architecture Reconnaissance agent. You are a SUB-AGENT, not the orchestrator.
- Read the /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md file that the orchestrator provides in your working directory to understand what feature is being planned.
- Explore the actual codebase using Glob, Grep, and Read tools to understand:
  - Directory layout and project structure
  - Tech stack, frameworks, and languages used
  - Build system and deployment model
  - Key entry points and main modules
  - Database schemas and data layer architecture
  - If /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/images/ exists, use the Read tool to examine any images for visual context (screenshots, mockups, diagrams)
- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Focus on FACTS about the codebase, not opinions. Reference specific file paths.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Agent B — Relevant Code:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Relevant Code Reconnaissance agent. You are a SUB-AGENT, not the orchestrator.
- Read the /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md file that the orchestrator provides in your working directory to understand what feature is being planned.
- Explore the actual codebase using Glob, Grep, and Read tools to identify:
  - Files and modules most likely to be modified for this feature
  - Existing APIs, endpoints, and interfaces relevant to the feature
  - Data models, types, and schemas that would be affected
  - Integration points with external services or systems
  - Related existing functionality that the feature would interact with
- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Include actual code snippets, function signatures, and type definitions. Reference specific file paths and line numbers.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Agent C — Conventions & Constraints:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Conventions Reconnaissance agent. You are a SUB-AGENT, not the orchestrator.
- Read the /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md file that the orchestrator provides in your working directory to understand what feature is being planned.
- Explore the actual codebase using Glob, Grep, and Read tools to document:
  - Coding style and naming conventions used throughout
  - Error handling patterns (how errors are thrown, caught, reported)
  - Test framework, test file naming, test patterns and helpers
  - CI/CD configuration and quality gates
  - Dependency management approach
  - Existing abstractions and utilities that should be reused
  - Any CLAUDE.md, AGENTS.md, or contributing guidelines
- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Include concrete examples from the codebase. Reference specific file paths.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After all 3 complete:** Confirm all 3 files exist (/mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md), then proceed to Stage 1. Do NOT read the files.

---

### Stage 1: Diverse Parallel Drafting

YOU MUST launch 4 Task tool calls in a SINGLE message (parallel execution). Use model "opus".
Each sub-agent gets a distinct architectural lens that forces genuinely different approaches.

**Drafter A — Minimal Surgery lens:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Minimal Surgery drafter. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- YOUR LENS: Achieve the requirements with the SMALLEST possible change set. Touch the fewest files. Reuse everything that exists. Avoid new abstractions. Prefer modifying existing code over creating new files.
- Write a detailed, complete implementation plan to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_1.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Cover: architecture, specific file changes, data models, API design, error handling, testing strategy, migration plan.
- Be specific — reference actual file paths, function names, and code patterns from the recon documents.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_1.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Drafter B — Clean Architecture lens:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Clean Architecture drafter. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- YOUR LENS: Design the RIGHT abstraction. Proper separation of concerns, clear interfaces, extensibility. Accept more files changed if the architecture is better. Think about how this feature fits into the broader system.
- Write a detailed, complete implementation plan to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_2.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Cover: architecture, specific file changes, data models, API design, error handling, testing strategy, migration plan.
- Be specific — reference actual file paths, function names, and code patterns from the recon documents.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_2.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Drafter C — Robustness-First lens:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Robustness-First drafter. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- YOUR LENS: Start from FAILURE MODES. What can go wrong? Design error handling, validation, and edge cases FIRST. Testing strategy drives the architecture. Every path must have explicit error handling. Consider rollback and recovery.
- Write a detailed, complete implementation plan to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_3.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Cover: architecture, specific file changes, data models, API design, error handling, testing strategy, migration plan.
- Be specific — reference actual file paths, function names, and code patterns from the recon documents.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_3.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Drafter D — Developer Experience lens:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Developer Experience drafter. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- YOUR LENS: Optimize for the NEXT DEVELOPER who reads this code. Simplicity over cleverness. Clear naming. Obvious control flow. Minimal cognitive load. If a junior developer would struggle to understand it, simplify it.
- Write a detailed, complete implementation plan to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_4.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Cover: architecture, specific file changes, data models, API design, error handling, testing strategy, migration plan.
- Be specific — reference actual file paths, function names, and code patterns from the recon documents.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_4.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After all 4 complete:** Confirm all 4 files exist, then proceed to Stage 2. Do NOT read the files.

---

### Stage 2: Rubric-Based Evaluation

YOU MUST launch 1 Task tool call. Use model "opus".

**This replaces free-form critique with structured scoring. One evaluator scores all 4 drafts comparatively.**

**Prompt:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Rubric Evaluator. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- Read ALL of: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_1.md through /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_4.md (4 drafts total).

Score EACH draft against this rubric (1-5 scale for each dimension):

**Requirements Coverage (1-5):**
  5 = Every requirement from the issue maps to a specific section with testable acceptance criteria
  3 = Most requirements addressed but some are vague or missing acceptance criteria
  1 = Multiple requirements missing or only superficially addressed

**Implementability (1-5):**
  5 = A developer could follow this with zero questions — exact file paths, function signatures, step-by-step order
  3 = Generally clear but some steps require interpretation or assumption
  1 = Vague hand-waving, missing specifics, ambiguous instructions

**Codebase Consistency (1-5):**
  5 = Follows all conventions from recon, builds on existing abstractions, respects patterns
  3 = Mostly consistent but ignores some existing patterns or reinvents existing utilities
  1 = Ignores existing code, introduces conflicting patterns, doesn't match the codebase style

**Completeness (1-5):**
  5 = Error handling, testing strategy, migration plan, and rollback all addressed
  3 = Happy path well-covered but error handling or testing partially addressed
  1 = Only covers the happy path, no error handling or testing strategy

**Feasibility (1-5):**
  5 = Every step is concrete and verified against the actual codebase from recon
  3 = Generally feasible but some assumptions may not hold
  1 = Contains assumptions contradicted by the recon documents

**Risk Identification (1-5):**
  5 = Risks identified with specific mitigations and fallback plans
  3 = Some risks noted but mitigations are vague
  1 = No risk acknowledgement

Your output MUST include:
- A score table: each draft scored on each dimension with a brief justification per score
- A comparative ranking: which draft is strongest overall and on which dimensions
- Strengths to preserve: the best ideas from each draft that the synthesizer should adopt
- Weaknesses to avoid: specific flaws from each draft that the synthesizer must not repeat
- Gap analysis: requirements or concerns not adequately addressed by ANY draft

- Write your evaluation to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/evaluation.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/evaluation.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After completion:** Confirm the file exists, then proceed to Stage 3. Do NOT read the file.

---

### Stage 3: Weighted Synthesis

YOU MUST launch 1 Task tool call. Use model "opus".

**The synthesizer receives pre-scored drafts so it can make informed trade-offs.**

**Prompt:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Synthesis agent. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- Read ALL of: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_1.md through /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/draft_plan_4.md (4 drafts).
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/evaluation.md (the rubric scores and comparative analysis).

Synthesize a master implementation plan using the evaluation to guide decisions:
  - For dimensions where one draft clearly leads in score: adopt that draft's approach for those aspects
  - Where all drafts agree: adopt directly as high-confidence decisions
  - Where drafts disagree: use evaluation scores + codebase recon to resolve, explain the choice
  - Incorporate every strength flagged by the evaluator
  - Avoid every weakness flagged by the evaluator
  - Address every gap identified in the gap analysis
  - The resulting plan must score 4+ on every rubric dimension

- Write the master plan to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After completion:** Confirm the file exists, then proceed to Stage 4. Do NOT read the file.

---

### Stage 4: Adversarial Red Team

YOU MUST launch 4 Task tool calls in a SINGLE message (parallel execution). Use model "opus".

**These are ADVERSARIAL agents. Their job is to BREAK the spec, not cooperate with it.**

**Red Team A — Requirements Auditor:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Requirements Auditor. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md — this is the plan you must audit.

YOUR MISSION: Systematically verify every requirement from the original issue.
For EACH requirement in /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md:
  - Is it addressed in the master plan? WHERE exactly (quote the relevant section)?
  - Is the acceptance criteria testable and specific?
  - Could a developer implement it differently than intended due to ambiguity?
  - What's missing?

Produce a REQUIREMENTS COVERAGE MATRIX as a table:
| Requirement | Addressed? | Location in Plan | Testable? | Gaps/Ambiguities |

- Write your audit to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_1.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_1.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Red Team B — Ambiguity Hunter:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Ambiguity Hunter. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md — this is the plan you must attack.

YOUR MISSION: Try to implement each section of this spec and find where you would get STUCK.
For each major section of the plan:
  - What information is missing that a developer would need?
  - What has multiple valid interpretations?
  - Where would two developers implement it differently?
  - What requires implicit knowledge not stated in the spec?
  - What order-of-operations dependencies are unstated?

Be adversarial. Assume the worst interpretation. Find every ambiguity.

- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_2.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_2.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Red Team C — Codebase Validator:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Codebase Validator. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md — this is the plan you must validate.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.

YOUR MISSION: Read the ACTUAL CODEBASE and verify every factual claim in the master plan.
Use Glob, Grep, and Read tools to check:
  - Do referenced files and directories actually exist?
  - Are function signatures and API contracts correct?
  - Do data models and schemas match what's described?
  - Are import paths and module references valid?
  - Does the plan correctly describe existing behavior it claims to modify?
  - Are there existing utilities or helpers the plan reinvents instead of reusing?

For every factual error, document: what the plan claims vs what the codebase actually shows.

- Write your validation report to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_3.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_3.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**Red Team D — Contradiction & Edge Case Finder:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Contradiction & Edge Case Finder. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md — this is the plan you must attack.

YOUR MISSION: Find internal contradictions, edge cases, and failure modes.
  - Find sections of the plan that CONTRADICT each other
  - Find ordering dependencies that would BREAK if steps are done out of order
  - Find edge cases NOT handled (empty inputs, concurrent access, partial failures, large data, etc.)
  - Find error paths NOT covered (network failures, auth failures, invalid data, timeouts)
  - Find assumptions that would FAIL in production (race conditions, resource limits, permissions)
  - Find security concerns (injection, auth bypass, data exposure, privilege escalation)

Be adversarial. Think like a chaos engineer. What breaks under stress?

- Write your findings to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_4.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_4.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After all 4 complete:** Confirm all 4 files exist, then proceed to Stage 5. Do NOT read the files.

---

### Stage 5: Final Spec with Traceability

YOU MUST launch 1 Task tool call. Use model "opus".

**Prompt:**

```
CRITICAL SUB-AGENT INSTRUCTIONS:
- You are the Final Spec agent. You are a SUB-AGENT, not the orchestrator.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/PROMPT.md for the full requirements.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/architecture.md, /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md, and /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/recon/conventions.md for codebase context.
- Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/master_plan.md (the master plan).
- Read ALL of: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_1.md through /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/red_team_4.md (4 red team reports).

Produce the FINAL, COMPLETE implementation specification. It MUST include:

1. **Requirements Traceability Matrix**: For each requirement from the original issue, the exact
   section of this spec that addresses it. Any requirement NOT addressed must be flagged as a gap
   with explicit justification for why it was deferred.

2. **Red Team Resolution Log**: For each finding from the 4 red team reports, document:
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

- Write the final spec to /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/SPEC.md
- Write in chunks of ~4000 tokens maximum. Use Write tool first, then Edit tool to append.
- Your final response must be ONLY: "Done. Output: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/SPEC.md"
- Do NOT return any content, summaries, or explanations. ONLY the done message.
```

**After completion:** Read /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/SPEC.md and present it to the user. This is the ONLY file you read.

---

### Orchestrator Context Management — CRITICAL

**Your context is precious. Sub-agents have their own 200k token contexts. You do NOT.**

- Your ONLY job is to launch Task agents and confirm they completed. That's it.
- You need ~1k tokens per stage. If your context grows beyond ~20k tokens, you broke a rule.
- NEVER read sub-agent output files yourself (the ONLY exception: /mnt/e/agentdev/projects/project-zeno/.specs/1-fix-light-basemap-tile-layer-failing-to-render-on/plans/SPEC.md at the very end)
- NEVER consume sub-agent return messages beyond confirming the word "Done"
- NEVER write plan content yourself — that's what the 13 sub-agents are for
- If a sub-agent fails, relaunch it. Do NOT do its work yourself as a fallback.


---

## Completion Protocol

When implementation is complete, the implementing agent must:

1. Create or update `DONE.md` in the spec directory.
2. Include the exact test commands run and their outcomes.
3. Summarize file changes and rationale in concise bullet points.
4. List any follow-up risks or deferred work.
