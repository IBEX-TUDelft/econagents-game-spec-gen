# Data Models Documentation

This document provides comprehensive documentation of all data structures used in the pipeline.

## Overview

The pipeline uses three categories of data models:

1. **Parsing Models** (gamedataclasses.py): Intermediate structures for Stage 1
2. **YAML Configuration Models** (yaml_dataclasses.py): Final output structures for Stage 2
3. **Runtime Models**: JSON dictionaries passed between stages

## Parsing Models (gamedataclasses.py)

These models are used internally by Stage 1 to store parsed game specifications.

### PhaseRoleTasks

**Purpose**: Represents tasks assigned to each role within a specific game phase.

**Definition**:
```python
@dataclass
class PhaseRoleTasks:
    phase: str
    phase_number: int
    actionable: bool
    role_tasks: Dict[str, List[str]] = field(default_factory=dict)
```

**Fields**:
- `phase`: Phase name (e.g., "Decision Making", "Round Initiation")
- `phase_number`: Integer identifying phase order (1-indexed)
- `actionable`: Boolean indicating if agents make decisions in this phase
- `role_tasks`: Dictionary mapping role names to lists of task descriptions

**Usage**: Internal representation during parsing, not directly output to JSON.

**Example**:
```python
PhaseRoleTasks(
    phase="Decision Phase",
    phase_number=1,
    actionable=True,
    role_tasks={
        "Prisoner": ["Choose to cooperate or defect"],
        "Guard": ["Observe prisoner choices"]
    }
)
```

### PayoffConsequence

**Purpose**: Describes the payoff outcome for a specific role's choice in a phase.

**Definition**:
```python
@dataclass
class PayoffConsequence:
    phase: str
    role: str
    choice: str
    payoff: str
```

**Fields**:
- `phase`: Phase name where consequence applies
- `role`: Role name making the choice
- `choice`: Description of the choice/action
- `payoff`: Description of the resulting payoff

**Usage**: Captured during META_ROLES_PHASES stage, output to JSON.

**Example**:
```python
PayoffConsequence(
    phase="Decision Phase",
    role="Prisoner",
    choice="Both cooperate",
    payoff="3 points each"
)
```

### PhaseRoleMatrix

**Purpose**: Container for complete phase-role mapping and payoff structure.

**Definition**:
```python
@dataclass
class PhaseRoleMatrix:
    phases: List[PhaseRoleTasks] = field(default_factory=list)
    payoff_consequences: List[PayoffConsequence] = field(default_factory=list)
```

**Fields**:
- `phases`: List of all game phases with role tasks
- `payoff_consequences`: List of all payoff rules

**Usage**: Aggregated view for analysis or validation (currently unused in main pipeline).

**Example**:
```python
PhaseRoleMatrix(
    phases=[
        PhaseRoleTasks(phase="Round 1", phase_number=1, actionable=True, ...),
        PhaseRoleTasks(phase="Round 2", phase_number=2, actionable=True, ...)
    ],
    payoff_consequences=[
        PayoffConsequence(...),
        PayoffConsequence(...)
    ]
)
```

## YAML Configuration Models (yaml_dataclasses.py)

These models define the structure of the final YAML output.

### PromptPartial

**Purpose**: Reusable prompt template snippet.

**Definition**:
```python
@dataclass
class PromptPartial:
    name: str
    content: str
```

**Fields**:
- `name`: Unique identifier (e.g., "game_description", "system_prisoner_1")
- `content`: Template text (may include Jinja2 syntax)

**Naming Conventions**:
- `game_description`: High-level game overview
- `game_information`: Dynamic context template
- `game_history`: Historical recap template
- `system_<role>_<phase>`: System prompt for role in phase
- `user_<role>_<phase>`: User instructions for role in phase

**Example**:
```python
PromptPartial(
    name="game_description",
    content="This is a Prisoner's Dilemma game where two players must decide whether to cooperate or defect."
)
```

### EventHandler

**Purpose**: Defines event-driven behavior in the game manager.

**Definition**:
```python
@dataclass
class EventHandler:
    event: str
    custom_code: Optional[str] = None
    custom_module: Optional[str] = None
    custom_function: Optional[str] = None
```

**Fields**:
- `event`: Event name to handle (e.g., "player-action", "round-end")
- `custom_code`: Inline Python code to execute
- `custom_module`: Module path to import
- `custom_function`: Function name to call

**Usage**: At most one of custom_code, custom_module, or custom_function should be set.

**Example**:
```python
EventHandler(
    event="round-end",
    custom_module="game.handlers",
    custom_function="calculate_payoffs"
)
```

### RolePromptEntry

**Purpose**: Single prompt (system or user) for an agent role.

**Definition**:
```python
@dataclass
class RolePromptEntry:
    key: str
    content: str
```

**Fields**:
- `key`: Prompt type identifier
  - "system": Base system prompt
  - "user": Base user prompt
  - "system_phase_N": Phase-specific system prompt
  - "user_phase_N": Phase-specific user prompt
- `content`: Prompt text (Jinja2 template)

**Key Naming Rules**:
- Base prompts: "system", "user"
- Phase-specific: Append "_phase_<number>"
- Must be unique within a role

**Example**:
```python
RolePromptEntry(
    key="system",
    content="You are a prisoner in a dilemma game. Your goal is to maximize your score."
)
```

### AgentRoleConfig

**Purpose**: Complete configuration for an agent role.

**Definition**:
```python
@dataclass
class AgentRoleConfig:
    role_id: Optional[int]
    name: Optional[str]
    llm_type: Optional[str] = None
    llm_params: Optional[Dict[str, Any]] = None
    prompts: List[RolePromptEntry] = field(default_factory=list)
    task_phases: List[int] = field(default_factory=list)
    task_phases_excluded: List[int] = field(default_factory=list)
```

**Fields**:
- `role_id`: Unique integer identifier for the role
- `name`: Human-readable role name
- `llm_type`: LLM class name (e.g., "ChatOpenAI", "ChatAnthropic")
- `llm_params`: Dictionary of LLM configuration
  - `model`: Model name (e.g., "gpt-4", "claude-3")
  - `temperature`: Sampling temperature (0.0-2.0)
  - `max_tokens`: Maximum response length
  - Other model-specific parameters
- `prompts`: List of prompt entries for this role
- `task_phases`: Phases where role is active (list of phase numbers)
- `task_phases_excluded`: Phases to exclude even if in task_phases

**Constraints**:
- Must have at least one prompt with key="system"
- All prompt keys must be unique
- role_id must be unique across experiment

**Example**:
```python
AgentRoleConfig(
    role_id=1,
    name="Prisoner",
    llm_type="ChatOpenAI",
    llm_params={"model": "gpt-4", "temperature": 0.7},
    prompts=[
        RolePromptEntry(key="system", content="You are a prisoner..."),
        RolePromptEntry(key="user", content="Choose COOPERATE or DEFECT.")
    ],
    task_phases=[1, 2, 3],
    task_phases_excluded=[]
)
```

### AgentMappingConfig

**Purpose**: Maps an individual agent instance to a role.

**Definition**:
```python
@dataclass
class AgentMappingConfig:
    id: Optional[int]
    role_id: Optional[int]
```

**Fields**:
- `id`: Unique agent identifier (across all agents)
- `role_id`: Reference to AgentRoleConfig.role_id

**Usage**: Multiple agents can share the same role_id (e.g., two prisoners in a game).

**Example**:
```python
# Two prisoners in same game
AgentMappingConfig(id=1, role_id=1)  # Prisoner 1
AgentMappingConfig(id=2, role_id=1)  # Prisoner 2
```

### StateFieldConfig

**Purpose**: Configuration for a single state variable.

**Definition**:
```python
@dataclass
class StateFieldConfig:
    name: Optional[str]
    type: Optional[str]
    default: Any = None
    default_factory: Optional[str] = None
    event_key: Optional[str] = None
    exclude_from_mapping: Optional[bool] = None
    optional: Optional[bool] = None
    events: Optional[List[str]] = None
    exclude_events: Optional[List[str]] = None
```

**Fields**:
- `name`: Variable name (snake_case)
- `type`: Python type as string ("int", "str", "bool", "list", "dict")
- `default`: Default value for immutable types
- `default_factory`: Factory function for mutable types ("list", "dict")
- `event_key`: Key in event data to map to this variable
- `exclude_from_mapping`: Don't auto-map from events if True
- `optional`: Can be None
- `events`: List of events that update this variable
- `exclude_events`: Events to ignore for this variable

**Type Guidelines**:
- Use `default` for immutable types (int, str, bool, None)
- Use `default_factory` for mutable types (list, dict)
- Never set both `default` and `default_factory`

**Example**:
```python
StateFieldConfig(
    name="round",
    type="int",
    default=1,
    event_key="round_number",
    events=["round-start"],
    optional=False
)
```

### StateConfig

**Purpose**: Container for all state variables categorized by visibility.

**Definition**:
```python
@dataclass
class StateConfig:
    meta_information: List[StateFieldConfig] = field(default_factory=list)
    private_information: List[StateFieldConfig] = field(default_factory=list)
    public_information: List[StateFieldConfig] = field(default_factory=list)
```

**Fields**:
- `meta_information`: Game-level state (round number, phase, etc.)
- `private_information`: Role-specific private state (individual scores, choices)
- `public_information`: Globally visible state (history, announcements)

**Visibility Rules**:
- Meta: Accessible to game manager and all agents
- Private: Accessible only to specific role
- Public: Accessible to all agents

**Example**:
```python
StateConfig(
    meta_information=[
        StateFieldConfig(name="round", type="int", default=1),
        StateFieldConfig(name="phase", type="str", default="waiting")
    ],
    private_information=[
        StateFieldConfig(name="score", type="int", default=0),
        StateFieldConfig(name="last_choice", type="str", default="")
    ],
    public_information=[
        StateFieldConfig(name="history", type="list", default_factory="list")
    ]
)
```

### ManagerConfig

**Purpose**: Game manager configuration.

**Definition**:
```python
@dataclass
class ManagerConfig:
    type: str = "TurnBasedPhaseManager"
    event_handlers: List[EventHandler] = field(default_factory=list)
```

**Fields**:
- `type`: Manager class name
  - "TurnBasedPhaseManager": Sequential turns
  - "SimultaneousActionManager": All agents act simultaneously
  - Custom manager class name
- `event_handlers`: List of event-driven behaviors

**Example**:
```python
ManagerConfig(
    type="TurnBasedPhaseManager",
    event_handlers=[
        EventHandler(event="round-end", custom_function="update_scores")
    ]
)
```

### RunnerConfig

**Purpose**: Game runner and server configuration.

**Definition**:
```python
@dataclass
class RunnerConfig:
    type: str = "GameRunner"
    protocol: str = "ws"
    hostname: str = "localhost"
    path: str = "wss"
    port: int = 0
    game_id: int = 0
    logs_dir: str = "logs"
    log_level: str = "INFO"
    prompts_dir: str = "prompts"
    phase_transition_event: str = "phase-transition"
    phase_identifier_key: str = "phase"
    observability_provider: Optional[Literal["langsmith", "langfuse"]] = None
    continuous_phases: List[int] = field(default_factory=list)
    min_action_delay: int = 5
    max_action_delay: int = 10
```

**Fields**:
- `type`: Runner class name ("GameRunner", "HybridGameRunner")
- `protocol`: Communication protocol ("ws" for WebSocket)
- `hostname`: Server hostname (default: "localhost")
- `path`: WebSocket path (default: "wss")
- `port`: Server port (0 = auto-assign)
- `game_id`: Unique game identifier
- `logs_dir`: Log file output directory
- `log_level`: Logging verbosity ("DEBUG", "INFO", "WARNING", "ERROR")
- `prompts_dir`: Directory containing prompt templates
- `phase_transition_event`: Event name for phase changes
- `phase_identifier_key`: Key identifying phase in event data
- `observability_provider`: LLM tracing provider ("langsmith", "langfuse", None)
- `continuous_phases`: List of phase numbers that run continuously (for HybridGameRunner)
- `min_action_delay`: Minimum seconds between agent actions
- `max_action_delay`: Maximum seconds between agent actions

**Runner Types**:
- **GameRunner**: Standard sequential game runner
- **HybridGameRunner**: Supports both turn-based and continuous phases

**Example**:
```python
RunnerConfig(
    type="GameRunner",
    protocol="ws",
    hostname="localhost",
    port=8080,
    game_id=1,
    logs_dir="logs/game1",
    log_level="INFO",
    phase_transition_event="phase-change",
    observability_provider="langsmith"
)
```

### ExperimentConfig

**Purpose**: Root configuration object containing all experiment settings.

**Definition**:
```python
@dataclass
class ExperimentConfig:
    name: Optional[str]
    description: Optional[str] = ""
    prompt_partials: List[PromptPartial] = field(default_factory=list)
    agent_roles: List[AgentRoleConfig] = field(default_factory=list)
    agents: List[AgentMappingConfig] = field(default_factory=list)
    state: StateConfig = field(default_factory=StateConfig)
    manager: ManagerConfig = field(default_factory=ManagerConfig)
    runner: RunnerConfig = field(default_factory=RunnerConfig)
```

**Fields**:
- `name`: Experiment name
- `description`: Longer experiment description
- `prompt_partials`: Reusable prompt snippets
- `agent_roles`: Role definitions
- `agents`: Agent-to-role mappings
- `state`: State variable configuration
- `manager`: Manager configuration
- `runner`: Runner configuration

**Methods**:

#### to_template_context()

Converts ExperimentConfig to dictionary for Jinja2 template rendering.

**Signature**:
```python
def to_template_context(self) -> Dict[str, Any]
```

**Returns**: Dictionary with keys matching YAML template variables:
- `experiment_name`: str
- `experiment_description`: str
- `prompt_partials`: List[Dict]
- `agent_roles`: List[Dict]
- `agents`: List[Dict]
- `state`: Dict with meta_information, private_information, public_information
- `manager`: Dict
- `runner`: Dict

**Special Transformations**:
- RolePromptEntry.content mapped to "value" key in template
- All list fields ensured to be lists (not None)
- Dataclasses converted to dicts via asdict()

**Example Output**:
```python
{
    "experiment_name": "Prisoner's Dilemma",
    "experiment_description": "Two-player cooperation game",
    "prompt_partials": [
        {"name": "game_description", "content": "..."}
    ],
    "agent_roles": [
        {
            "role_id": 1,
            "name": "Prisoner",
            "llm_type": "ChatOpenAI",
            "prompts": [
                {"key": "system", "value": "You are a prisoner..."}
            ],
            "task_phases": [1, 2, 3]
        }
    ],
    # ... other fields ...
}
```

## Utility Functions

### make_state_field_from_json()

**Purpose**: Factory function to create StateFieldConfig from JSON dictionary.

**Signature**:
```python
def make_state_field_from_json(field_json: Dict[str, Any]) -> StateFieldConfig
```

**Parameters**:
- `field_json`: Dictionary with state field specification
  - Required: `name` or `id`, `type`
  - Optional: `default`, `default_factory`, `event_key`, `exclude_from_mapping`, `optional`, `events`, `exclude_events`

**Returns**: StateFieldConfig instance

**Example**:
```python
field_data = {
    "name": "round",
    "type": "int",
    "default": 1,
    "events": ["round-start"]
}
config = make_state_field_from_json(field_data)
# StateFieldConfig(name="round", type="int", default=1, events=["round-start"], ...)
```

## JSON Schema Patterns

### Stage 1 Output Schema

The parsed JSON from Stage 1 follows this structure:

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
      "phases": ["string"]
    }
  ],
  "phases": [
    {
      "phase": "string",
      "phase_number": "integer",
      "actionable": "boolean",
      "role_tasks": {
        "RoleName": ["task1", "task2"]
      }
    }
  ],
  "payoff_consequences": [
    {
      "phase": "string",
      "role": "string",
      "choice": "string",
      "payoff": "string"
    }
  ],
  "state": {
    "meta": [
      {
        "id": "string",
        "type": "string",
        "description": "string",
        "default": "any"
      }
    ],
    "public": [...],
    "private": [
      {
        "id": "string",
        "role": "string",
        "type": "string",
        "description": "string",
        "default": "any"
      }
    ]
  },
  "prompt_partials": [
    {
      "name": "string",
      "content": "string"
    }
  ],
  "settings": {
    "random_seed": "integer or string",
    "max_rounds": "integer"
  },
  "ui": {
    "title": "string",
    "instructions": "string"
  }
}
```

### YAML Output Schema

The final YAML conforms to this structure (via econagents_template.yaml.jinja2):

```yaml
name: string
description: string

prompt_partials:
  - name: string
    content: multi-line string

agent_roles:
  - role_id: integer
    name: string
    llm_type: string
    llm_params: object
    prompts:
      - key: value (multi-line)
    task_phases: [integers]
    task_phases_excluded: [integers]

agents:
  - id: integer
    role_id: integer

state:
  meta_information:
    - name: string
      type: string
      default: any
      default_factory: string | null
      event_key: string | null
      exclude_from_mapping: boolean
      optional: boolean
      events: [strings]
      exclude_events: [strings]
  private_information: [...]
  public_information: [...]

manager:
  type: string
  event_handlers:
    - event: string
      custom_code: multi-line string
      custom_module: string
      custom_function: string

runner:
  type: string
  protocol: string
  hostname: string
  path: string
  port: integer
  game_id: integer
  logs_dir: string
  log_level: string
  prompts_dir: string
  phase_transition_event: string
  phase_identifier_key: string
  observability_provider: string
  continuous_phases: [integers]
  min_action_delay: integer
  max_action_delay: integer
```

## Field Validation Rules

### Name Validation

**Role Names**:
- Must be unique within experiment
- Should be descriptive (e.g., "Buyer", "Seller", not "Role1")
- Converted to snake_case for prompt partial names

**State Variable Names**:
- Must be valid Python identifiers (snake_case)
- Must be unique within meta/private/public scope
- Should be descriptive and concise

**Prompt Keys**:
- Must be unique within each role
- Base prompts: "system", "user"
- Phase-specific: "system_phase_N", "user_phase_N"
- Custom keys allowed but discouraged

### Type Validation

**State Variable Types**:
- Valid types: "int", "str", "bool", "list", "dict", "float"
- Must match actual default value type
- Use default_factory for mutable types

**LLM Types**:
- Must be valid EconAgents LLM class name
- Common: "ChatOpenAI", "ChatAnthropic", "ChatCohere"
- Custom LLM classes supported

### Reference Validation

**Agent role_id References**:
- Must refer to existing AgentRoleConfig.role_id
- Multiple agents can share same role_id

**Event References**:
- Event names should be consistent across manager and state
- Common events: "phase-transition", "round-start", "round-end", "player-action"

## Data Transformation Pipeline

### Stage 1: Parse → JSON

```
Natural Language
    |
    v
Meta, Role, Phase, PayoffConsequence objects
    |
    v
GameSpec.to_dict()
    |
    v
JSON dictionary
    |
    v
json.dump() to file
```

### Stage 2: JSON → YAML

```
JSON file
    |
    v
json.load()
    |
    v
Stage extraction (META, ROLES, STATE, etc.)
    |
    v
ExperimentConfig dataclass
    |
    v
to_template_context()
    |
    v
Jinja2 template rendering
    |
    v
YAML file
```

## Common Patterns

### Optional Field Handling

```python
# In dataclass definition
field: Optional[str] = None

# In validation
if field is None or field == "cannot infer":
    # Handle unknown value
    field = "(UPDATE MANUALLY)"
```

### List Field Handling

```python
# In dataclass definition
items: List[Item] = field(default_factory=list)

# In template context
items_ctx = [asdict(item) for item in (self.items or [])]
```

### Nested Structure Handling

```python
# In template context
state_ctx = {
    "meta_information": [asdict(f) for f in self.state.meta_information],
    "private_information": [asdict(f) for f in self.state.private_information],
    "public_information": [asdict(f) for f in self.state.public_information]
}
```

## Best Practices

### Immutability

- Use frozen dataclasses for truly immutable data
- Prefer `field(default_factory=list)` over mutable defaults
- Document when mutation is expected

### Type Hints

- Always provide complete type hints
- Use `Optional[T]` for nullable fields
- Use `List[T]`, `Dict[K, V]` with specific types

### Defaults

- Provide sensible defaults for optional fields
- Use `None` for truly optional fields
- Use default_factory for mutable containers

### Documentation

- Document all public fields
- Explain constraints and relationships
- Provide examples for complex structures

## Related Documentation

- See STAGE_PIPELINE.md for how these models are populated
- See ARCHITECTURE.md for overall data flow
- See API_REFERENCE.md for complete method documentation
