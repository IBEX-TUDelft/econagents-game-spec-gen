# Future Roadmap

This document outlines planned features and improvements for the EconAgents Game Spec Generation Pipeline.

## Current Status (January 2026)

The pipeline consists of two working stages:

**Stage 1 (parse_in_stages.py)**: Natural language → Structured JSON
**Stage 2 (interpret_in_stages.py)**: Structured JSON → YAML configuration

Both stages are functional and tested with multiple game specifications.

## Planned Features

### Priority 1: Stage 3 - Schema-Driven Prompt Generation

**Status**: Planned, not yet implemented

**Problem Statement**:
Currently, Stage 2 outputs YAML files with placeholder prompts marked as "(UPDATE MANUALLY)". Users must manually write prompts that enforce structured agent outputs. This is error-prone and time-consuming.

**Proposed Solution**:
Implement Stage 3 that consumes JSON schema files and automatically generates prompts that enforce schema compliance.

#### Stage 3 Architecture

**Input**:
1. YAML file from Stage 2 (with placeholder prompts)
2. JSON Schema files defining expected agent output formats
3. Mapping file linking roles/phases to schemas

**Process**:
1. Identify placeholder prompts in YAML
2. Load corresponding JSON schemas
3. For each placeholder:
   - Generate system prompt explaining the schema
   - Generate user prompt with output format requirements
   - Include validation examples
   - Test prompt with sample inputs
4. Replace placeholders with generated prompts
5. Validate that generated prompts enforce schemas

**Output**:
1. Complete YAML file (no placeholders)
2. Validation report showing schema compliance
3. Test results from sample executions

#### JSON Schema Integration

**Schema Format Options**:

**Option A: Standard JSON Schema**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["COOPERATE", "DEFECT"]
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    }
  },
  "required": ["action"]
}
```

Pros:
- Standard format
- Many validation libraries
- Well-documented

Cons:
- Verbose for simple schemas
- No prompt-specific hints

**Option B: Pydantic Models**
```python
from pydantic import BaseModel, Field

class AgentAction(BaseModel):
    action: Literal["COOPERATE", "DEFECT"] = Field(description="Your choice")
    confidence: float = Field(ge=0, le=1, description="Confidence level")
```

Pros:
- Python-native
- Better error messages
- Easier testing

Cons:
- Requires Python dependency
- Less portable

**Option C: Custom DSL**
```yaml
output_schema:
  action:
    type: enum
    values: [COOPERATE, DEFECT]
    required: true
    description: "Your strategic choice for this round"
  confidence:
    type: float
    range: [0, 1]
    required: false
```

Pros:
- Simple and readable
- Prompt-friendly descriptions
- Easy to extend

Cons:
- Non-standard
- Requires custom parser

**Recommendation**: Start with Option A (JSON Schema) for standards compliance, with Option B as future enhancement.

#### Mapping File Format

```yaml
schema_mappings:
  - role: "Prisoner"
    phase: 2
    prompt_type: "user"
    schema_file: "schemas/prisoner_decision.json"
    validation_mode: "strict"
    
  - role: "Developer"
    phase: 2
    prompt_type: "user"
    schema_file: "schemas/developer_choice.json"
    validation_mode: "flexible"
```

Fields:
- `role`: Role name matching YAML
- `phase`: Phase number
- `prompt_type`: "system" or "user"
- `schema_file`: Path to JSON schema
- `validation_mode`: "strict" (enforce exact schema) or "flexible" (allow extras)

#### Prompt Generation Strategy

**Template-Based Generation**:

```python
def generate_schema_prompt(schema: dict, mode: str) -> str:
    """Generate prompt that enforces JSON schema."""
    
    # Extract schema info
    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})
    
    # Build prompt
    prompt = "You must respond with valid JSON matching this structure:\n\n"
    prompt += json.dumps(schema, indent=2)
    prompt += "\n\nRequired fields: " + ", ".join(required_fields)
    
    # Add examples
    prompt += "\n\nExample valid response:\n"
    prompt += generate_example_from_schema(schema)
    
    if mode == "strict":
        prompt += "\n\nDo not include any extra fields."
    
    return prompt
```

**LLM-Assisted Generation**:

Alternative approach: Use LLM to generate prompts from schemas.

```python
async def llm_generate_prompt(schema: dict, context: dict) -> str:
    """Use LLM to generate prompt from schema."""
    
    meta_prompt = f"""
    Generate a clear, concise prompt that instructs an AI agent to output
    JSON matching this schema:
    
    {json.dumps(schema, indent=2)}
    
    Context about the game:
    {json.dumps(context, indent=2)}
    
    The prompt should:
    1. Explain what the agent needs to output
    2. Provide the exact JSON schema
    3. Include an example
    4. Emphasize required fields
    5. Be friendly but precise
    """
    
    return await llm.get_response(meta_prompt)
```

#### Validation and Testing

**Validation Pipeline**:

1. **Syntax Validation**: Ensure generated prompts are valid text
2. **Schema Validation**: Parse example outputs against schemas
3. **Mock Testing**: Test prompts with mock LLM responses
4. **Live Testing**: Execute prompts with real LLM and validate outputs

**Validation Report Example**:

```
Schema Validation Report
========================

Role: Prisoner, Phase: 2
Schema: schemas/prisoner_decision.json
Status: PASS

Test Cases:
  1. Valid cooperative response: PASS
  2. Valid defect response: PASS
  3. Invalid response (extra fields): FAIL (as expected)
  4. Missing required field: FAIL (as expected)

Generated Prompt Quality:
  - Clarity: 9/10
  - Completeness: 10/10
  - Example quality: 8/10

Recommendations:
  - Consider adding more context about payoffs
  - Example could include confidence explanation
```

#### Implementation Plan

**Phase 1: Core Infrastructure**
1. Create `schema_driven_prompts.py` module
2. Implement JSON Schema parser
3. Implement basic prompt generator
4. Add validation framework

**Phase 2: Integration**
5. Extend interpret_in_stages.py to call Stage 3
6. Create mapping file parser
7. Add placeholder detection logic
8. Implement prompt replacement

**Phase 3: Testing and Validation**
9. Create test suite with sample schemas
10. Implement validation pipeline
11. Add reporting functionality
12. Test with existing game specs

**Phase 4: Enhancement**
13. Add LLM-assisted prompt generation
14. Support Pydantic models
15. Add interactive refinement mode
16. Create schema library for common patterns

#### Design Decisions to Make

**Question 1: Schema Location**

Where should JSON schema files be stored?

- Option A: `schemas/` directory (parallel to prompts/)
- Option B: Embedded in YAML as separate section
- Option C: External schema repository

**Question 2: Prompt Replacement Strategy**

How to identify which prompts need schema enforcement?

- Option A: Explicit markers in YAML ("SCHEMA_PLACEHOLDER")
- Option B: Detect "(UPDATE MANUALLY)" markers
- Option C: Mapping file specifies all schema-driven prompts

**Question 3: Validation Timing**

When to validate schema compliance?

- Option A: At prompt generation time (static analysis)
- Option B: At runtime (during game execution)
- Option C: Both (generate tests + runtime validation)

**Question 4: Schema Evolution**

How to handle schema changes over time?

- Option A: Versioned schemas (schema_v1.json, schema_v2.json)
- Option B: Schema migration scripts
- Option C: Regenerate prompts when schemas change

### Priority 2: Automated Testing

**Status**: Not implemented

**Goal**: Create comprehensive test suite for both parsing and interpretation pipelines.

**Planned Components**:

**Unit Tests**:
- Validator functions for each stage
- Context composition logic
- Data model serialization/deserialization
- Template rendering edge cases

**Integration Tests**:
- End-to-end pipeline with fixed game specs
- Mock LLM responses for deterministic testing
- Schema conformance validation
- Error recovery and retry logic

**Regression Tests**:
- Known good outputs for each example game spec
- Detect unintended changes in behavior
- Performance benchmarks

**Implementation**:
```python
# tests/test_parser.py
import unittest
from parse_in_stages import StagedGameSpecParser, Stage

class TestParserValidation(unittest.TestCase):
    def test_meta_stage_validation(self):
        parser = StagedGameSpecParser()
        valid_data = {
            "meta": {...},
            "roles": [],
            "phases": [],
            "payoff_consequences": []
        }
        is_valid, error = parser._validate_stage(Stage.META_ROLES_PHASES, valid_data)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
```

### Priority 3: Interactive CLI Improvements

**Status**: Basic CLI exists

**Planned Enhancements**:

1. **Command-Line Arguments**:
   ```bash
   python parse_in_stages.py --input game_spec/prisoner.md --output custom_output.json
   python interpret_in_stages.py --input parsed.json --auto-accept --skip-errors
   ```

2. **Non-Interactive Mode**:
   - Auto-accept all LLM responses
   - Skip stages on error
   - Batch processing of multiple specs

3. **Progress Indicators**:
   - Visual progress bars
   - Estimated time remaining
   - Token usage tracking

4. **Better Error Display**:
   - Syntax-highlighted JSON diffs
   - Structured error messages
   - Suggested fixes for common errors

### Priority 4: Prompt Engineering Improvements

**Status**: Basic prompts implemented

**Planned Enhancements**:

1. **Few-Shot Examples**:
   - Include successful extraction examples in prompts
   - Adapt examples based on game type

2. **Chain-of-Thought Prompting**:
   - Ask LLM to explain reasoning before extraction
   - Improve accuracy for complex game mechanics

3. **Self-Correction**:
   - Ask LLM to validate its own output
   - Auto-retry with feedback on obvious errors

4. **Prompt Versioning**:
   - Track prompt template versions
   - A/B test different prompt strategies
   - Rollback to previous versions

### Priority 5: Documentation Generation

**Status**: Manual documentation

**Planned Enhancements**:

1. **Sphinx Integration**:
   - Auto-generate API docs from docstrings
   - Create searchable HTML documentation
   - Host on ReadTheDocs

2. **Interactive Examples**:
   - Jupyter notebooks demonstrating pipeline
   - Step-by-step walkthroughs
   - Video tutorials

3. **Auto-Generated Diagrams**:
   - State machine diagrams from code
   - Data flow diagrams
   - Class hierarchy diagrams

### Priority 6: Performance Optimization

**Status**: Functional but not optimized

**Planned Enhancements**:

1. **Caching**:
   - Cache LLM responses for identical prompts
   - Cache validated stages
   - Cache template renderings

2. **Parallel Execution**:
   - Run independent stages in parallel
   - Batch multiple game specs
   - Async I/O for file operations

3. **Prompt Optimization**:
   - Reduce token usage
   - More efficient context composition
   - Compressed JSON representations

### Priority 7: Extended Game Spec Support

**Status**: Supports basic game mechanics

**Planned Extensions**:

1. **Complex Payoff Structures**:
   - Matrix games
   - Probabilistic payoffs
   - Time-dependent rewards

2. **Advanced Agent Behaviors**:
   - Memory and learning
   - Communication between agents
   - Coalition formation

3. **Dynamic Game Elements**:
   - Procedural generation
   - Adaptive difficulty
   - Real-time events

## Long-Term Vision

### Stage 4: Runtime Validation and Monitoring

**Concept**: Monitor deployed games and validate agent behaviors match specifications.

**Components**:
- Real-time schema validation
- Anomaly detection
- Performance monitoring
- Automatic error recovery

### Stage 5: Game Spec Optimization

**Concept**: Use ML to optimize game specifications for specific objectives.

**Applications**:
- Maximize engagement
- Balance difficulty
- Ensure fairness
- Optimize for learning outcomes

### Integration with EconAgents Ecosystem

**Planned Integrations**:
1. Direct deployment to EconAgents servers
2. Integration with experiment management tools
3. Connection to data analysis pipelines
4. Shared game spec repository

## Contributing to Roadmap

### How to Propose New Features

1. Open GitHub issue with "Feature Request" label
2. Describe use case and motivation
3. Outline proposed implementation
4. Discuss alternatives and trade-offs

### Priority Criteria

Features prioritized based on:
1. **Impact**: How many users benefit?
2. **Effort**: How complex to implement?
3. **Dependencies**: What else needs to be done first?
4. **Alignment**: Does it fit the vision?

### Current Needs

We especially welcome contributions in:
1. Testing infrastructure
2. Documentation improvements
3. Prompt engineering
4. Schema-driven prompts (Stage 3)

## Version History and Milestones

### v0.1 (Current)
- Two-stage pipeline (parsing + interpretation)
- Interactive CLI
- Basic prompt templates
- Manual YAML completion

### v0.2 (Planned Q2 2026)
- Stage 3: Schema-driven prompts
- Automated testing suite
- Improved CLI with arguments
- Performance optimizations

### v0.3 (Planned Q3 2026)
- Non-interactive batch mode
- Advanced prompt engineering
- Sphinx documentation
- Extended game spec support

### v1.0 (Planned Q4 2026)
- Production-ready pipeline
- Comprehensive documentation
- Full test coverage
- Integration with EconAgents platform

## Technology Considerations

### Potential Technology Additions

**LLM Providers**:
- Add support for Anthropic Claude
- Add support for open-source models (Llama, Mistral)
- Add local LLM support (Ollama)

**Validation**:
- Integrate Pydantic for schema validation
- Add hypothesis for property-based testing
- Consider formal verification tools

**UI/UX**:
- Web-based GUI for pipeline execution
- Visual prompt editor
- Real-time collaboration features

**Infrastructure**:
- Docker containerization
- CI/CD pipelines
- Cloud deployment options

## Feedback and Discussion

### Where to Discuss

- GitHub Issues: Bug reports and feature requests
- GitHub Discussions: General questions and ideas
- Pull Requests: Code contributions

### Contact

For questions about the roadmap or to propose major changes, please open a GitHub Discussion or contact the maintainers.

## Summary

The immediate priority is implementing Stage 3 (Schema-Driven Prompt Generation) to eliminate manual YAML completion. This will make the pipeline fully automated from natural language to deployable configuration.

Longer-term goals include comprehensive testing, better tooling, and integration with the broader EconAgents ecosystem.

Contributions are welcome at all levels, from documentation improvements to major feature implementations.
