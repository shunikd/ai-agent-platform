"""Agent loader for Phase 1.
Loads an agent definition from the ``agents/`` directory.
Supports hot‑reload by checking the modification time of ``config.yaml``
(and ``system_prompt.md``). Validation is performed with Pydantic models.
If validation fails, a Japanese error message is raised as ``ValueError``.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel, ValidationError, Field
import json

# ---------- Pydantic schemas ----------
class AgentInfo(BaseModel):
    id: str = Field(..., description="エージェントID")
    name: str
    description: str
    enabled: bool = True

class AccessControl(BaseModel):
    allowed_roles: list[str]

class ModelsConfig(BaseModel):
    default: str

class Step(BaseModel):
    id: str
    role: str
    prompt_file: str
    tools: list[str] = []

class Workflow(BaseModel):
    type: str
    steps: list[Step] = []

class ToolMCPServer(BaseModel):
    name: str
    allowed_tools: list[str]
    config: Dict[str, Any] = {}

class ToolsConfig(BaseModel):
    mcp_servers: list[ToolMCPServer] = []

class AgentConfig(BaseModel):
    agent: AgentInfo
    access_control: AccessControl
    models: ModelsConfig
    workflow: Workflow
    tools: ToolsConfig

# ---------- Loader implementation ----------
_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "agents"

# cache: {agent_id: (mtime_config, mtime_prompt, AgentConfig, prompt_text)}
_cache: Dict[str, tuple[float, float, AgentConfig, str]] = {}

def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def load_agent(agent_id: str) -> dict:
    """Load an agent definition.

    Returns a dict with keys ``config`` (AgentConfig instance) and ``prompt`` (str).
    Raises ``ValueError`` with a Japanese message if validation fails.
    """
    agent_dir = _AGENTS_ROOT / agent_id
    if not agent_dir.is_dir():
        raise ValueError(f"エージェント '{agent_id}' が見つかりません。")

    config_path = agent_dir / "config.yaml"
    prompt_path = agent_dir / "system_prompt.md"

    if not config_path.is_file():
        raise ValueError(f"エージェント '{agent_id}' の config.yaml が存在しません。")
    if not prompt_path.is_file():
        raise ValueError(f"エージェント '{agent_id}' の system_prompt.md が存在しません。")

    mtime_cfg = config_path.stat().st_mtime
    mtime_prompt = prompt_path.stat().st_mtime

    cached = _cache.get(agent_id)
    if cached and cached[0] == mtime_cfg and cached[1] == mtime_prompt:
        cfg, prompt = cached[2], cached[3]
    else:
        raw_cfg = _load_yaml(config_path)
        try:
            cfg = AgentConfig(**raw_cfg)
        except ValidationError as e:
            # Convert Pydantic errors to Japanese message
            msgs = ", ".join(err["msg"] for err in e.errors())
            raise ValueError(f"設定ファイルのバリデーションエラー: {msgs}")
        prompt = _load_prompt(prompt_path)
        _cache[agent_id] = (mtime_cfg, mtime_prompt, cfg, prompt)

    return {"config": cfg, "prompt": prompt}
