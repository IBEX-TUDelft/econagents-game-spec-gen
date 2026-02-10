# API Reference

This document provides comprehensive API documentation for all public classes and methods in the pipeline.

## parse_in_stages Module

### StagedGameSpecParser

Main orchestrator for Stage 1 (natural language to JSON parsing).

```python
class StagedGameSpecParser:
    def __init__(self, game_spec_dir="game_spec", prompt_dir="prompts/parsing", output_dir="output/parse_out")
```

**Parameters**:
- `game_spec_dir` (str): Directory containing game specification files. Default: "game_spec"
- `prompt_dir` (str): Directory containing prompt templates. Default: "prompts/parsing"
- `output_dir` (str): Directory for output JSON files. Default: "output/parse_out"

**Attributes**:
- `state` (ParserState): Current execution state
- `current_stage_idx` (int): Index of current stage in stages list
- `stages` (List[Stage]): List of parsing stages
- `stage_results` (Dict[Stage, Any]): Results for each completed stage
- `stage_errors` (Dict[Stage, Optional[str]]): Errors for each stage
- `selected_game_path` (Optional[str]): Path to selected game spec file
- `game_spec` (GameSpec): Parsed game specification container
- `last_prompt` (Optional[str]): Last prompt sent to LLM
- `last_llm_response` (Optional[str]): Last response from LLM

#### Methods

##### list_game_specs()

List all available game specification files.

```python
def list_game_specs(self) -> List[str]
```

**Returns**: List of file paths to game spec files in game_spec_dir

**Example**:
```python
parser = StagedGameSpecParser()
specs = parser.list_game_specs()
# ['game_spec/prisoner.md', 'game_spec/dictator.md', ...]
```

##### select_game_spec()

Select a game specification file to parse and reset parser state.

```python
def select_game_spec(self, path: str)
```

**Parameters**:
- `path` (str): Absolute or relative path to game specification file

**Raises**:
- `FileNotFoundError`: If specified file does not exist

**Side Effects**:
- Resets current_stage_idx to 0
- Clears all stage_results and stage_errors
- Creates new empty GameSpec instance

**Example**:
```python
parser.select_game_spec("game_spec/prisoner_dilemma.md")
```

##### run_stage()

Execute LLM call for current stage in background thread.

```python
def run_stage(self, feedback: Optional[str] = None) -> str
```

**Parameters**:
- `feedback` (Optional[str]): Custom prompt to use instead of auto-generated prompt. Used for retries with human feedback.

**Returns**: Name of the stage being run (str)

**Side Effects**:
- Sets state to WAITING_RESPONSE
- Starts background thread for LLM execution
- Updates last_prompt and last_llm_response

**Thread Safety**: Uses internal lock for state updates

**Example**:
```python
stage_name = parser.run_stage()
parser.wait_for_llm()  # Block until completion
```

##### wait_for_llm()

Block until LLM response is ready.

```python
def wait_for_llm(self, poll_interval=0.5)
```

**Parameters**:
- `poll_interval` (float): Seconds between status checks. Default: 0.5

**Behavior**:
- Polls parser state every poll_interval seconds
- Prints progress message every 10 polls
- Returns when state is no longer WAITING_RESPONSE

**Example**:
```python
parser.run_stage()
parser.wait_for_llm(poll_interval=1.0)  # Check every second
```

##### get_current_stage()

Get name of current parsing stage.

```python
def get_current_stage(self) -> str
```

**Returns**: Stage name (e.g., "meta_roles_phases")

**Example**:
```python
print(f"Now executing: {parser.get_current_stage()}")
```

##### get_stage_result()

Get parsed result of current stage.

```python
def get_stage_result(self) -> Any
```

**Returns**: Parsed data for current stage (JSON dictionary), or None if not available

**Example**:
```python
if parser.get_state() == "SUCCESS":
    result = parser.get_stage_result()
    print(json.dumps(result, indent=2))
```

##### get_stage_error()

Get error message for current stage.

```python
def get_stage_error(self) -> Optional[str]
```

**Returns**: Error message string, or None if no error

**Example**:
```python
if parser.get_state() == "ERROR":
    error = parser.get_stage_error()
    print(f"Error: {error}")
```

##### get_state()

Get current parser state.

```python
def get_state(self) -> str
```

**Returns**: State name (e.g., "IDLE", "SUCCESS", "ERROR")

**Possible States**:
- "IDLE": Ready for next operation
- "SELECTING_GAME": Game spec selection in progress
- "WAITING_RESPONSE": LLM call in progress
- "PROCESSING_RESPONSE": Validating LLM response
- "SUCCESS": Current stage completed successfully
- "ERROR": Current stage encountered error
- "WRITING_FILE": Writing final JSON to disk

##### next_stage()

Advance to next parsing stage.

```python
def next_stage(self) -> Optional[str]
```

**Returns**: Name of next stage, or None if all stages complete

**Side Effects**:
- Increments current_stage_idx
- Resets state to IDLE

**Example**:
```python
next_stage_name = parser.next_stage()
if next_stage_name:
    print(f"Moving to stage: {next_stage_name}")
else:
    print("All stages complete!")
```

##### retry_stage_with_feedback()

Retry current stage with human feedback.

```python
def retry_stage_with_feedback(self, human_feedback: Optional[str] = None)
```

**Parameters**:
- `human_feedback` (Optional[str]): Additional guidance for LLM

**Behavior**:
- Constructs retry prompt including:
  - Standard prompt for current stage
  - Previous LLM response
  - Validation error message (if any)
  - Human feedback (if provided)
- Calls run_stage() with constructed prompt

**Example**:
```python
if parser.get_state() == "ERROR":
    feedback = "Please extract only two roles, not three."
    parser.retry_stage_with_feedback(feedback)
    parser.wait_for_llm()
```

##### all_stages_successful()

Check if all parsing stages completed successfully.

```python
def all_stages_successful(self) -> bool
```

**Returns**: True if all stages have results, False otherwise

**Example**:
```python
if parser.all_stages_successful():
    output_path = parser.write_results_to_file()
```

##### write_results_to_file()

Write final parsed game spec to JSON file.

```python
def write_results_to_file(self, output_path: Optional[str] = None) -> str
```

**Parameters**:
- `output_path` (Optional[str]): Custom output path. If None, auto-generates timestamped filename.

**Returns**: Path to written JSON file

**Raises**:
- `Exception`: If not all stages completed successfully

**Side Effects**:
- Creates output directory if needed
- Writes JSON file to disk
- Sets state to WRITING_FILE

**Example**:
```python
output_path = parser.write_results_to_file()
print(f"Saved to: {output_path}")
# Output: Saved to: output/parse_out/prisoner_20260119_143022.json
```

##### print_next_prompt_excluding_game_instructions()

Print preview of next prompt without full game spec text.

```python
def print_next_prompt_excluding_game_instructions()
```

**Behavior**:
- Renders prompt for current stage
- Replaces game instructions with placeholder text
- Prints to stdout in gray color

**Use Case**: Show user what will be sent to LLM without overwhelming output

## interpret_in_stages Module

### StagedYamlInterpreter

Main orchestrator for Stage 2 (JSON to YAML interpretation).

```python
class StagedYamlInterpreter:
    def __init__(self, parsed_json_path=None, interpret_prompts_dir="prompts/interpret", 
                 template_dir="templates", output_dir="output/experiment_yaml")
```

**Parameters**:
- `parsed_json_path` (Optional[str]): Path to parsed JSON from Stage 1
- `interpret_prompts_dir` (str): Directory with interpretation prompt templates
- `template_dir` (str): Directory with YAML Jinja2 template
- `output_dir` (str): Directory for output YAML files

**Attributes**:
- `state` (RunnerState): Current execution state
- `current_stage_idx` (int): Index of current stage
- `stages` (List[Stage]): List of interpretation stages
- `stage_results` (Dict[Stage, Any]): Results for each stage
- `stage_errors` (Dict[Stage, Optional[str]]): Errors for each stage
- `selected_parsed_json_path` (Optional[str]): Path to selected JSON
- `last_prompt` (Optional[str]): Last prompt sent to LLM
- `last_llm_response` (Optional[str]): Last LLM response
- `max_auto_retries` (int): Maximum automatic retries on validation failure

#### Methods

##### list_parsed_specs()

List available parsed JSON files from Stage 1.

```python
def list_parsed_specs(self) -> List[str]
```

**Returns**: List of JSON file paths in output/parse_out/

**Example**:
```python
interpreter = StagedYamlInterpreter()
specs = interpreter.list_parsed_specs()
# ['output/parse_out/prisoner_20260119.json', ...]
```

##### select_parsed_json()

Select a parsed JSON file and validate it.

```python
def select_parsed_json(self, path: str)
```

**Parameters**:
- `path` (str): Path to parsed JSON file

**Raises**:
- `FileNotFoundError`: If file doesn't exist
- `json.JSONDecodeError`: If file is not valid JSON

**Side Effects**:
- Resets all stage results and errors
- Sets state to IDLE
- Resets current_stage_idx to 0

##### run_stage()

Execute LLM call for current stage with auto-retry support.

```python
def run_stage(self, feedback: Optional[str] = None) -> str
```

**Parameters**:
- `feedback` (Optional[str]): Custom prompt for retry

**Returns**: Name of stage being run

**Behavior**: Similar to parse_in_stages.run_stage() but with auto-retry support

##### wait_for_llm()

Block until LLM response ready (same as parse_in_stages version).

```python
def wait_for_llm(self, poll_interval=0.5)
```

##### next_stage()

Advance to next interpretation stage.

```python
def next_stage(self) -> Optional[str]
```

**Returns**: Next stage name or None if complete

##### retry_stage()

Retry current stage with auto-constructed feedback prompt.

```python
def retry_stage(self, human_feedback: Optional[str] = None)
```

**Parameters**:
- `human_feedback` (Optional[str]): Additional human guidance

**Behavior**:
- Includes previous response, error message, and feedback in retry prompt

##### render_yaml()

Render final YAML configuration from ExperimentConfig.

```python
def render_yaml(self, cfg: ExperimentConfig, output_basename: Optional[str] = None) -> str
```

**Parameters**:
- `cfg` (ExperimentConfig): Configuration to render
- `output_basename` (Optional[str]): Custom output filename (without extension)

**Returns**: Path to written YAML file

**Side Effects**:
- Writes YAML file to output_dir
- Applies unknown value marking ("(UPDATE MANUALLY)")
- Injects placeholder elements for empty lists

**Example**:
```python
config = interpreter._merge_into_config()
output_path = interpreter.render_yaml(config, "my_experiment")
# Output: output/experiment_yaml/my_experiment.yaml
```

## yaml_dataclasses Module

### ExperimentConfig

Root configuration object.

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

#### Methods

##### to_template_context()

Convert to Jinja2-compatible dictionary.

```python
def to_template_context(self) -> Dict[str, Any]
```

**Returns**: Dictionary with keys matching econagents_template.yaml.jinja2 variables

**Key Transformations**:
- `name` -> `experiment_name`
- `description` -> `experiment_description`
- `RolePromptEntry.content` -> `prompt.value` in template
- Ensures all lists are present (never None)

### make_state_field_from_json()

Factory function to create StateFieldConfig from JSON dict.

```python
def make_state_field_from_json(field_json: Dict[str, Any]) -> StateFieldConfig
```

**Parameters**:
- `field_json` (Dict): JSON field specification with keys:
  - `name` or `id` (required): Field name
  - `type` (optional): Data type
  - `default`, `default_factory`, `event_key`, etc. (optional)

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
```

## Enumerations

### Stage (parse_in_stages)

```python
class Stage(Enum):
    META_ROLES_PHASES = "meta_roles_phases"
    STATE = "state"
    SETTINGS_UI = "settings_ui"
    PARTIAL_PROMPTS = "partial_prompts"
```

### Stage (interpret_in_stages)

```python
class Stage(Enum):
    META = "meta"
    ROLES = "roles"
    ROLE_PROMPTS_REFINEMENT = "role_prompts_refinement"
    STATE = "state"
    MANAGER = "manager"
    RUNNER = "runner"
    AGENTS = "agents"
```

### ParserState

```python
class ParserState(Enum):
    IDLE = auto()
    SELECTING_GAME = auto()
    WAITING_RESPONSE = auto()
    PROCESSING_RESPONSE = auto()
    READY_FOR_FEEDBACK = auto()
    SUCCESS = auto()
    ERROR = auto()
    WRITING_FILE = auto()
```

### RunnerState

```python
class RunnerState(Enum):
    IDLE = auto()
    WAITING_RESPONSE = auto()
    PROCESSING_RESPONSE = auto()
    READY_FOR_FEEDBACK = auto()
    SUCCESS = auto()
    ERROR = auto()
    WRITING_FILE = auto()
```

## Usage Examples

### Complete Parsing Pipeline

```python
from parse_in_stages import StagedGameSpecParser

# Initialize parser
parser = StagedGameSpecParser()

# Select game spec
parser.select_game_spec("game_spec/prisoner_dilemma.md")

# Run all stages interactively
for stage in parser.stages:
    parser.run_stage()
    parser.wait_for_llm()
    
    if parser.get_state() == "ERROR":
        error = parser.get_stage_error()
        print(f"Error: {error}")
        # Provide feedback or skip
        feedback = input("Enter feedback (or press Enter to skip): ")
        if feedback:
            parser.retry_stage_with_feedback(feedback)
            parser.wait_for_llm()
    
    if parser.get_state() == "SUCCESS":
        result = parser.get_stage_result()
        print(f"Stage {parser.get_current_stage()} succeeded")
        parser.next_stage()

# Write final JSON
if parser.all_stages_successful():
    output_path = parser.write_results_to_file()
    print(f"Saved to: {output_path}")
```

### Complete Interpretation Pipeline

```python
from interpret_in_stages import StagedYamlInterpreter

# Initialize interpreter
interpreter = StagedYamlInterpreter()

# Select parsed JSON
interpreter.select_parsed_json("output/parse_out/prisoner_20260119.json")

# Run all stages with auto-retry
for stage in interpreter.stages:
    interpreter.run_stage()
    interpreter.wait_for_llm()
    
    # Auto-retry up to max_auto_retries on error
    retry_count = 0
    while interpreter.state == "ERROR" and retry_count < interpreter.max_auto_retries:
        print(f"Auto-retrying ({retry_count + 1}/{interpreter.max_auto_retries})...")
        interpreter.retry_stage()
        interpreter.wait_for_llm()
        retry_count += 1
    
    if interpreter.state == "SUCCESS":
        interpreter.next_stage()

# Render final YAML
config = interpreter._merge_into_config()
output_path = interpreter.render_yaml(config)
print(f"YAML saved to: {output_path}")
```

### Programmatic Configuration Building

```python
from yaml_dataclasses import (
    ExperimentConfig, AgentRoleConfig, RolePromptEntry,
    AgentMappingConfig, StateConfig, StateFieldConfig,
    ManagerConfig, RunnerConfig
)

# Build configuration programmatically
config = ExperimentConfig(
    name="My Experiment",
    description="A simple two-player game",
    agent_roles=[
        AgentRoleConfig(
            role_id=1,
            name="Player",
            llm_type="ChatOpenAI",
            llm_params={"model": "gpt-4", "temperature": 0.7},
            prompts=[
                RolePromptEntry(key="system", content="You are a player in a game."),
                RolePromptEntry(key="user", content="Choose your action.")
            ],
            task_phases=[1, 2, 3]
        )
    ],
    agents=[
        AgentMappingConfig(id=1, role_id=1),
        AgentMappingConfig(id=2, role_id=1)
    ],
    state=StateConfig(
        meta_information=[
            StateFieldConfig(name="round", type="int", default=1)
        ],
        public_information=[
            StateFieldConfig(name="history", type="list", default_factory="list")
        ]
    ),
    manager=ManagerConfig(type="TurnBasedPhaseManager"),
    runner=RunnerConfig(port=8080, game_id=1)
)

# Render to YAML
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader("templates"))
template = env.get_template("econagents_template.yaml.jinja2")
context = config.to_template_context()
yaml_text = template.render(**context)
print(yaml_text)
```

## Error Handling

All public methods may raise standard Python exceptions:

- `FileNotFoundError`: File operations with invalid paths
- `json.JSONDecodeError`: Invalid JSON parsing
- `ValueError`: Invalid parameter values
- `RuntimeError`: Async/threading errors
- `Exception`: General errors with descriptive messages

Best practice: Wrap API calls in try-except blocks for production use.

## Thread Safety

Both StagedGameSpecParser and StagedYamlInterpreter use internal threading.Lock for state management. Public methods are thread-safe for state reads/writes, but you should not call run_stage() multiple times concurrently on the same instance.

## See Also

- ARCHITECTURE.md: System design and components
- DEVELOPER_GUIDE.md: Getting started and common tasks
- STAGE_PIPELINE.md: Detailed stage documentation
- DATA_MODELS.md: Complete data model documentation
