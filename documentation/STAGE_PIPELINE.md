# Stage Pipeline Documentation

This document provides detailed documentation for all stages in both parsing and interpretation pipelines.

## Overview

The pipeline consists of two sequential processes:

**Stage 1 (Parsing)**: 4 stages that extract structured data from natural language
**Stage 2 (Interpretation)**: 7 stages that transform structured JSON into YAML configuration

Each stage follows a consistent pattern:
1. Render prompt template with context
2. Execute LLM call
3. Parse and validate JSON response
4. Store results for downstream stages
5. Allow human feedback/retry

## Stage 1: Parsing Pipeline

Location: `parse_in_stages.py`

Input: Natural language game specification (text/markdown files)
Output: Structured JSON file

### Stage 1.1: META_ROLES_PHASES

**Purpose**: Extract core game structure including metadata, roles, phases, and payoff rules.

**Input Context**:
- Raw game specification text (full file contents)

**Expected LLM Output**:
```json
{
  "meta": {
    "game_name": "string",
    "game_description": "string",
    "game_version": "string",
    "author1": "string",
    "author2": "string",
    "creation_date": "string"
  },
  "roles": [
    {
      "id": "string",
      "name": "string",
      "llm": "string",
      "notes": "string",
      "phases": ["PhaseName1", "PhaseName2"]
    }
  ],
  "phases": [
    {
      "phase": "PhaseName",
      "phase_number": 1,
      "actionable": true,
      "role_tasks": {
        "RoleName1": ["task1", "task2"],
        "RoleName2": ["task1"]
      }
    }
  ],
  "payoff_consequences": [
    {
      "phase": "PhaseName",
      "role": "RoleName",
      "choice": "ChoiceDescription",
      "payoff": "PayoffDescription"
    }
  ]
}
```

**Validation Rules**:
- Must contain all four top-level keys
- `roles` must be a list (can be empty)
- `phases` must be a list (can be empty)
- `payoff_consequences` must be a list (can be empty)
- All role IDs should be unique (not enforced but recommended)

**Common Extraction Patterns**:
- Game name: Usually in title or first paragraph
- Roles: Look for "players", "agents", "participants" with distinct functions
- Phases: Sequential stages like "round", "turn", "decision phase"
- Actionable phases: Phases where agents make choices/decisions
- Payoffs: Described in terms of outcomes, rewards, scores, values

**Data Storage**:
Updates `GameSpec` object:
- `self.game_spec.meta = Meta(**meta)`
- `self.game_spec.roles = [Role(**r) for r in roles]`
- `self.game_spec.phases = [Phase(**p) for p in phases]`
- `self.game_spec.payoff_consequences = [PayoffConsequence(**pc) for pc in payoffs]`

**Prompt Template**: `prompts/parsing/meta_roles_phases_prompt.jinja2`

**Example**:
Input game spec mentions:
- "Prisoner's Dilemma between two players"
- "Each player chooses to cooperate or defect"
- "If both cooperate: 3 points each"

Extracted:
```json
{
  "meta": {"game_name": "Prisoner's Dilemma", ...},
  "roles": [
    {"id": "1", "name": "Prisoner", "phases": ["Decision Phase"]}
  ],
  "phases": [
    {"phase": "Decision Phase", "phase_number": 1, "actionable": true,
     "role_tasks": {"Prisoner": ["Choose to cooperate or defect"]}}
  ],
  "payoff_consequences": [
    {"phase": "Decision Phase", "role": "Prisoner", 
     "choice": "Both cooperate", "payoff": "3 points each"}
  ]
}
```

### Stage 1.2: STATE

**Purpose**: Identify state variables needed to track game progress and player information.

**Input Context**:
- ROLES (from Stage 1.1)
- PHASES (from Stage 1.1)
- PAYOFF CONSEQUENCES (from Stage 1.1)

**Expected LLM Output**:
```json
{
  "state": {
    "meta": [
      {
        "id": "variable_name",
        "type": "integer|string|boolean|array|dict",
        "description": "What this variable tracks",
        "default": <default_value>
      }
    ],
    "public": [
      {
        "id": "variable_name",
        "type": "data_type",
        "description": "Public information visible to all",
        "default": <default_value>
      }
    ],
    "private": [
      {
        "id": "variable_name",
        "role": "RoleName",
        "type": "data_type",
        "description": "Private to specific role",
        "default": <default_value>
      }
    ]
  }
}
```

**Validation Rules**:
- Must contain `state` key
- `state` must have `meta`, `public`, `private` arrays
- Each array can be empty
- Private state entries should include `role` field

**State Variable Categories**:

1. **Meta Information** (game-level state):
   - Round/turn numbers
   - Game phase identifiers
   - Total rounds
   - Practice/real round flags
   - Random seeds

2. **Public Information** (visible to all agents):
   - History logs
   - Aggregate statistics
   - Public announcements
   - Shared resources

3. **Private Information** (role-specific):
   - Individual scores
   - Private choices
   - Personal budgets
   - Hidden information

**Data Storage**:
- `self.game_spec.state = data["state"]`

**Prompt Template**: `prompts/parsing/state_prompt.jinja2`

**Example**:
For Prisoner's Dilemma:
```json
{
  "state": {
    "meta": [
      {"id": "round", "type": "integer", "description": "Current round number", "default": 1}
    ],
    "public": [
      {"id": "history", "type": "array", "description": "Past rounds history", "default": []}
    ],
    "private": [
      {"id": "score", "role": "Prisoner", "type": "integer", "description": "Total score", "default": 0},
      {"id": "last_choice", "role": "Prisoner", "type": "string", "description": "Previous choice", "default": ""}
    ]
  }
}
```

### Stage 1.3: SETTINGS_UI

**Purpose**: Extract experiment settings and user interface configuration.

**Input Context**:
- META (from Stage 1.1)
- ROLES (from Stage 1.1)
- PHASES (from Stage 1.1)
- STATE VARIABLES (from Stage 1.2)

**Expected LLM Output**:
```json
{
  "settings": {
    "random_seed": "integer or 'determined at runtime'",
    "max_rounds": 10
  },
  "ui": {
    "title": "Experiment Title",
    "instructions": "Full participant instructions text"
  }
}
```

**Validation Rules**:
- Must contain `settings` and `ui` keys
- `settings.max_rounds` should be present
- `ui.title` and `ui.instructions` should be strings

**Extraction Guidelines**:

1. **Settings**:
   - Random seed: If mentioned, extract value; otherwise "determined at runtime"
   - Max rounds: Total number of game rounds/iterations
   - Other parameters: Payment structure, time limits, etc.

2. **UI**:
   - Title: Short game name for display
   - Instructions: Complete participant instructions (can be very long)
   - Extract exactly as written (preserve formatting if possible)

**Data Storage**:
- `self.game_spec.settings = data["settings"]`
- `self.game_spec.ui = data["ui"]`

**Prompt Template**: `prompts/parsing/settings_ui_prompt.jinja2`

**Example**:
```json
{
  "settings": {
    "random_seed": "determined at runtime",
    "max_rounds": 10
  },
  "ui": {
    "title": "Prisoner's Dilemma Experiment",
    "instructions": "You will play 10 rounds. Each round, choose cooperate or defect. Your earnings depend on your choices and your opponent's choices. Cooperate-Cooperate: 3 points each. Defect-Cooperate: 5 for defector, 0 for cooperator..."
  }
}
```

### Stage 1.4: PARTIAL_PROMPTS

**Purpose**: Generate reusable prompt templates that will guide LLM agents during game play.

**Input Context**:
- ROLES (from Stage 1.1)
- PHASES (from Stage 1.1)
- PAYOFF CONSEQUENCES (from Stage 1.1)
- STATE VARIABLES (from Stage 1.2)
- SETTINGS (from Stage 1.3)
- SKELETON: Auto-generated list of expected partial names

**Expected LLM Output**:
```json
{
  "prompt_partials": [
    {"name": "game_description", "content": "..."},
    {"name": "game_information", "content": "..."},
    {"name": "game_history", "content": "..."},
    {"name": "system_<role>_<phase>", "content": "..."},
    {"name": "user_<role>_<phase>", "content": "..."}
  ]
}
```

**Validation Rules**:
- Must contain `prompt_partials` key
- Must be a list of objects
- Each object must have `name` and `content`
- All expected names from SKELETON must be present
- No duplicate names
- No unexpected names (strict matching)

**Required Partials**:

1. **game_description**: High-level game overview
   - Purpose and mechanics
   - Strategic considerations
   - No phase-specific details
   - Use bullet points for clarity

2. **game_information**: Dynamic context template
   - Must use Jinja2 variables: `{{ meta.phase }}`, `{{ meta.role }}`, etc.
   - Current phase, player number, role, name
   - No literal values (always template variables)

3. **game_history**: Historical recap template
   - Must use Jinja2 conditionals and loops
   - Reference public state variable for history (usually `history_log`)
   - Format: "{% raw %}{% if public_information.history_log %}...{% endif %}{% endraw %}"
   - Show previous rounds, choices, outcomes

4. **system_<role>_<phase>**: Role framing for specific phase
   - Naming: `system_developer_2` for Developer in phase 2
   - Content: Role identity, objectives, relevant payoff rules
   - Keep under 350 tokens
   - Don't specify output format (that's for user prompts)

5. **user_<role>_<phase>**: Concrete action instructions
   - Naming: `user_developer_2` for Developer in phase 2
   - Content: What to output, valid action tokens (UPPERCASE), format
   - Include game_information via: `{% include "_partials/game_information.jinja2" %}`
   - Include game_history if relevant
   - Reference state variables: `{{ private_information.score }}`
   - JSON schema if structured output required

**Generation Rules**:

- Role names converted to snake_case: "Land Owner" becomes "land_owner"
- Only generate system/user for actionable phases
- Only for roles with tasks in that phase
- Must match SKELETON exactly (no additions or omissions)

**Data Storage**:
- `self.game_spec.partial_prompts = data["prompt_partials"]`

**Prompt Template**: `prompts/parsing/partial_prompts_prompt.jinja2`

**Example Partial**:
```json
{
  "name": "user_prisoner_1",
  "content": "### Make Your Choice\n\nChoose one of the following actions:\n- COOPERATE\n- DEFECT\n\nOutput only the action token.\n\n#### Game Information\n{% include \"_partials/game_information.jinja2\" %}\n\n#### History\n{% include \"_partials/game_history.jinja2\" %}\n\n#### Your Score\nCurrent score: {{ private_information.score }}"
}
```

### Stage 1 Output

**Final JSON Structure**:
```json
{
  "meta": {...},
  "roles": [...],
  "phases": [...],
  "payoff_consequences": [...],
  "state": {...},
  "prompt_partials": [...],
  "settings": {...},
  "ui": {...}
}
```

**Output Location**: `output/parse_out/<filename>_<timestamp>.json`

## Stage 2: Interpretation Pipeline

Location: `interpret_in_stages.py`

Input: Parsed JSON from Stage 1
Output: YAML configuration file + prompt partial files

### Stage 2.1: META

**Purpose**: Extract experiment name, description, and prompt partials for YAML header.

**Input**: Full parsed JSON from Stage 1

**Expected LLM Output**:
```json
{
  "name": "Experiment Name" | "cannot infer",
  "description": "Description text" | "cannot infer",
  "prompt_partials": [
    {"name": "partial_name", "content": "content" | "cannot infer"}
  ]
}
```

**Validation Rules**:
- Exact keys: `name`, `description`, `prompt_partials`
- No additional keys allowed
- `prompt_partials` must be a list
- Each partial must have `name` and `content`

**Extraction Strategy**:
- Name: From `meta.game_name` or experiment title
- Description: From `meta.game_description` or `ui.title`
- Prompt partials: From `prompt_partials` array (direct copy usually)
- Use "cannot infer" if field not present in JSON

**Data Usage**:
Populates ExperimentConfig:
```python
cfg = ExperimentConfig(
    name=name,
    description=desc,
    prompt_partials=[PromptPartial(name=..., content=...) for ...]
)
```

**Prompt Template**: `prompts/interpret/meta_prompt.jinja2`

### Stage 2.2: ROLES

**Purpose**: Define agent roles with their LLM configuration, prompts, and active phases.

**Input**: Full parsed JSON (primarily `roles` and `phases`)

**Expected LLM Output**:
```json
{
  "agent_roles": [
    {
      "role_id": 1,
      "name": "RoleName",
      "llm_type": "ChatOpenAI" | "cannot infer",
      "llm_params": {} | "cannot infer",
      "prompts": [
        {"key": "system", "content": "..." | "cannot infer"},
        {"key": "user", "content": "..." | "cannot infer"}
      ],
      "task_phases": [1, 2, 3],
      "task_phases_excluded": []
    }
  ]
}
```

**Validation Rules**:
- Exact keys: `agent_roles`
- Each role must have: `role_id`, `name`, `llm_type`, `llm_params`, `prompts`, `task_phases`, `task_phases_excluded`
- `prompts` must be a list
- Each prompt must have `key` and `content`
- Prompt keys must be unique within a role
- Must include at least `system` prompt key

**Field Definitions**:

- **role_id**: Integer from parsed roles
- **name**: Role name (e.g., "Prisoner", "Developer")
- **llm_type**: LLM class name (default: "ChatOpenAI")
- **llm_params**: JSON object with LLM config (temperature, model, etc.)
- **prompts**: List of prompt entries
  - **key**: "system", "user", "system_phase_2", "user_phase_3", etc.
  - **content**: Prompt text or template
- **task_phases**: List of phase numbers where role is active
- **task_phases_excluded**: Phases to explicitly exclude

**Prompt Key Conventions**:
- `system`: Base system prompt (always present)
- `user`: Base user prompt (optional)
- `system_phase_N`: System prompt override for phase N
- `user_phase_N`: User prompt override for phase N

**Data Usage**:
```python
for r in agent_roles:
    prompts = [RolePromptEntry(key=pe["key"], content=pe["content"]) for pe in r["prompts"]]
    cfg.agent_roles.append(AgentRoleConfig(..., prompts=prompts, ...))
```

**Prompt Template**: `prompts/interpret/roles_prompt.jinja2`

### Stage 2.3: STATE

**Purpose**: Map state variables from parsed JSON to YAML state schema.

**Input**: Full parsed JSON (primarily `state`)

**Expected LLM Output**:
```json
{
  "state": {
    "meta_information": [
      {
        "name": "variable_name",
        "type": "int|str|bool|list|dict",
        "default": value | "cannot infer",
        "default_factory": "list|dict" | "cannot infer",
        "event_key": "event_name" | "cannot infer",
        "exclude_from_mapping": false,
        "optional": false,
        "events": ["event1"] | [],
        "exclude_events": [] | "cannot infer"
      }
    ],
    "private_information": [...],
    "public_information": [...]
  }
}
```

**Validation Rules**:
- Exact key: `state`
- `state` must contain: `meta_information`, `private_information`, `public_information`
- Each section must be a list (can be empty)

**Field Definitions**:

- **name**: Variable identifier (snake_case)
- **type**: Python type as string
- **default**: Default value (use None for "cannot infer")
- **default_factory**: Factory function name for mutable defaults
- **event_key**: Event that updates this variable
- **exclude_from_mapping**: Don't auto-map from events
- **optional**: Can be None
- **events**: List of events that affect this variable
- **exclude_events**: Events to ignore

**Type Mappings**:
- "integer" -> "int"
- "string" -> "str"
- "boolean" -> "bool"
- "array" -> "list"
- "dict" -> "dict"

**Data Usage**:
```python
cfg.state = StateConfig(
    meta_information=[make_state_field_from_json(f) for f in meta_info],
    private_information=[make_state_field_from_json(f) for f in private_info],
    public_information=[make_state_field_from_json(f) for f in public_info]
)
```

**Prompt Template**: `prompts/interpret/state_prompt.jinja2`

### Stage 2.4: MANAGER

**Purpose**: Configure game manager type and event handlers.

**Input**: Full parsed JSON

**Expected LLM Output**:
```json
{
  "manager": {
    "type": "TurnBasedPhaseManager" | "cannot infer",
    "event_handlers": [
      {
        "event": "event-name",
        "custom_code": "python code" | "cannot infer",
        "custom_module": "module.path" | "cannot infer",
        "custom_function": "function_name" | "cannot infer"
      }
    ]
  }
}
```

**Validation Rules**:
- Exact key: `manager`
- Can contain `type` and/or `event_handlers`
- `event_handlers` must be a list if present

**Field Definitions**:

- **type**: Manager class name (default: "TurnBasedPhaseManager")
- **event_handlers**: List of event-driven behaviors
  - **event**: Event name to handle
  - **custom_code**: Inline Python code
  - **custom_module**: Module to import
  - **custom_function**: Function to call

**Common Manager Types**:
- "TurnBasedPhaseManager": Sequential turn-based games
- "SimultaneousActionManager": All agents act simultaneously
- "Custom managers": User-defined classes

**Data Usage**:
```python
cfg.manager = ManagerConfig(
    type=manager_type or "TurnBasedPhaseManager",
    event_handlers=[EventHandler(**eh) for eh in handlers]
)
```

**Prompt Template**: `prompts/interpret/manager_prompt.jinja2`

### Stage 2.5: RUNNER

**Purpose**: Configure game runner and server parameters.

**Input**: Full parsed JSON (settings, meta)

**Expected LLM Output**:
```json
{
  "runner": {
    "type": "GameRunner" | "cannot infer",
    "protocol": "ws" | "cannot infer",
    "hostname": "localhost" | "cannot infer",
    "path": "wss" | "cannot infer",
    "port": 8080 | 0,
    "game_id": 1 | 0,
    "logs_dir": "logs" | "cannot infer",
    "log_level": "INFO" | "cannot infer",
    "prompts_dir": "prompts" | "cannot infer",
    "phase_transition_event": "phase-transition" | "cannot infer",
    "phase_identifier_key": "phase" | "cannot infer",
    "observability_provider": "langsmith" | "cannot infer",
    "continuous_phases": [1, 2] | [],
    "min_action_delay": 5 | 0,
    "max_action_delay": 10 | 0
  }
}
```

**Validation Rules**:
- Exact key: `runner`
- All fields optional (have defaults)

**Field Definitions**:

- **type**: Runner class ("GameRunner", "HybridGameRunner")
- **protocol**: Communication protocol ("ws" for WebSocket)
- **hostname**: Server hostname
- **path**: WebSocket path
- **port**: Server port number
- **game_id**: Unique game identifier
- **logs_dir**: Log file directory
- **log_level**: "DEBUG", "INFO", "WARNING", "ERROR"
- **prompts_dir**: Directory containing prompt templates
- **phase_transition_event**: Event name for phase changes
- **phase_identifier_key**: Key in event data identifying phase
- **observability_provider**: "langsmith", "langfuse", or null
- **continuous_phases**: Phases that run continuously (for HybridGameRunner)
- **min_action_delay**: Minimum delay between actions (seconds)
- **max_action_delay**: Maximum delay between actions (seconds)

**Data Usage**:
```python
cfg.runner = RunnerConfig(
    type=runner_type or "GameRunner",
    protocol=protocol or "ws",
    # ... all fields with defaults ...
)
```

**Prompt Template**: `prompts/interpret/runner_prompt.jinja2`

### Stage 2.6: AGENTS

**Purpose**: Map individual agent instances to roles.

**Input**: Full parsed JSON (roles)

**Expected LLM Output**:
```json
{
  "agents": [
    {
      "id": 1,
      "role_id": 1
    },
    {
      "id": 2,
      "role_id": 1
    }
  ]
}
```

**Validation Rules**:
- Exact key: `agents`
- Must be a list
- Each agent must have `id` and `role_id`

**Field Definitions**:

- **id**: Unique agent identifier
- **role_id**: Reference to role from ROLES stage

**Mapping Strategy**:
- One agent per role instance
- Multiple agents can share same role
- Agent IDs must be unique across experiment

**Data Usage**:
```python
cfg.agents = [
    AgentMappingConfig(id=a["id"], role_id=a["role_id"])
    for a in agents_data
]
```

**Prompt Template**: `prompts/interpret/agents_prompt.jinja2`

### Stage 2.7: ROLE_PROMPTS_REFINEMENT

**Purpose**: Final validation and refinement of role prompts.

**Input**: Results from ROLES stage

**Expected LLM Output**:
```json
{
  "agent_roles_update": [
    {
      "role_id": 1,
      "prompts": [
        {"key": "system", "content": "refined content"},
        {"key": "user", "content": "refined content"}
      ]
    }
  ]
}
```

**Validation Rules**:
- Exact key: `agent_roles_update`
- Must be a list
- Each update must have `role_id` and `prompts` list

**Purpose**:
- Final opportunity to refine prompts
- Ensure consistency across all prompts
- Validate prompt references to state variables
- Check Jinja2 syntax

**Data Usage**:
If updates provided, replace role prompts:
```python
if role.role_id in updates:
    role.prompts = [RolePromptEntry(**pe) for pe in updates[role.role_id]]
```

**Prompt Template**: `prompts/interpret/role_prompts_prompt.jinja2`

### Stage 2 Output

**Final YAML File**: `output/experiment_yaml/<name>.yaml`

Structure matches `econagents_template.yaml.jinja2`:
```yaml
name: "Experiment Name"
description: "Description"
prompt_partials: [...]
agent_roles: [...]
agents: [...]
state:
  meta_information: [...]
  private_information: [...]
  public_information: [...]
manager:
  type: "TurnBasedPhaseManager"
  event_handlers: [...]
runner:
  type: "GameRunner"
  protocol: "ws"
  # ... all runner config ...
```

**Prompt Partial Files**: `prompts/_partials/<name>.jinja2`

One file per prompt partial extracted in META stage.

## Common Patterns Across Stages

### Retry Logic

All stages support retry with feedback:

1. **Auto-retry**: Stage 2 auto-retries on validation failure (up to `max_auto_retries`)
2. **Human feedback**: User can provide feedback to guide retry
3. **Retry prompt composition**:
   - Standard prompt for stage
   - Previous LLM response
   - Validation error message
   - Human feedback (if provided)

### Context Composition

Later stages include context from earlier stages:

**Stage 1**:
- STATE uses: ROLES, PHASES, PAYOFF_CONSEQUENCES
- SETTINGS_UI uses: META, ROLES, PHASES, STATE
- PARTIAL_PROMPTS uses: All previous stages + SKELETON

**Stage 2**:
- All stages receive full parsed JSON
- No cumulative context (each reads from JSON independently)

### Validation Patterns

**Stage 1 (Permissive)**:
- Check required fields exist
- Verify data types
- Allow flexible content

**Stage 2 (Strict)**:
- Exact key matching
- Strict type enforcement
- Relationship validation
- Schema conformance

### Error Handling

**JSON Parse Errors**:
```
Invalid JSON: <error message>
Raw response: <LLM output>
```

**Validation Errors**:
```
<STAGE>: <specific error message>
```

**Recovery**:
- Display error to user
- Offer retry with feedback
- Option to skip stage (Stage 2 only)
- Continue with partial data (marked incomplete)

## Performance Characteristics

### Latency Per Stage

Approximate times (varies by LLM model):

**Stage 1**:
- META_ROLES_PHASES: 10-20 seconds
- STATE: 5-10 seconds
- SETTINGS_UI: 5-10 seconds
- PARTIAL_PROMPTS: 15-30 seconds (most complex)

**Stage 2**:
- META: 3-5 seconds
- ROLES: 5-10 seconds
- STATE: 3-5 seconds
- MANAGER: 3-5 seconds
- RUNNER: 3-5 seconds
- AGENTS: 2-3 seconds
- ROLE_PROMPTS_REFINEMENT: 5-10 seconds

Total pipeline: 1-3 minutes depending on game complexity and retry count.

### Token Usage

**Stage 1**:
- Input: Full game spec (500-5000 tokens per stage)
- Output: JSON (200-2000 tokens per stage)

**Stage 2**:
- Input: Parsed JSON + schema (300-1500 tokens per stage)
- Output: JSON (100-800 tokens per stage)

Total tokens: 5K-20K per complete pipeline run.

## Best Practices

### For Prompt Engineering

1. Keep schemas minimal (required fields only)
2. Provide clear examples in prompts
3. Use strict JSON-only formatting instructions
4. Include edge case handling in prompts

### For Validation

1. Validate early and fail fast
2. Provide specific error messages
3. Include example of correct format in error
4. Test with diverse game specs

### For Context Composition

1. Only include necessary context
2. Summarize instead of full dumps when possible
3. Order context logically (chronological or hierarchical)
4. Label context sections clearly

### For Debugging

1. Print prompts before LLM calls
2. Save raw LLM responses
3. Log validation failures with full context
4. Test stages independently with mock data
