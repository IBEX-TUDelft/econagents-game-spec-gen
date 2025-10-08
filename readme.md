# EconAgents Game Spec Generation Pipeline

Transform natural language economic game descriptions into validated EconAgents YAML configurations in two LLM‑assisted stages: (1) parsing raw human text into a structured intermediate JSON and (2) interpreting that JSON into a strict YAML file matching `templates/econagents_template.yaml.jinja2`.

---
## High-Level Architecture
```
 Raw Game Specification (Markdown / plain text)
                │
                V
      parse_in_stages.py (LLM stages: meta+roles+phases → state →  prompt_partials)
                │  (Validated, feedback-capable JSON extraction)
                V
     Intermediate Structured JSON (output/parse_out/*.json)
                │
                V
  interpret_in_stages.py (LLM stages: meta → roles → state → manager → runner → agents → prompt refinement)
                │  (Strict schemas, unknown sentinel handling, file generation)
                V
      Final YAML file (output/experiment_yaml/*.yaml)
```

Two separable loops:
- **Parsing Loop**: Understand the natural language description.
- **Interpretation Loop**: Convert condensed JSON into the final executable YAML configuration.

---
## Repository Layout (Key Paths)
| Path | Purpose |
|------|---------|
| `game_spec/` | Source human-readable specs (input to Stage 1). |
| `parse_in_stages.py` | First pipeline: text → structured JSON. |
| `prompts/parsing/` | Jinja2 prompt templates for parsing stages. |
| `output/parse_out/` | Generated intermediate JSON specs. |
| `interpret_in_stages.py` | Second pipeline: JSON → final YAML. |
| `prompts/interpret/` | Prompt templates for interpretation stages (strict schemas). |
| `yaml_dataclasses.py` | Python dataclasses mirroring YAML schema. |
| `templates/econagents_template.yaml.jinja2` | Immutable final YAML template. |
| `prompts/_partials/` | Auto-written partial prompt include files (Stage 2). |
| `valid_yaml_examples/` | Reference manually created valid YAMLs (targets). |

---
## Data Flow Overview
1. **Human spec**: multi‑paragraph description (roles, phases, payoffs, state variables, instructions).
2. **Stage 1 (Parsing)** produces structured JSON containing:
   - `meta`, `roles`, `phases`, `payoff_consequences`, `state`, `settings`, `prompt_partials`.
3. **Stage 2 (Interpretation)** ingests that JSON and emits:
   - A strict YAML with: name, description, prompt_partials, agent_roles, agents, state (meta/private/public), manager, runner.
4. **Unknown information** surfaced as `(UPDATE MANUALLY)` for explicit human completion.

---
## Stage 1: Text → Structured JSON (`parse_in_stages.py`)
Stages (fixed order):
1. `meta_roles_phases` – Extracts metadata, list of roles (with notes / tasks), phases (actionability & role tasks), payoff consequences.
2. `state` – Candidate state variables & classifications.
3. `partial_prompts` – Skeleton of prompt partial names & placeholders.

Features:
- **Threaded LLM call** with progress spinner and color output.
- **Strict JSON validation** per stage; errors trigger auto or feedback retries.
- **Human feedback injection** after each successful parse (optional interactive refinement).
- Writes final JSON snapshot to `output/parse_out/<spec_name>_YYYYmmdd_HHMMSS.json`.

---
## 6. Stage 2: JSON → YAML (`interpret_in_stages.py`)
Stages (default sequence):
1. `meta`  
2. `roles`  
3. `state`  
4. `manager`  
5. `runner`  
6. `agents`  
7. `role_prompts_refinement`

Each stage:
- Renders a **strict schema prompt** (see `prompts/interpret/`).
- Enforces: “Extract ONLY from supplied JSON; use `cannot infer` when absent.”
- Validates shape & uniqueness constraints (e.g., no duplicate prompt keys, mandatory system prompt). 
- Auto‑retries on schema failures (configurable) and then offers manual feedback injection.

Outputs:
- YAML file in `output/experiment_yaml/`.
- `(UPDATE MANUALLY)` markers for unknown scalars.

---
## YAML Template Contract (Immutable)
`templates/econagents_template.yaml.jinja2` is **not to be altered**. All generation logic must conform to its structure:
```
name: "..."
description: "..."
prompt_partials: [...]
agent_roles: [...]
agents: [...]
state: { meta_information, private_information, public_information }
manager: { type, event_handlers }
runner: { type, protocol, hostname, ... }
```
Prompts inside each role are rendered as a list of single‑key mappings; this matches downstream server expectations.

---
## Dataclasses Mapping (`yaml_dataclasses.py`)
Core classes: `ExperimentConfig`, `PromptPartial`, `AgentRoleConfig`, `RolePromptEntry`, `StateFieldConfig`, `ManagerConfig`, `RunnerConfig`.

`ExperimentConfig.to_template_context()` transforms internal Python objects into the dictionary consumed by the Jinja2 template, also normalizing `RolePromptEntry.content` → `value` for the template’s `prompt.value` access pattern.

---
## Prompt Templates & Schemas
Two families:
- Parsing prompts: `prompts/parsing/*.jinja2` – loosely structured extraction.
- Interpretation prompts: `prompts/interpret/*.jinja2` – **strict JSON schemas**; all contain the header enforcing non‑inference policy.

You can modify or add interpretation stages by:
1. Creating a new Jinja2 prompt file with a strict return schema.
2. Adding a `Stage` enum entry (if new) and wiring it into the stage list in the relevant driver script.
3. Extending validation logic accordingly.

---
## Handling Unknown / Missing Fields
Policy: *Never hallucinate.* Instead:
- LLM returns `"cannot infer"` (string) or `[]` (empty list) for unknown fields.
- During interpretation merge, `"cannot infer"` → `None` (Python) for scalars.
- Prior to YAML render, any `None` scalar is converted to `(UPDATE MANUALLY)` for clarity.
- Empty lists are sometimes given a placeholder element (in Stage 2 rendering) so the YAML shows an explicit location to edit rather than an invisible omission.

---
## Running the Pipeline (Quick Start)
### Prerequisites
- Python 3.11+ recommended (uses modern typing and dataclasses).
- OpenAI (or compatible) API key exported as `OPENAI_API_KEY` (the custom wrapper expects it).

### Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...   # set your key (fish/zsh adapt accordingly) or create a .env file
```

### (A) Parse a Human Spec to JSON
Game spec source files live in `game_spec/`. Add or edit one (Markdown / text). Then:
```bash
python parse_in_stages.py
# Follow interactive menu to choose a spec.
# Accept or provide feedback per stage until JSON is written to output/parse_out/
```
Result: `output/parse_out/<your_spec>_TIMESTAMP.json`.

### (B) Interpret JSON to Final YAML
```bash
python interpret_in_stages.py
# Select the generated JSON file.
# Review each strict schema stage; accept or retry with feedback.
```
Result: 
- YAML: `output/experiment_yaml/<your_spec>.yaml`
- Prompt partial includes: `prompts/_partials/*.jinja2`

### (C) Manual Completion
Search for `(UPDATE MANUALLY)` in the YAML and partials to finalize missing pieces.

### (D) (Optional) Use YAML in EconAgents
(Outside this repo) point the EconAgents runner to the produced YAML.

---
## Advanced Usage & Feedback Loop
- **Auto‑Retry**: Each interpretation stage auto‑retries a configurable number of times (default 2) on JSON validation failure.
- **Human Feedback**: After an error or accepted result you can inject targeted feedback; the retry prompt includes: previous response, error message, and your notes.
- **Color Codes**: Blue (stage header), Green (success), Red (error), Yellow (warnings / skip), Gray (prompt preview).

(End of README)
