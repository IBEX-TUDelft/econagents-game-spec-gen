# Developer Guide

## Quick Start for New Developers

This guide will help you understand the codebase and start contributing within 1-2 hours.

## Prerequisites

### Required Knowledge
- Python 3.11+ (dataclasses, async/await, type hints)
- JSON and YAML formats
- Jinja2 templating basics
- Basic understanding of LLM prompting

### System Requirements
- Linux/macOS (Windows may work but untested)
- Python 3.11 or higher
- OpenAI API key (or compatible LLM endpoint)

## Environment Setup

### 1. Clone and Navigate
```bash
cd /path/to/econagents-game-spec-gen
```

### 2. Create Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_api_key_here
```

### 5. Verify Installation
```bash
python parse_in_stages.py --help 2>/dev/null || echo "Ready to run interactively"
```

## Understanding the Codebase

### Core Files (Read in This Order)

1. **README.md** - High-level overview
2. **ARCHITECTURE.md** - System design and data flow
3. **yaml_dataclasses.py** - Data models (start here for code reading)
4. **parse_in_stages.py** - Stage 1 pipeline
5. **interpret_in_stages.py** - Stage 2 pipeline
6. **templates/econagents_template.yaml.jinja2** - Final output template

### Directory Structure Guide

```
project_root/
|
+-- parse_in_stages.py          # Stage 1: Text to JSON
+-- interpret_in_stages.py      # Stage 2: JSON to YAML
+-- yaml_dataclasses.py         # YAML schema models
+-- gamedataclasses.py          # Parsing data models
|
+-- game_spec/                  # Input: Natural language specs
|   +-- prisoner_dilemma.md
|   +-- dictator.md
|   +-- harberger.txt
|   +-- futachry
|
+-- prompts/
|   +-- parsing/                # Stage 1 prompt templates
|   |   +-- meta_roles_phases_prompt.jinja2
|   |   +-- state_prompt.jinja2
|   |   +-- settings_ui_prompt.jinja2
|   |   +-- partial_prompts_prompt.jinja2
|   |
|   +-- interpret/              # Stage 2 prompt templates
|       +-- meta_prompt.jinja2
|       +-- roles_prompt.jinja2
|       +-- state_prompt.jinja2
|       +-- manager_prompt.jinja2
|       +-- runner_prompt.jinja2
|       +-- agents_prompt.jinja2
|       +-- role_prompts_prompt.jinja2
|
+-- templates/
|   +-- econagents_template.yaml.jinja2  # Immutable YAML template
|
+-- output/
|   +-- parse_out/              # Stage 1 outputs (JSON)
|   +-- experiment_yaml/        # Stage 2 outputs (YAML)
|
+-- documentation/              # You are here
+-- examples/                   # Example configurations
+-- test_game_servers/          # Test implementations
```

## Running the Pipeline

### Stage 1: Parse Natural Language to JSON

```bash
python parse_in_stages.py
```

**Interactive Steps**:
1. Select a game spec file from the menu
2. For each stage (4 total):
   - Review the prompt preview
   - Wait for LLM response (5-15 seconds)
   - Review parsed JSON output
   - Accept (y) or provide feedback (n)
3. Final JSON saved to `output/parse_out/`

**Example Output**:
```
output/parse_out/prisoner_dilemma_20260119_143022.json
```

### Stage 2: Interpret JSON to YAML

```bash
python interpret_in_stages.py
```

**Interactive Steps**:
1. Select a parsed JSON file from Stage 1
2. For each stage (7 total):
   - Review prompt preview (first 1200 chars)
   - Wait for LLM response
   - Review extracted configuration
   - Accept (y) or provide feedback (n)
3. Final YAML and partials saved to `output/experiment_yaml/`

**Example Outputs**:
```
output/experiment_yaml/prisoner_dilemma_20260119_143022.yaml
prompts/_partials/game_description.jinja2
prompts/_partials/game_information.jinja2
prompts/_partials/system_prisoner_1.jinja2
prompts/_partials/user_prisoner_1.jinja2
```

### Manual Completion

Search generated YAML for `(UPDATE MANUALLY)` markers:
```bash
grep -n "UPDATE MANUALLY" output/experiment_yaml/*.yaml
```

Edit these fields with appropriate values based on your game requirements.

## Common Development Tasks

### Task 1: Add a New Parsing Stage

**Use Case**: You need to extract additional information not covered by existing stages.

**Steps**:

1. Define the stage in `parse_in_stages.py`:
```python
class Stage(Enum):
    META_ROLES_PHASES = "meta_roles_phases"
    STATE = "state"
    SETTINGS_UI = "settings_ui"
    PARTIAL_PROMPTS = "partial_prompts"
    YOUR_NEW_STAGE = "your_new_stage"  # Add this
```

2. Update the stages list in `__init__()`:
```python
self.stages = [
    Stage.META_ROLES_PHASES, 
    Stage.STATE, 
    Stage.SETTINGS_UI,
    Stage.YOUR_NEW_STAGE,      # Add before PARTIAL_PROMPTS if it needs context
    Stage.PARTIAL_PROMPTS
]
```

3. Create prompt template at `prompts/parsing/your_new_stage_prompt.jinja2`:
```jinja
{{ header }}

Here are the instructions to parse:
---
{{ instructions }}

{{ context }}

Extract X, Y, Z from the game specification.

Return strictly valid JSON with schema:
{
  "your_data": {
    "field1": "<type>",
    "field2": "<type>"
  }
}
```

4. Add prompt mapping in `_get_prompt_template()`:
```python
prompt_map = {
    Stage.META_ROLES_PHASES: "meta_roles_phases_prompt.jinja2",
    # ... existing mappings ...
    Stage.YOUR_NEW_STAGE: "your_new_stage_prompt.jinja2",
}
```

5. Implement validator in `_validate_stage()`:
```python
elif stage == Stage.YOUR_NEW_STAGE:
    if "your_data" not in data:
        return False, "Missing 'your_data' field"
    # Add specific validation logic
```

6. Update `GameSpec` class if needed:
```python
class GameSpec:
    def __init__(self):
        # ... existing fields ...
        self.your_new_data: Optional[Dict[str, Any]] = None
```

7. Implement data merger in `_update_game_spec()`:
```python
elif stage == Stage.YOUR_NEW_STAGE:
    self.game_spec.your_new_data = data["your_data"]
```

8. Add context composition in `_compose_context_for_stage()` for downstream stages:
```python
elif stage == Stage.SOME_LATER_STAGE:
    your_data = self.stage_results.get(Stage.YOUR_NEW_STAGE, {})
    if your_data:
        context_sections.append("YOUR DATA:\n" + json.dumps(your_data, indent=2))
```

9. Update `to_dict()` method in GameSpec:
```python
def to_dict(self):
    return {
        # ... existing fields ...
        "your_new_data": self.your_new_data,
    }
```

### Task 2: Add a New Interpretation Stage

**Use Case**: You need to extract additional YAML configuration not handled by existing stages.

**Steps**:

1. Add dataclass to `yaml_dataclasses.py` (if needed):
```python
@dataclass
class YourNewConfig:
    field1: Optional[str] = None
    field2: List[str] = field(default_factory=list)
```

2. Add to `ExperimentConfig`:
```python
@dataclass
class ExperimentConfig:
    # ... existing fields ...
    your_config: YourNewConfig = field(default_factory=YourNewConfig)
```

3. Define stage in `interpret_in_stages.py`:
```python
class Stage(Enum):
    META = "meta"
    # ... existing stages ...
    YOUR_NEW_STAGE = "your_new_stage"
```

4. Add to stages list (order matters):
```python
self.stages: List[Stage] = [
    Stage.META,
    Stage.ROLES,
    Stage.YOUR_NEW_STAGE,  # Position based on dependencies
    # ... rest of stages ...
]
```

5. Create prompt at `prompts/interpret/your_new_stage_prompt.jinja2`:
```jinja
{{ header }}
You are the YOUR_NEW_STAGE stage.

Return STRICT JSON with this exact schema:
{
  "your_config": {
    "field1": string | "cannot infer",
    "field2": [string] | []
  }
}

Rules:
- Extract ONLY from provided JSON
- Use "cannot infer" for uncertain fields
- Output must be valid JSON

Parsed JSON:
{{ parsed_json }}
```

6. Add prompt mapping:
```python
fname = {
    # ... existing mappings ...
    Stage.YOUR_NEW_STAGE: "your_new_stage_prompt.jinja2",
}[stage]
```

7. Implement validator:
```python
elif stage == Stage.YOUR_NEW_STAGE:
    if set(data.keys()) != {"your_config"}:
        return False, "YOUR_NEW_STAGE: missing your_config"
    # Add field validation
```

8. Add merger logic in `_merge_into_config()`:
```python
your_data = self.stage_results.get(Stage.YOUR_NEW_STAGE) or {"your_config": {}}
cfg.your_config = YourNewConfig(
    field1=self._coerce_unknown(your_data.get("your_config", {}).get("field1")),
    field2=your_data.get("your_config", {}).get("field2") or [],
)
```

9. Update `to_template_context()` in ExperimentConfig:
```python
def to_template_context(self) -> Dict[str, Any]:
    # ... existing code ...
    return {
        # ... existing fields ...
        "your_config": asdict(self.your_config),
    }
```

10. Update YAML template (if adding to final output):
```jinja
your_config:
  field1: "{{ your_config.field1 }}"
  field2: {{ your_config.field2 }}
```

### Task 3: Modify Prompt Templates

**Use Case**: Improve LLM extraction quality or change schema requirements.

**Guidelines**:

1. **For Parsing Prompts** (prompts/parsing/):
   - Keep schema examples clear and comprehensive
   - Provide context from game specification
   - Allow flexibility in interpretation
   - Include edge case examples

2. **For Interpretation Prompts** (prompts/interpret/):
   - Use strict JSON schemas with exact key sets
   - Emphasize "Extract ONLY from JSON" policy
   - Define "cannot infer" fallback explicitly
   - Keep schemas minimal (required fields only)

**Best Practices**:
- Test with multiple game specs after changes
- Document schema changes in prompt comments
- Version control prompt templates
- Consider backward compatibility with existing JSONs

### Task 4: Debug LLM Response Issues

**Common Issues**:

**1. Invalid JSON Response**
```
Error: Invalid JSON: Expecting property name enclosed in double quotes
```

**Solution**:
- Check LLM response in `self.last_llm_response`
- Add print statement in `_process_stage_response()` before JSON parsing
- Ensure prompt explicitly requests JSON without markdown fences
- Check for trailing commas or comments in LLM output

**2. Schema Validation Failure**
```
Error: ROLES[0]: prompts must be list
```

**Solution**:
- Review validator logic in `_validate_stage()`
- Print the actual data structure before validation
- Check if LLM returned correct type (list vs dict)
- Verify prompt schema matches validator expectations

**3. Missing Context Between Stages**
```
LLM returns: "cannot infer" for everything
```

**Solution**:
- Verify `_compose_context_for_stage()` includes necessary data
- Print composed context before LLM call
- Check stage ordering (later stages need earlier results)
- Ensure previous stage completed successfully

**Debugging Tools**:

Add debug prints:
```python
# Before LLM call
print(f"DEBUG Prompt:\n{prompt[:500]}...")

# After LLM response
print(f"DEBUG Response:\n{self.last_llm_response}")

# Before validation
print(f"DEBUG Parsed:\n{json.dumps(data, indent=2)}")
```

### Task 5: Extend DataClasses

**Use Case**: Add new fields to existing configurations.

**Steps**:

1. Update dataclass in `yaml_dataclasses.py`:
```python
@dataclass
class AgentRoleConfig:
    # ... existing fields ...
    new_field: Optional[str] = None  # Add with default
```

2. Update `to_template_context()` if field needs transformation:
```python
agent_roles_ctx.append({
    # ... existing mappings ...
    "new_field": r.new_field or "default_value",
})
```

3. Update interpretation stage to extract new field
4. Update YAML template to render new field
5. Update validators to check new field if required

**Important**: Always use `Optional[Type]` or provide defaults to maintain backward compatibility.

## Code Style Guidelines

### Python Style
- Follow PEP 8
- Use type hints for all function signatures
- Use dataclasses for data containers
- Prefer f-strings over .format()
- Keep functions under 50 lines when possible

### Docstring Format (Google Style)
```python
def example_function(param1: str, param2: int) -> Dict[str, Any]:
    """Brief one-line description.
    
    Longer description explaining the function's purpose,
    edge cases, and important notes.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter
        
    Returns:
        Dictionary containing result data with keys:
        - key1: Description
        - key2: Description
        
    Raises:
        ValueError: When param1 is empty
        FileNotFoundError: When file doesn't exist
        
    Example:
        >>> result = example_function("test", 42)
        >>> print(result["key1"])
        expected_output
    """
```

### File Naming
- Use snake_case for Python files
- Use kebab-case for documentation
- Use descriptive names (no abbreviations)

### Git Workflow
- Branch naming: `feature/description`, `fix/description`, `docs/description`
- Commit messages: Imperative mood ("Add feature" not "Added feature")
- One logical change per commit
- Reference issue numbers when applicable

## Testing Your Changes

### Manual Testing Checklist

Before submitting changes:

1. **Run Stage 1 with multiple game specs**
   ```bash
   python parse_in_stages.py
   ```
   Test with at least 2 different game spec files

2. **Run Stage 2 with generated JSONs**
   ```bash
   python interpret_in_stages.py
   ```
   Verify YAML syntax is valid

3. **Check YAML validity**
   ```bash
   python -c "import yaml; yaml.safe_load(open('output/experiment_yaml/your_file.yaml'))"
   ```

4. **Verify no regressions**
   - Test with existing example files
   - Compare outputs to known good configurations
   - Check that existing features still work

5. **Test error cases**
   - Invalid game spec files
   - Malformed JSON responses (simulate LLM errors)
   - Missing required fields

### Writing Unit Tests (Recommended for Future)

Example test structure:
```python
import unittest
from parse_in_stages import StagedGameSpecParser, Stage

class TestParser(unittest.TestCase):
    def setUp(self):
        self.parser = StagedGameSpecParser()
        
    def test_validation_meta_stage(self):
        valid_data = {
            "meta": {"game_name": "Test"},
            "roles": [],
            "phases": [],
            "payoff_consequences": []
        }
        is_valid, error = self.parser._validate_stage(Stage.META_ROLES_PHASES, valid_data)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
```

## Common Pitfalls and Solutions

### Pitfall 1: Event Loop Already Running
**Symptom**: RuntimeError about event loop

**Solution**: Ensure each stage creates a new event loop in worker thread. Never call `asyncio.run()` in main thread.

### Pitfall 2: Thread Safety Issues
**Symptom**: Intermittent state corruption or race conditions

**Solution**: Always use `with self.lock:` when reading or writing shared state.

### Pitfall 3: Template Rendering Errors
**Symptom**: Jinja2 TemplateError or UndefinedError

**Solution**:
- Check that all template variables are provided in context
- Use `| default('fallback')` filters for optional values
- Verify template path is correct

### Pitfall 4: JSON Schema Mismatch
**Symptom**: Validation fails despite correct-looking LLM response

**Solution**:
- Print both expected schema and actual data
- Check for type mismatches (string vs int, dict vs list)
- Verify key names match exactly (case-sensitive)

### Pitfall 5: Prompt Context Too Large
**Symptom**: LLM errors or truncated responses

**Solution**:
- Summarize context instead of full JSON dumps
- Remove redundant information from prompts
- Split large stages into smaller ones

## Getting Help

### Resources
1. **Documentation**: Read ARCHITECTURE.md and STAGE_PIPELINE.md
2. **Code Comments**: Inline documentation in source files
3. **Examples**: Study existing game specs and outputs
4. **API Reference**: See API_REFERENCE.md for detailed method docs

### When You're Stuck
1. Add debug print statements to trace execution
2. Check `self.last_prompt` and `self.last_llm_response` for LLM interactions
3. Verify environment variables are set correctly
4. Test with simpler game specs to isolate issues
5. Review git history for similar past changes

## Contributing Guidelines

### Before Starting Work
1. Read ARCHITECTURE.md to understand system design
2. Check existing issues for duplicate work
3. Discuss major changes before implementing

### Pull Request Checklist
- [ ] Code follows style guidelines
- [ ] Added/updated docstrings
- [ ] Tested with multiple game specs
- [ ] Updated documentation if needed
- [ ] No breaking changes to existing APIs (or documented)
- [ ] Commit messages are clear and descriptive

### Documentation Requirements
- Update CHANGELOG.md with your changes
- Add examples if introducing new features
- Update API_REFERENCE.md if changing public APIs
- Add troubleshooting entries for common issues

## Next Steps

Now that you understand the basics:

1. **Read STAGE_PIPELINE.md** for detailed stage documentation
2. **Read DATA_MODELS.md** for schema specifications
3. **Try running the pipeline** with example game specs
4. **Make a small change** (e.g., add a debug print) to practice
5. **Read FUTURE_ROADMAP.md** to see planned features

Welcome to the project!
