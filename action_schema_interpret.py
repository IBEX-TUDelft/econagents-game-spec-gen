import os
import json
import re
import threading
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
from econagents.llm.openai import ChatOpenAI

# Color helpers
BLUE = "\033[1;34m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GRAY = "\033[1;90m"
RESET = "\033[0m"

PLACEHOLDER_PATTERN = r'<ACTION_JSON_PLACEHOLDER>'

class RunnerState(Enum):
    IDLE = auto()
    WAITING_RESPONSE = auto()
    PROCESSING_RESPONSE = auto()
    READY_FOR_FEEDBACK = auto()
    SUCCESS = auto()
    ERROR = auto()

class ActionSchemaInterpreter:
    """Third stage: Finds placeholders in YAML and fills them with JSON from schema."""
    
    def __init__(self,
                 yaml_template_path: Optional[str] = None,
                 schema_path: Optional[str] = None,
                 prompts_dir: str = "prompts/interpret",
                 output_dir: str = "output/experiment_yaml"):
        load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.llm = ChatOpenAI(api_key=self.api_key)
        self.prompts_dir = prompts_dir
        self.output_dir = output_dir
        self.state = RunnerState.IDLE
        
        self.yaml_template_path = yaml_template_path
        self.schema_path = schema_path
        
        self.yaml_content = None
        self.placeholders_found = []
        self.replacements = {}
        
        self.last_prompt = None
        self.last_llm_response = None
        self.error: Optional[str] = None
        self.max_auto_retries = 2
        
    def load_files(self, yaml_template: str, schema: str):
        """Load the input files"""
        if not os.path.isfile(yaml_template):
            raise FileNotFoundError(f"YAML template not found: {yaml_template}")
        if not os.path.isfile(schema):
            raise FileNotFoundError(f"Schema file not found: {schema}")
            
        self.yaml_template_path = yaml_template
        self.schema_path = schema
        
        with open(yaml_template, 'r') as f:
            self.yaml_content = f.read()
        
        with open(schema, 'r') as f:
            self.schema_content = f.read()
        
        # Find all placeholders
        self.placeholders_found = self._find_placeholders()
        
        print(f"{GREEN}✓ Loaded YAML template: {yaml_template}{RESET}")
        print(f"{GREEN}✓ Loaded JSON schema: {schema}{RESET}")
        print(f"{BLUE}Found {len(self.placeholders_found)} placeholder(s) to fill{RESET}\n")
        
    def _find_placeholders(self) -> List[Dict[str, Any]]:
        """Find all placeholders in YAML and extract context"""
        placeholders = []
        lines = self.yaml_content.split('\n')
        
        for i, line in enumerate(lines):
            if PLACEHOLDER_PATTERN in line:
                # Extract context: find the prompt this belongs to
                context = self._extract_prompt_context(lines, i)
                placeholders.append({
                    'line_number': i,
                    'line': line,
                    'context': context
                })
        
        return placeholders
    
    def _extract_prompt_context(self, lines: List[str], placeholder_line: int) -> Dict[str, str]:
        """Extract the prompt context around a placeholder"""
        # Go backwards to find the prompt key (e.g., "- user_phase_2:")
        prompt_key = None
        role_name = None
        prompt_content_lines = []
        
        for i in range(placeholder_line - 1, max(0, placeholder_line - 50), -1):
            line = lines[i]
            # Look for prompt key pattern
            if re.match(r'\s+- \w+:', line):
                prompt_key = line.strip().lstrip('- ').rstrip(':')
                break
            else:
                prompt_content_lines.insert(0, line)
        
        # Go further back to find role name
        for i in range(placeholder_line - 1, max(0, placeholder_line - 100), -1):
            line = lines[i]
            if 'name:' in line and 'role_id' in lines[i-1] if i > 0 else False:
                role_name = line.split('name:')[1].strip().strip('"')
                break
        
        return {
            'role': role_name or 'unknown',
            'prompt_key': prompt_key or 'unknown',
            'prompt_content': '\n'.join(prompt_content_lines[-10:])  # Last 10 lines before placeholder
        }
    
    def _get_prompt_template(self) -> str:
        """Load the action interpretation prompt template"""
        path = os.path.join(self.prompts_dir, "actions_prompt.jinja2")
        with open(path, "r") as f:
            return f.read()
    
    def _render_prompt_for_placeholder(self, placeholder_info: Dict[str, Any]) -> str:
        """Render a prompt to ask LLM for JSON for this specific placeholder"""
        from jinja2 import Template
        
        context = placeholder_info['context']
        
        # Load the template
        template_str = self._get_prompt_template()
        template = Template(template_str)
        
        # Render with context
        prompt = template.render(
            prompt_context=context['prompt_content'],
            json_schema=self.schema_content
        )
        
        self.last_prompt = prompt
        return prompt
    
    async def _run_llm_async(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are a JSON generator. Reply with valid JSON only."},
            {"role": "user", "content": prompt}
        ]
        tracing_extra = {}
        response = await self.llm.get_response(messages, tracing_extra)
        self.last_llm_response = response
        return response
    
    def process_placeholder(self, placeholder_info: Dict[str, Any], skip_interaction: bool = False) -> Optional[str]:
        """Process a single placeholder: ask LLM for JSON instruction"""
        context = placeholder_info['context']
        print(f"\n{BLUE}Processing placeholder for:{RESET}")
        print(f"  Role: {context['role']}")
        print(f"  Prompt: {context['prompt_key']}")
        
        self.state = RunnerState.WAITING_RESPONSE
        prompt = self._render_prompt_for_placeholder(placeholder_info)
        
        # Run LLM
        thread = threading.Thread(target=self._run_llm_thread, args=(prompt,))
        thread.start()
        
        # Wait for response
        count = 0
        while self.state == RunnerState.WAITING_RESPONSE:
            if count % 10 == 0:
                print(f"{GRAY}Waiting for LLM... {count * 0.5:.1f}s{RESET}")
            count += 1
            time.sleep(0.5)
        
        if self.state == RunnerState.ERROR:
            print(f"{RED}Error: {self.error}{RESET}")
            return None
        
        if self.state == RunnerState.SUCCESS:
            try:
                data = json.loads(self.last_llm_response)
                instruction = data.get('instruction', '')
                
                # Unescape the instruction (LLM returns escaped newlines, etc.)
                instruction = instruction.encode().decode('unicode_escape')
                
                print(f"{GREEN}✓ Generated instruction ({len(instruction)} chars){RESET}")
                
                if not skip_interaction:
                    print(f"\n{YELLOW}Preview:{RESET}")
                    print(instruction[:200] + "..." if len(instruction) > 200 else instruction)
                    ok = input(f"\nAccept? (y/n): ").strip().lower() or "y"
                    if ok != "y":
                        feedback = input("Feedback for retry: ").strip()
                        # TODO: Implement retry with feedback
                        print(f"{YELLOW}Retry not yet implemented, using current result{RESET}")
                
                return instruction
            except json.JSONDecodeError as e:
                print(f"{RED}Failed to parse LLM response as JSON: {e}{RESET}")
                return None
        
        return None
    
    def _run_llm_thread(self, prompt: str):
        import asyncio
        def ignore_event_loop_closed(loop, context):
            exception = context.get('exception')
            if isinstance(exception, RuntimeError) and str(exception) == 'Event loop is closed':
                return
            loop.default_exception_handler(context)
        loop = None
        try:
            loop = asyncio.new_event_loop()
            loop.set_exception_handler(ignore_event_loop_closed)
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self._run_llm_async(prompt))
            self.state = RunnerState.SUCCESS
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            self.error = str(e)
            self.state = RunnerState.ERROR
        finally:
            if loop is not None and not loop.is_closed():
                loop.close()
    
    def process_all_placeholders(self, skip_interaction: bool = False):
        """Process all placeholders found in the YAML"""
        for idx, placeholder_info in enumerate(self.placeholders_found, 1):
            print(f"\n{'='*60}")
            print(f"Placeholder {idx}/{len(self.placeholders_found)}")
            print('='*60)
            
            instruction = self.process_placeholder(placeholder_info, skip_interaction)
            if instruction:
                self.replacements[placeholder_info['line_number']] = instruction
            else:
                print(f"{YELLOW}Warning: No instruction generated for this placeholder{RESET}")
    
    def generate_final_yaml(self, output_path: Optional[str] = None) -> str:
        """Replace all placeholders in YAML with generated instructions"""
        if not output_path:
            base = os.path.splitext(os.path.basename(self.yaml_template_path))[0]
            base = base.replace('_template', '')  # Remove _template suffix if present
            output_path = os.path.join(self.output_dir, f"{base}_final.yaml")
        
        lines = self.yaml_content.split('\n')
        
        # Replace placeholders
        for line_number, instruction in self.replacements.items():
            original_line = lines[line_number]
            # Keep the indentation
            indent = len(original_line) - len(original_line.lstrip())
            # Replace placeholder with instruction (indented)
            instruction_indented = '\n'.join(' ' * indent + line for line in instruction.split('\n'))
            lines[line_number] = instruction_indented
        
        final_yaml = '\n'.join(lines)
        
        os.makedirs(self.output_dir, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(final_yaml)
        
        print(f"\n{GREEN}✓ Final YAML written to: {output_path}{RESET}")
        return output_path
        """List available YAML template files (not final YAML, but Jinja2 templates)"""
        candidates = []
        if os.path.isdir(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith(".yaml.jinja2") or f.endswith("_template.yaml"):
                    candidates.append(os.path.join(self.output_dir, f))
        return sorted(candidates)
    
    def list_schema_files(self) -> List[str]:
        """List available JSON schema files"""
        candidates = []
        # Look in common locations
        for d in ["schemas", ".", "examples"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".json") and ("schema" in f.lower() or "openapi" in f.lower() or "spec" in f.lower()):
                        candidates.append(os.path.join(d, f))
        return sorted(candidates)
    
    def select_files(self, yaml_template: str, schema: str, parsed_json: str):
        """Select the input files for this stage"""
        if not os.path.isfile(yaml_template):
            raise FileNotFoundError(f"YAML template not found: {yaml_template}")
        if not os.path.isfile(schema):
            raise FileNotFoundError(f"Schema file not found: {schema}")
        if not os.path.isfile(parsed_json):
            raise FileNotFoundError(f"Parsed JSON not found: {parsed_json}")
            
        self.yaml_template_path = yaml_template
        self.schema_path = schema
        self.parsed_json_path = parsed_json
        self.state = RunnerState.IDLE
        self.result = None
        self.error = None
    
    def _read_file(self, path: str) -> str:
        with open(path, "r") as f:
            return f.read()
    
    def _get_prompt_template(self) -> str:
        path = os.path.join(self.prompts_dir, "actions_prompt.jinja2")
        with open(path, "r") as f:
            return f.read()
    
    def _render_prompt(self) -> str:
        assert self.yaml_template_path and self.schema_path and self.parsed_json_path, "Files not selected"
        
        yaml_content = self._read_file(self.yaml_template_path)
        schema_content = self._read_file(self.schema_path)
        parsed_content = self._read_file(self.parsed_json_path)
        
        header = (
            "You are an assistant that interprets JSON schemas and generates action options for LLM agents.\n"
            "Extract configuration ONLY from the provided JSON schema. Do not infer beyond direct textual or structural evidence.\n"
            "If any field cannot be determined solely from the schema, return empty action_options [] for that mapping.\n"
            "Return STRICT JSON only."
        )
        
        template_str = self._get_prompt_template()
        prompt = template_str.replace("{{ header }}", header)
        prompt = prompt.replace("{{ yaml_template }}", yaml_content)
        prompt = prompt.replace("{{ json_schema }}", schema_content)
        prompt = prompt.replace("{{ parsed_json }}", parsed_content)
        
        self.last_prompt = prompt
        return prompt
    
    async def _run_llm_async(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are a JSON extractor. Reply with valid JSON only."},
            {"role": "user", "content": prompt}
        ]
        tracing_extra = {}
        response = await self.llm.get_response(messages, tracing_extra)
        self.last_llm_response = response
        return response
    
    def run_stage(self, feedback: Optional[str] = None):
        self.state = RunnerState.WAITING_RESPONSE
        prompt = feedback if feedback else self._render_prompt()
        thread = threading.Thread(target=self._run_stage_thread, args=(prompt,))
        thread.start()
    
    def _run_stage_thread(self, prompt: str):
        import asyncio
        def ignore_event_loop_closed(loop, context):
            exception = context.get('exception')
            if isinstance(exception, RuntimeError) and str(exception) == 'Event loop is closed':
                return
            loop.default_exception_handler(context)
        loop = None
        try:
            loop = asyncio.new_event_loop()
            loop.set_exception_handler(ignore_event_loop_closed)
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self._run_llm_async(prompt))
            self.state = RunnerState.PROCESSING_RESPONSE
            self._process_response(response)
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            self.error = str(e)
            self.state = RunnerState.ERROR
        finally:
            if loop is not None and not loop.is_closed():
                loop.close()
    
    def _process_response(self, response: str):
        try:
            data = json.loads(response)
        except Exception as e:
            self.error = f"Invalid JSON: {e}\nRaw response:\n{response}"
            self.state = RunnerState.ERROR
            return
        
        valid, error = self._validate_response(data)
        if not valid:
            self.error = error
            self.state = RunnerState.ERROR
            return
        
        self.result = data
        self.error = None
        self.state = RunnerState.SUCCESS
    
    def _validate_response(self, data: Any) -> Tuple[bool, Optional[str]]:
        try:
            if not isinstance(data, dict):
                return False, "Response must be a JSON object"
            if "action_mappings" not in data:
                return False, "Missing 'action_mappings' key"
            if not isinstance(data["action_mappings"], list):
                return False, "'action_mappings' must be a list"
            
            for i, mapping in enumerate(data["action_mappings"]):
                if not isinstance(mapping, dict):
                    return False, f"action_mappings[{i}] must be an object"
                if "role_id" not in mapping or "prompt_key" not in mapping or "action_options" not in mapping:
                    return False, f"action_mappings[{i}] missing required keys"
                if not isinstance(mapping["action_options"], list):
                    return False, f"action_mappings[{i}].action_options must be a list"
                
                for j, action in enumerate(mapping["action_options"]):
                    if not isinstance(action, dict):
                        return False, f"action_mappings[{i}].action_options[{j}] must be an object"
                    if "description" not in action or "json_template" not in action:
                        return False, f"action_mappings[{i}].action_options[{j}] missing required keys"
        except Exception as e:
            return False, f"Validation error: {e}"
        return True, None
    
    def wait_for_llm(self, poll_interval=0.5):
        count = 0
        while self.state == RunnerState.WAITING_RESPONSE:
            if count % 10 == 0:
                print(f"{GRAY}Waiting for LLM response... elapsed: {count * poll_interval:.1f}s{RESET}")
            count += 1
            time.sleep(poll_interval)
    
    def _create_retry_prompt(self, human_feedback: Optional[str] = None) -> str:
        base = self._render_prompt()
        prev = self.last_llm_response or ""
        err = self.error or ""
        parts = ["You are retrying the ACTION SCHEMA INTERPRETATION stage.", base]
        if prev:
            parts.append(f"\n--- PREVIOUS LLM RESPONSE ---\n{prev}")
        if err:
            parts.append(f"\n--- ERROR MESSAGE ---\n{err}")
        if human_feedback:
            parts.append(f"\n--- HUMAN FEEDBACK ---\n{human_feedback}")
        return "\n".join(parts)
    
    def retry_stage(self, human_feedback: Optional[str] = None):
        prompt = self._create_retry_prompt(human_feedback)
        self.run_stage(feedback=prompt)
    
    def apply_actions_to_yaml(self, output_path: Optional[str] = None) -> str:
        """Apply the action mappings to the YAML template to produce final YAML"""
        assert self.result, "No action mappings result available"
        assert self.yaml_template_path, "No YAML template selected"
        
        # Read the YAML template as a Jinja2 template
        with open(self.yaml_template_path, "r") as f:
            yaml_template_content = f.read()
        
        # Parse it to extract the config structure
        # We need to inject action_options into the config before rendering
        # This is tricky because we're dealing with a pre-rendered template
        # Instead, we'll re-render using our original config data
        
        # For simplicity, we'll modify the YAML template content directly
        # by injecting action options into the template context
        
        # Load the original parsed JSON to rebuild the config
        from interpret_in_stages import StagedYamlInterpreter
        interpreter = StagedYamlInterpreter()
        interpreter.select_parsed_json(self.parsed_json_path)
        
        # We need to re-run all stages OR load the saved stage results
        # For now, let's assume we have a simpler approach:
        # Parse the YAML template and inject actions
        
        print(f"{YELLOW}Note: Final YAML generation with actions needs config reconstruction.{RESET}")
        print(f"{YELLOW}Saving action mappings to separate file for manual integration.{RESET}")
        
        os.makedirs(self.output_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(self.yaml_template_path))[0]
        actions_path = os.path.join(self.output_dir, f"{base}_actions.json")
        
        with open(actions_path, "w") as f:
            json.dump(self.result, f, indent=2)
        
        print(f"{GREEN}Action mappings saved to: {actions_path}{RESET}")
        return actions_path




def main():
    import sys
    
    skip_interaction = '--auto' in sys.argv
    
    print(f"\n{BLUE}=== Action Schema Interpreter (Stage 3) ==={RESET}\n")
    
    interpreter = ActionSchemaInterpreter()
    
    # Parse arguments
    if '--auto' in sys.argv:
        auto_idx = sys.argv.index('--auto')
        if len(sys.argv) < auto_idx + 3:
            print(f"{RED}Error: --auto requires <yaml_template> <schema>{RESET}")
            print(f"Usage: python action_schema_interpret.py --auto <yaml_template> <schema>")
            return 1
        yaml_path = sys.argv[auto_idx + 1]
        schema_path = sys.argv[auto_idx + 2]
    else:
        # Interactive mode
        yaml_path = input("Enter path to YAML template: ").strip()
        schema_path = input("Enter path to JSON schema: ").strip()
    
    # Load files
    try:
        interpreter.load_files(yaml_path, schema_path)
    except FileNotFoundError as e:
        print(f"{RED}Error: {e}{RESET}")
        return 1
    
    if len(interpreter.placeholders_found) == 0:
        print(f"{YELLOW}No placeholders found in YAML. Nothing to do.{RESET}")
        return 0
    
    # Process all placeholders
    interpreter.process_all_placeholders(skip_interaction=skip_interaction)
    
    # Generate final YAML
    output_path = interpreter.generate_final_yaml()
    
    print(f"\n{GREEN}✓ Action schema interpretation complete!{RESET}")
    print(f"{GREEN}✓ Final YAML ready to use: {output_path}{RESET}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


