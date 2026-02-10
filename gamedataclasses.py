"""
Parsing Data Models

This module defines simple dataclasses used during Stage 1 (parse_in_stages.py) to store
intermediate parsing results. These models are internal representations that get serialized
to JSON at the end of the parsing pipeline.

The models defined here are conceptually distinct from the YAML configuration models in
yaml_dataclasses.py. Parsing models focus on capturing the raw structure extracted from
natural language, while YAML models enforce the strict schema required by EconAgents.

Classes:
    PhaseRoleTasks: Tasks mapped to roles for a specific phase
    PayoffConsequence: Payoff rule for a role's choice
    PhaseRoleMatrix: Complete phase-role-payoff mapping

These classes are primarily used for type safety during parsing and are not exposed
in the final API.

See Also:
    parse_in_stages.py: Uses these models internally
    yaml_dataclasses.py: Final YAML configuration models
    DATA_MODELS.md: Complete data model documentation
"""

from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class PhaseRoleTasks:
    """Tasks mapped to each role for a single phase."""
    phase: str
    phase_number: int
    actionable: bool
    role_tasks: Dict[str, List[str]] = field(default_factory=dict)

@dataclass
class PayoffConsequence:
    """Payoff consequence for a role's choice in a phase."""
    phase: str
    role: str
    choice: str
    payoff: str

@dataclass
class PhaseRoleMatrix:
    """Complete matrix: one entry per phase, plus payoff consequences."""
    phases: List[PhaseRoleTasks] = field(default_factory=list)
    payoff_consequences: List[PayoffConsequence] = field(default_factory=list)
