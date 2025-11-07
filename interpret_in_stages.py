import os
import json
import threading
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
from econagents.llm.openai import ChatOpenAI
from yaml_dataclasses import (
    ExperimentConfig,
    PromptPartial,
    AgentRoleConfig,
    AgentMappingConfig,
    RolePromptEntry,
    StateConfig,
    make_state_field_from_json,
    EventHandler,
    ManagerConfig,
    RunnerConfig,
)

# Color helpers
BLUE = "\033[1;34m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
GRAY = "\033[1;90m"
RESET = "\033[0m"

class Stage(Enum):
    META = "meta"
    ROLES = "roles"
    ROLE_PROMPTS_REFINEMENT = "role_prompts_refinement"
    STATE = "state"
    MANAGER = "manager"
    RUNNER = "runner"
    AGENTS = "agents"

class RunnerState(Enum):
    IDLE = auto()
    WAITING_RESPONSE = auto()
    PROCESSING_RESPONSE = auto()
    READY_FOR_FEEDBACK = auto()
    SUCCESS = auto()
    ERROR = auto()
    WRITING_FILE = auto()

class StagedYamlInterpreter:
    def __init__(self,
                 parsed_json_path: Optional[str] = None,
                 interpret_prompts_dir: str = "prompts/interpret",
                 template_dir: str = "templates",
                 output_dir: str = "output/interpret_out"):
        load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.llm = ChatOpenAI(api_key=self.api_key)
        self.interpret_prompts_dir = interpret_prompts_dir
        self.template_dir = template_dir
        self.output_dir = output_dir
        self.state = RunnerState.IDLE
        self.current_stage_idx = 0
        self.stages: List[Stage] = [
            Stage.META,
            Stage.ROLES,
            Stage.STATE,
            Stage.MANAGER,
            Stage.RUNNER,
            Stage.AGENTS,
            Stage.ROLE_PROMPTS_REFINEMENT,
        ]
        self.stage_results: Dict[Stage, Any] = {s: None for s in self.stages}
        self.stage_errors: Dict[Stage, Optional[str]] = {s: None for s in self.stages}
        self.lock = threading.Lock()
        self.selected_parsed_json_path = parsed_json_path
        self.last_prompt = None
        self.last_llm_response = None
        self.env = Environment(loader=FileSystemLoader(self.template_dir))
        self.max_auto_retries = 2

    def list_parsed_specs(self) -> List[str]:
        candidates = []
        for d in ["output/parse_out"]:
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".json"):
                        candidates.append(os.path.join(d, f))
        return sorted(candidates)

    def select_parsed_json(self, path: str):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        with open(path, "r") as f:
            # Validate JSON
            _ = json.load(f)
        with self.lock:
            self.selected_parsed_json_path = path
            self.state = RunnerState.IDLE
            self.current_stage_idx = 0
            self.stage_results = {s: None for s in self.stages}
            self.stage_errors = {s: None for s in self.stages}

    def _read_parsed_json(self) -> Dict[str, Any]:
        assert self.selected_parsed_json_path, "No parsed JSON selected"
        with open(self.selected_parsed_json_path, "r") as f:
            return json.load(f)

    def _get_prompt_template(self, stage: Stage) -> str:
        fname = {
            Stage.META: "meta_prompt.jinja2",
            Stage.ROLES: "roles_prompt.jinja2",
            Stage.ROLE_PROMPTS_REFINEMENT: "role_prompts_prompt.jinja2",
            Stage.STATE: "state_prompt.jinja2",
            Stage.MANAGER: "manager_prompt.jinja2",
            Stage.RUNNER: "runner_prompt.jinja2",
            Stage.AGENTS: "agents_prompt.jinja2",
        }[stage]
        path = os.path.join(self.interpret_prompts_dir, fname)
        with open(path, "r") as f:
            return f.read()

    def _render_prompt(self, stage: Stage) -> str:
        parsed_json = self._read_parsed_json()
        header = (
            "You are an assistant that converts condensed JSON game specs into YAML configuration parts.\n"
            "Extract configuration ONLY from the provided JSON. Do not infer beyond direct textual or structural evidence.\n"
            "If any field cannot be determined solely from this JSON, return the literal string 'cannot infer' for that field (or [] for list fields).\n"
            f"You are in stage: {stage.value}. Return STRICT JSON only."
        )
        template_str = self._get_prompt_template(stage)
        # naive string format using Jinja2-like placeholders already present
        prompt = template_str.replace("{{ header }}", header)
        prompt = prompt.replace("{{ parsed_json }}", json.dumps(parsed_json, indent=2))
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
        with self.lock:
            stage = self.stages[self.current_stage_idx]
            self.state = RunnerState.WAITING_RESPONSE
            prompt = feedback if feedback else self._render_prompt(stage)
            thread = threading.Thread(target=self._run_stage_thread, args=(stage, prompt))
            thread.start()
            return stage.value

    def _run_stage_thread(self, stage: Stage, prompt: str):
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
            self._process_stage_response(stage, response)
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            self.stage_errors[stage] = str(e)
            self.state = RunnerState.ERROR
        finally:
            if loop is not None and not loop.is_closed():
                loop.close()

    def _process_stage_response(self, stage: Stage, response: str):
        try:
            data = json.loads(response)
        except Exception as e:
            self.stage_errors[stage] = f"Invalid JSON: {e}\nRaw response:\n{response}"
            self.state = RunnerState.ERROR
            return
        valid, error = self._validate_stage(stage, data)
        if not valid:
            self.stage_errors[stage] = error
            self.state = RunnerState.ERROR
            return
        self.stage_results[stage] = data
        self.stage_errors[stage] = None
        self.state = RunnerState.SUCCESS

    def _validate_stage(self, stage: Stage, data: Any) -> Tuple[bool, Optional[str]]:
        try:
            if stage == Stage.META:
                if not set(data.keys()) == {"name", "description", "prompt_partials"}:
                    return False, "META: keys must be exactly name, description, prompt_partials"
                if not isinstance(data["prompt_partials"], list):
                    return False, "META: prompt_partials must be a list"
                for i, p in enumerate(data["prompt_partials"]):
                    if not (isinstance(p, dict) and "name" in p and "content" in p):
                        return False, f"META: prompt_partials[{i}] must have name, content"
            elif stage == Stage.ROLES:
                if set(data.keys()) != {"agent_roles"}: return False, "ROLES: missing agent_roles"
                if not isinstance(data["agent_roles"], list): return False, "ROLES: agent_roles must be list"
                for i, r in enumerate(data["agent_roles"]):
                    required = {"role_id", "name", "llm_type", "llm_params", "prompts", "task_phases", "task_phases_excluded"}
                    if set(r.keys()) != required:
                        return False, f"ROLES[{i}]: keys must be {sorted(required)}"
                    if not isinstance(r["prompts"], list): return False, f"ROLES[{i}]: prompts must be list"
                    keys = set()
                    for j, pe in enumerate(r["prompts"]):
                        if not (isinstance(pe, dict) and "key" in pe and "content" in pe):
                            return False, f"ROLES[{i}].prompts[{j}] invalid"
                        if pe["key"] in keys:
                            return False, f"ROLES[{i}].prompts duplicate key {pe['key']}"
                        keys.add(pe["key"])
            elif stage == Stage.ROLE_PROMPTS_REFINEMENT:
                if set(data.keys()) != {"agent_roles_update"}: return False, "REFINE: missing agent_roles_update"
                if not isinstance(data["agent_roles_update"], list): return False, "REFINE: must be list"
                for upd in data["agent_roles_update"]:
                    if not ("role_id" in upd and isinstance(upd.get("prompts"), list)):
                        return False, "REFINE: each update must have role_id and prompts list"
            elif stage == Stage.STATE:
                if set(data.keys()) != {"state"}: return False, "STATE: missing state"
                st = data["state"]
                for section in ["meta_information", "private_information", "public_information"]:
                    if section not in st or not isinstance(st[section], list):
                        return False, f"STATE: {section} must be a list"
            elif stage == Stage.MANAGER:
                if set(data.keys()) != {"manager"}: return False, "MANAGER: missing manager"
                m = data["manager"]
                if "event_handlers" in m and not isinstance(m["event_handlers"], list):
                    return False, "MANAGER: event_handlers must be list"
            elif stage == Stage.RUNNER:
                if set(data.keys()) != {"runner"}: return False, "RUNNER: missing runner"
            elif stage == Stage.AGENTS:
                if set(data.keys()) != {"agents"}: return False, "AGENTS: missing agents"
                if not isinstance(data["agents"], list): return False, "AGENTS: agents must be list"
                for a in data["agents"]:
                    if not ("id" in a and "role_id" in a):
                        return False, "AGENTS: each needs id and role_id"
        except Exception as e:
            return False, f"Validation error: {e}"
        return True, None

    def wait_for_llm(self, poll_interval=0.5):
        count = 0
        while self.state == RunnerState.WAITING_RESPONSE:
            if count % 10 == 0:
                print(f"Waiting for LLM response... (state: {self.state.name}), elapsed: {count * poll_interval:.1f}s")
            count += 1
            time.sleep(poll_interval)

    def next_stage(self) -> Optional[str]:
        with self.lock:
            if self.current_stage_idx < len(self.stages) - 1:
                self.current_stage_idx += 1
                self.state = RunnerState.IDLE
                return self.stages[self.current_stage_idx].value
            else:
                self.state = RunnerState.SUCCESS
                return None

    def _create_retry_prompt(self, human_feedback: Optional[str] = None) -> str:
        stage = self.stages[self.current_stage_idx]
        base = self._render_prompt(stage)
        prev = self.last_llm_response or ""
        err = self.stage_errors.get(stage) or ""
        parts = [f"You are retrying stage: {stage.value}.", base]
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

    def _coerce_unknown(self, v: Any) -> Any:
        # Converts 'cannot infer' -> None; leaves lists as-is
        if isinstance(v, str) and v.strip().lower() == "cannot infer":
            return None
        return v

    def _merge_into_config(self) -> ExperimentConfig:
        # Build ExperimentConfig from stage_results with coercion
        meta = self.stage_results.get(Stage.META) or {}
        roles = self.stage_results.get(Stage.ROLES) or {}
        state = self.stage_results.get(Stage.STATE) or {"state": {"meta_information": [], "private_information": [], "public_information": []}}
        manager = self.stage_results.get(Stage.MANAGER) or {"manager": {}}
        runner = self.stage_results.get(Stage.RUNNER) or {"runner": {}}
        agents = self.stage_results.get(Stage.AGENTS) or {"agents": []}
        # Coerce
        name = self._coerce_unknown(meta.get("name"))
        desc = self._coerce_unknown(meta.get("description")) or ""
        partials = [PromptPartial(name=p.get("name", ""), content=self._coerce_unknown(p.get("content", "")) or "") for p in (meta.get("prompt_partials") or [])]
        cfg = ExperimentConfig(name=name, description=desc, prompt_partials=partials)
        # Roles
        for r in (roles.get("agent_roles") or []):
            prompts = [RolePromptEntry(key=pe.get("key", ""), content=self._coerce_unknown(pe.get("content", "")) or "") for pe in (r.get("prompts") or [])]
            arc = AgentRoleConfig(
                role_id=self._coerce_unknown(r.get("role_id")),
                name=self._coerce_unknown(r.get("name")),
                llm_type=self._coerce_unknown(r.get("llm_type")),
                llm_params=r.get("llm_params") or {},
                prompts=prompts,
                task_phases=[int(x) for x in (r.get("task_phases") or []) if isinstance(x, int) or (isinstance(x, str) and x.isdigit())],
                task_phases_excluded=[int(x) for x in (r.get("task_phases_excluded") or []) if isinstance(x, int) or (isinstance(x, str) and x.isdigit())],
            )
            cfg.agent_roles.append(arc)
        # Agents
        for a in (agents.get("agents") or []):
            cfg.agents.append(AgentMappingConfig(id=self._coerce_unknown(a.get("id")), role_id=self._coerce_unknown(a.get("role_id"))))
        # State
        st = state.get("state") or {}
        cfg.state = StateConfig(
            meta_information=[make_state_field_from_json({k: self._coerce_unknown(v) for k, v in f.items()}) for f in (st.get("meta_information") or [])],
            private_information=[make_state_field_from_json({k: self._coerce_unknown(v) for k, v in f.items()}) for f in (st.get("private_information") or [])],
            public_information=[make_state_field_from_json({k: self._coerce_unknown(v) for k, v in f.items()}) for f in (st.get("public_information") or [])],
        )
        # Manager
        m = manager.get("manager") or {}
        cfg.manager = ManagerConfig(
            type=self._coerce_unknown(m.get("type")) or "TurnBasedPhaseManager",
            event_handlers=[EventHandler(event=eh.get("event", ""), custom_code=self._coerce_unknown(eh.get("custom_code")), custom_module=self._coerce_unknown(eh.get("custom_module")), custom_function=self._coerce_unknown(eh.get("custom_function"))) for eh in (m.get("event_handlers") or [])]
        )
        # Runner
        r = runner.get("runner") or {}
        cfg.runner = RunnerConfig(
            type=self._coerce_unknown(r.get("type")) or "GameRunner",
            protocol=self._coerce_unknown(r.get("protocol")) or "ws",
            hostname=self._coerce_unknown(r.get("hostname")) or "localhost",
            path=self._coerce_unknown(r.get("path")) or "wss",
            port=r.get("port") if isinstance(r.get("port"), int) else 0,
            game_id=r.get("game_id") if isinstance(r.get("game_id"), int) else 0,
            logs_dir=self._coerce_unknown(r.get("logs_dir")) or "logs",
            log_level=self._coerce_unknown(r.get("log_level")) or "INFO",
            prompts_dir=self._coerce_unknown(r.get("prompts_dir")) or "prompts",
            phase_transition_event=self._coerce_unknown(r.get("phase_transition_event")) or "phase-transition",
            phase_identifier_key=self._coerce_unknown(r.get("phase_identifier_key")) or "phase",
            observability_provider=self._coerce_unknown(r.get("observability_provider")),
            continuous_phases=[int(x) for x in (r.get("continuous_phases") or []) if isinstance(x, int) or (isinstance(x, str) and x.isdigit())],
            min_action_delay=r.get("min_action_delay") if isinstance(r.get("min_action_delay"), int) else 5,
            max_action_delay=r.get("max_action_delay") if isinstance(r.get("max_action_delay"), int) else 10,
        )
        # Apply refinement prompts if present
        refine = self.stage_results.get(Stage.ROLE_PROMPTS_REFINEMENT) or {"agent_roles_update": []}
        updates_by_id = {u.get("role_id"): u.get("prompts") or [] for u in (refine.get("agent_roles_update") or [])}
        if updates_by_id:
            for role in cfg.agent_roles:
                if role.role_id in updates_by_id and updates_by_id[role.role_id]:
                    role.prompts = [RolePromptEntry(key=pe.get("key", ""), content=self._coerce_unknown(pe.get("content", "")) or "") for pe in updates_by_id[role.role_id]]
        return cfg

    def _inject_placeholders_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure lists used in for-loops have at least one placeholder element when empty
        ctx = json.loads(json.dumps(ctx))  # deep copy
        if isinstance(ctx.get("prompt_partials"), list) and len(ctx["prompt_partials"]) == 0:
            ctx["prompt_partials"].append({"name": None, "content": None})
        if isinstance(ctx.get("agent_roles"), list) and len(ctx["agent_roles"]) == 0:
            ctx["agent_roles"].append({
                "role_id": None,
                "name": None,
                "llm_type": None,
                "llm_params": {},
                "prompts": [{"key": "system", "value": None}],
                "task_phases": [],
                "task_phases_excluded": []
            })
        # Ensure each role has at least one prompt entry for visibility
        for role in ctx.get("agent_roles", []):
            if isinstance(role.get("prompts"), list) and len(role["prompts"]) == 0:
                role["prompts"].append({"key": "system", "value": None})
        if isinstance(ctx.get("agents"), list) and len(ctx["agents"]) == 0:
            ctx["agents"].append({"id": None, "role_id": None})
        # State sections
        state = ctx.get("state", {})
        for section in ["meta_information", "private_information", "public_information"]:
            items = state.get(section)
            if isinstance(items, list) and len(items) == 0:
                state[section].append({
                    "name": None,
                    "type": None,
                    "default": None,
                    "default_factory": None,
                    "event_key": None,
                    "exclude_from_mapping": None,
                    "optional": None,
                    # put explicit placeholder item to avoid default('[]') masking
                    "events": ["(UPDATE MANUALLY)"],
                    "exclude_events": ["(UPDATE MANUALLY)"]
                })
        ctx["state"] = state
        return ctx

    def _mark_unknowns_for_yaml(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Replace None and "cannot infer" scalars with "(UPDATE MANUALLY)"; keep lists/dicts intact.
        def transform(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: transform(v) for k, v in value.items()}
            if isinstance(value, list):
                return [transform(v) for v in value]
            if value is None:
                return "(UPDATE MANUALLY)"
            if isinstance(value, str) and value.strip().lower() == "cannot infer":
                return "(UPDATE MANUALLY)"
            return value
        return transform(ctx)

    def render_yaml(self, cfg: ExperimentConfig, output_basename: Optional[str] = None, final: bool = False) -> str:
        """
        Render YAML from config. If final=False, outputs intermediate template for action schema stage.
        If final=True, outputs final YAML (used after action schema integration).
        """
        os.makedirs(self.output_dir, exist_ok=True)
        template = self.env.get_template("econagents_template.yaml.jinja2")
        ctx = cfg.to_template_context()
        ctx = self._inject_placeholders_context(ctx)
        ctx_marked = self._mark_unknowns_for_yaml(ctx)
        yaml_text = template.render(**ctx_marked)
        
        base = output_basename or (os.path.splitext(os.path.basename(self.selected_parsed_json_path))[0] if self.selected_parsed_json_path else "experiment")
        
        if final:
            out_path = os.path.join(self.output_dir, f"{base}.yaml")
        else:
            # Output intermediate template for stage 3
            out_path = os.path.join(self.output_dir, f"{base}_partial.yaml")
            
        with open(out_path, "w") as f:
            f.write(yaml_text)
        return out_path
    
    def save_stage_results(self, output_basename: Optional[str] = None) -> str:
        """Save all stage results to JSON for later integration with actions"""
        os.makedirs(self.output_dir, exist_ok=True)
        base = output_basename or (os.path.splitext(os.path.basename(self.selected_parsed_json_path))[0] if self.selected_parsed_json_path else "experiment")
        out_path = os.path.join(self.output_dir, f"{base}_stage_results.json")
        
        # Convert stage_results to serializable format
        results = {}
        for stage, data in self.stage_results.items():
            if data is not None:
                results[stage.value] = data
        
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        
        return out_path


def main():

    skip_human_interaction = False
    import sys
    if '--auto' in sys.argv:
        skip_human_interaction = True
        auto_index = sys.argv.index('--auto') + 1
        if auto_index >= len(sys.argv):
            print("Error: --auto flag requires a path to a game spec json file.")
            return
        auto_game_spec_path = sys.argv[auto_index]
    
    
    print(f"\n{BLUE}=== EconAgents YAML Interpreter (Staged) ==={RESET}\n")
    runner = StagedYamlInterpreter()
    if not skip_human_interaction:
        specs = runner.list_parsed_specs()
        if not specs:
            print(f"{RED}No parsed JSON files found in output/parse_out or examples.{RESET}")
            return
        print("Available parsed JSON files:")
        for idx, spec in enumerate(specs):
            print(f"  [{idx}] {spec}")
        while True:
            try:
                choice = int(input(f"Select a parsed spec [0-{len(specs)-1}]: "))
                if 0 <= choice < len(specs):
                    break
            except Exception:
                pass
            print("Invalid input. Enter a number.")
        runner.select_parsed_json(specs[choice])
        print(f"Selected: {specs[choice]}")
    else:
        runner.select_parsed_json(auto_game_spec_path)
        print(f"Auto mode: Selected parsed JSON: {auto_game_spec_path}")

    # Stage loop
    while True:
        stage = runner.stages[runner.current_stage_idx]
        print(f"{BLUE}\n--- Running stage: {stage.value} ---{RESET}")
        # Show prompt without full JSON body for readability
        preview = runner._render_prompt(stage)
        # Avoid dumping full JSON twice; keep a short preview
        print(f"{GRAY}{preview[:1200]}...{RESET}")

        # Auto retries + human feedback
        auto_retries = 0
        runner.run_stage()
        runner.wait_for_llm()
        while True:
            if runner.state == RunnerState.ERROR:
                print(f"{RED}Error in stage {stage.value}:{RESET} {runner.stage_errors.get(stage)}")
                if auto_retries < runner.max_auto_retries:
                    auto_retries += 1
                    print(f"Auto-retrying ({auto_retries}/{runner.max_auto_retries})...")
                    runner.retry_stage()
                    runner.wait_for_llm()
                    continue
                feedback = input("Provide feedback for retry (or leave empty to skip): ").strip()
                if feedback:
                    runner.retry_stage(feedback)
                    runner.wait_for_llm()
                    continue
                else:
                    print(f"{YELLOW}Skipping stage due to repeated errors. YAML may be incomplete.{RESET}")
                    break
            elif runner.state == RunnerState.SUCCESS:
                result = runner.stage_results[stage]
                print(f"{GREEN}Stage {stage.value} completed successfully.{RESET}")
                print(json.dumps(result, indent=2))
                if not skip_human_interaction:
                    ok = input("Accept this result? (y/n): ").strip().lower() or "y"
                    if ok == "y":
                        break
                    else:
                        fb = input("Enter feedback to retry: ")
                        runner.retry_stage(fb)
                        runner.wait_for_llm()
                        continue
                else:
                    print(f"{GREEN}Auto-accepting result.{RESET}")
                    break
        next_stage = runner.next_stage()
        if not next_stage:
            print(f"{GREEN}All interpretation stages completed.{RESET}")
            break

    cfg = runner._merge_into_config()
    out_path = runner.render_yaml(cfg, final=False)
    print(f"{GREEN}YAML template written to: {out_path}{RESET}")
    print(f"{YELLOW}Next step: Run action_schema_interpret.py with this template and a JSON schema{RESET}")

if __name__ == "__main__":
    main()
