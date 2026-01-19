# Architecture Documentation

## System Overview

The EconAgents Game Spec Generation Pipeline is a two-stage LLM-assisted system that transforms natural language economic game specifications into validated YAML configurations compatible with the EconAgents framework.

## High-Level Data Flow

```
Stage 1: Parsing Pipeline
--------------------------
Input: Natural language game specification (Markdown/text files in game_spec/)
  |
  v
parse_in_stages.py executes 4 stages sequentially:
  1. META_ROLES_PHASES - Extract metadata, roles, phases, payoffs
  2. STATE - Identify state variables (meta/public/private)
  3. SETTINGS_UI - Extract settings and UI configuration
  4. PARTIAL_PROMPTS - Generate reusable prompt templates
  |
  v
Output: Structured JSON (output/parse_out/*.json)


Stage 2: Interpretation Pipeline
---------------------------------
Input: Structured JSON from Stage 1
  |
  v
interpret_in_stages.py executes 7 stages sequentially:
  1. META - Extract experiment name, description, prompt partials
  2. ROLES - Define agent roles and their configurations
  3. STATE - Map state variables to YAML schema
  4. MANAGER - Configure game manager and event handlers
  5. RUNNER - Configure game runner parameters
  6. AGENTS - Map individual agents to roles
  7. ROLE_PROMPTS_REFINEMENT - Refine and validate role prompts
  |
  v
Output: Final YAML configuration (output/experiment_yaml/*.yaml)
         Prompt partial files (prompts/_partials/*.jinja2)
```

## Core Components

### 1. Parsing Pipeline (parse_in_stages.py)

**Purpose**: Convert unstructured natural language game descriptions into structured JSON.

**Key Classes**:
- `StagedGameSpecParser`: Main orchestrator for parsing stages
- `GameSpec`: Container for parsed game specification
- `Meta`, `Role`, `Phase`, `PayoffConsequence`: Data holders for parsed components
- `Stage` (Enum): Defines parsing stages
- `ParserState` (Enum): Tracks parser execution state

**Threading Model**:
- Main thread handles user interaction and state coordination
- Worker thread runs async LLM calls via asyncio event loop
- Thread-safe state transitions using threading.Lock

**Stage Execution Flow**:
1. User selects game specification file
2. For each stage:
   - Render prompt template with context from previous stages
   - Execute LLM call in background thread
   - Parse and validate JSON response
   - Update GameSpec with parsed data
   - Allow human feedback and retry if needed
3. Write final JSON to disk

### 2. Interpretation Pipeline (interpret_in_stages.py)

**Purpose**: Convert structured JSON into strict YAML configurations with schema validation.

**Key Classes**:
- `StagedYamlInterpreter`: Main orchestrator for interpretation stages
- `ExperimentConfig`: Target data structure matching YAML template
- `Stage` (Enum): Defines interpretation stages
- `RunnerState` (Enum): Tracks interpreter execution state

**Threading Model**:
- Identical to parsing pipeline (main thread + async worker thread)
- Thread-safe state management

**Unknown Value Handling**:
- LLM returns "cannot infer" for fields with insufficient evidence
- Coercion layer converts "cannot infer" to None in Python objects
- YAML rendering replaces None with "(UPDATE MANUALLY)" markers
- Empty lists get placeholder elements to show structure

**Stage Execution Flow**:
1. User selects parsed JSON file
2. For each stage:
   - Render strict schema prompt
   - Execute LLM call with validation
   - Auto-retry on schema failures (configurable limit)
   - Merge validated data into ExperimentConfig
3. Render final YAML via Jinja2 template
4. Write YAML and prompt partials to disk

### 3. Data Models (yaml_dataclasses.py)

**Purpose**: Python dataclasses mirroring the YAML configuration schema.

**Key Classes**:
- `ExperimentConfig`: Root configuration object
- `PromptPartial`: Reusable prompt snippets
- `AgentRoleConfig`: Role definition with prompts and phases
- `RolePromptEntry`: Individual prompt (system/user) for a role
- `StateFieldConfig`: State variable specification
- `StateConfig`: Container for meta/private/public state
- `ManagerConfig`: Game manager configuration
- `RunnerConfig`: Game runner parameters
- `EventHandler`: Event-driven code hooks

**Design Pattern**:
- Immutable dataclasses with default factories
- `to_template_context()` method converts to Jinja2-compatible dict
- Explicit field mapping (e.g., RolePromptEntry.content maps to "value" in template)

### 4. Template Rendering (templates/)

**Purpose**: Jinja2 templates that define final YAML structure.

**Key File**: `econagents_template.yaml.jinja2`
- Immutable contract between pipeline and EconAgents runtime
- All generation logic must conform to this structure
- Uses Jinja2 loops, conditionals, filters for dynamic rendering

**Template Features**:
- Multi-line string literals with proper indentation
- Default value handling for optional fields
- List iteration for roles, agents, state fields, event handlers
- Conditional rendering based on field presence

### 5. Prompt Engineering (prompts/)

**Two Prompt Categories**:

**A. Parsing Prompts (prompts/parsing/)**:
- Loosely structured extraction from natural language
- Encourage comprehensive extraction
- Allow LLM flexibility in interpretation
- Provide JSON schemas as guidance

**B. Interpretation Prompts (prompts/interpret/)**:
- Strict JSON schema enforcement
- "Extract ONLY from provided JSON" policy
- "cannot infer" fallback for missing data
- Minimal schema with required fields only

**Prompt Template Pattern**:
```
{{ header }} - Injected system instructions
{{ parsed_json }} - Context from previous stages
Schema definition - Expected JSON structure
```

## State Management

### Parser State Machine (ParserState)

```
IDLE
  |
  v
SELECTING_GAME (user selects file)
  |
  v
WAITING_RESPONSE (LLM call in progress)
  |
  v
PROCESSING_RESPONSE (validating JSON)
  |
  +---> ERROR (validation failed) --> retry or next
  |
  +---> SUCCESS (stage complete) --> next stage or write file
  |
  v
WRITING_FILE (final JSON output)
```

### Interpreter State Machine (RunnerState)

```
IDLE
  |
  v
WAITING_RESPONSE (LLM call in progress)
  |
  v
PROCESSING_RESPONSE (validating JSON)
  |
  +---> ERROR (schema violation) --> auto-retry or human feedback
  |
  +---> SUCCESS (stage complete) --> next stage
  |
  v
WRITING_FILE (YAML and partials output)
```

## Concurrency Model

### Async Event Loop Handling

Both pipelines use a careful pattern to avoid event loop issues:

1. **Main Thread**: Handles user I/O and state coordination
2. **Worker Thread**: Creates new asyncio event loop for LLM calls
3. **Event Loop Lifecycle**:
   - Create new loop per stage execution
   - Set custom exception handler to suppress "Event loop closed" warnings
   - Run LLM async coroutine to completion
   - Shutdown async generators
   - Close loop in finally block

**Rationale**: Python's asyncio and threading interaction requires isolated event loops to prevent resource leaks and "event loop already running" errors.

### Thread Safety

- All state mutations protected by `threading.Lock`
- Lock acquisition pattern: `with self.lock:`
- Lock scope: Minimal (only around state reads/writes)

## Validation Strategy

### Stage 1 (Parsing) Validation

**Per-Stage Validators**:
- META_ROLES_PHASES: Verify presence of meta, roles, phases, payoff_consequences
- STATE: Verify state object with meta/public/private arrays
- SETTINGS_UI: Verify settings and ui objects
- PARTIAL_PROMPTS: 
  - Verify prompt_partials is a list
  - Check all expected partial names are present
  - Detect duplicates and unexpected names
  - Validate name/content fields in each partial

### Stage 2 (Interpretation) Validation

**Strict Schema Validation**:
- Exact key matching (reject extra or missing keys)
- Type checking (lists must be lists, etc.)
- Relationship validation (e.g., agent role_id must reference existing role)
- Prompt key uniqueness (no duplicate system/user prompts)
- Required field enforcement

**Validation Failure Handling**:
- Auto-retry up to configurable limit (default: 2)
- Include previous response and error in retry prompt
- Allow human feedback injection
- Option to skip stage with warning

## Error Handling Philosophy

### Non-Inference Policy

**Core Principle**: Never hallucinate data not present in source material.

**Implementation**:
- LLM instructed to return "cannot infer" for uncertain fields
- Empty lists preferred over fabricated data
- Explicit markers in final YAML guide manual completion

### Graceful Degradation

- Schema violations don't crash the pipeline
- User can skip stages with warnings
- Partial outputs marked with "(UPDATE MANUALLY)"
- Final YAML always produces valid syntax (even if semantically incomplete)

## File Organization

### Input Files
- `game_spec/` - Natural language game specifications
- `.env` - Environment variables (OPENAI_API_KEY)

### Intermediate Files
- `output/parse_out/*.json` - Stage 1 outputs (timestamped)

### Output Files
- `output/experiment_yaml/*.yaml` - Final configurations
- `prompts/_partials/*.jinja2` - Extracted prompt partials (written by Stage 2)

### Configuration Files
- `prompts/parsing/*.jinja2` - Stage 1 prompt templates
- `prompts/interpret/*.jinja2` - Stage 2 prompt templates
- `templates/econagents_template.yaml.jinja2` - Final YAML template

### Code Organization
- `parse_in_stages.py` - Stage 1 pipeline
- `interpret_in_stages.py` - Stage 2 pipeline
- `yaml_dataclasses.py` - YAML data model
- `gamedataclasses.py` - Parsing data model
- `requirements.txt` - Python dependencies

## Extension Points

### Adding a New Parsing Stage

1. Add enum value to `Stage` in parse_in_stages.py
2. Create prompt template in `prompts/parsing/`
3. Add prompt filename mapping in `_get_prompt_template()`
4. Implement validator in `_validate_stage()`
5. Implement data merger in `_update_game_spec()`
6. Add context composition logic in `_compose_context_for_stage()`

### Adding a New Interpretation Stage

1. Add enum value to `Stage` in interpret_in_stages.py
2. Create prompt template in `prompts/interpret/`
3. Add prompt filename mapping in `_get_prompt_template()`
4. Implement validator in `_validate_stage()`
5. Add dataclass handling in `_merge_into_config()`
6. Update `to_template_context()` in yaml_dataclasses.py if needed

### Modifying the YAML Schema

**Critical Constraint**: `econagents_template.yaml.jinja2` is the source of truth.

1. Modify template first
2. Update corresponding dataclasses in yaml_dataclasses.py
3. Update interpretation stage prompts to extract new fields
4. Update validation logic to enforce new schema
5. Test end-to-end with existing game specs

## Dependencies

### External Libraries
- `econagents.llm.openai.ChatOpenAI` - LLM wrapper (custom library)
- `jinja2` - Template rendering
- `python-dotenv` - Environment variable loading
- `asyncio` - Async LLM execution
- `threading` - Concurrent execution
- `json` - Data serialization
- `os`, `time`, `datetime` - Standard utilities

### Dependency Injection
- LLM client injected via environment variable (OPENAI_API_KEY)
- File paths configurable via constructor parameters
- Templates loaded from filesystem at runtime

## Performance Considerations

### LLM Call Optimization
- Each stage makes exactly one LLM call (plus retries)
- Prompts include all necessary context to avoid multi-turn conversations
- Context composition reuses previous stage results (no re-parsing)

### Memory Management
- JSON objects held in memory during pipeline execution
- Large game specs may require pagination (not currently implemented)
- Event loop cleanup prevents memory leaks

### Disk I/O
- Minimal disk reads (one per template, one per game spec)
- Outputs written once per successful pipeline completion
- No intermediate file caching

## Testing Strategy

### Current State
- Manual testing via interactive CLI
- No automated test suite

### Recommended Testing Approach
1. Unit tests for validators (`_validate_stage()`)
2. Integration tests for stage execution (mock LLM responses)
3. End-to-end tests with fixed game specs
4. Schema conformance tests (validate YAML against EconAgents runtime)
5. Regression tests with known good outputs

## Security Considerations

### API Key Handling
- Never log or print API keys
- Load from environment variables only
- No hardcoded credentials

### LLM Input Sanitization
- Game specs may contain untrusted user content
- No code execution from game spec content
- Template rendering is sandboxed (Jinja2 default safety)

### Output Validation
- YAML syntax validated before writing
- No arbitrary file writes (fixed output directories)
- Timestamped filenames prevent overwrites

## Future Architecture Considerations

### Planned Stage 3: Schema-Driven Prompt Generation

**Proposed Architecture**:
```
Stage 2 Output (YAML + placeholders)
  |
  v
Stage 3: schema_driven_prompts.py
  - Input: JSON schema files defining agent output formats
  - Input: YAML with placeholder prompts
  - Process: LLM generates prompts that enforce schema compliance
  - Validation: Test prompts with sample inputs
  |
  v
Final YAML (no placeholders, schema-enforced prompts)
```

**Key Design Questions**:
1. Schema format (JSON Schema, Pydantic, custom DSL)?
2. Prompt generation vs. prompt modification?
3. How to validate generated prompts enforce schemas?
4. Integration point (new binary or extend interpret_in_stages.py)?

See FUTURE_ROADMAP.md for detailed plans.
