"""FastAPI entry point for Phase 1.
Provides two OpenAI‑compatible endpoints:
* ``GET /v1/models`` – returns available agents.
* ``POST /v1/chat/completions`` – runs the specified agent and returns the answer.
The implementation is deliberately minimal, focusing on the prototype
behaviour required for the test.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from core.engine.strands_factory import StrandsFactory
from core.engine.agent_loader import load_agent
from pathlib import Path
import yaml

app = FastAPI(title="AI Agent Platform – Phase 1")

# ---------- Models ----------
class ModelInfo(BaseModel):
    id: str = Field(..., description="モデルID (エージェントID)")
    object: str = "model"
    owned_by: str = "organization"

class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]

class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str  # エージェントID
    messages: List[Message]
    stream: bool = False

class ChoiceDelta(BaseModel):
    role: str = "assistant"
    content: str

class Choice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str = "stop"

class ChatCompletionResponse(BaseModel):
    id: str = "chatcmpl-1"
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]

# ---------- Helpers ----------
def list_agents() -> List[ModelInfo]:
    agents_dir = Path(__file__).resolve().parents[1] / "agents"
    models = []
    for entry in agents_dir.iterdir():
        if not entry.is_dir():
            continue
        config_path = entry / "config.yaml"
        if not config_path.is_file():
            continue
        try:
            cfg = load_agent(entry.name)
        except Exception:
            continue
        if cfg["config"].agent.enabled:
            models.append(ModelInfo(id=cfg["config"].agent.id))
    return models

factory = StrandsFactory()

# ---------- Endpoints ----------
@app.get("/v1/models", response_model=ModelsResponse)
async def get_models():
    return ModelsResponse(data=list_agents())

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest):
    # Find the agent directory by model ID safely (skip directories missing required files)
    agents_dir = Path(__file__).resolve().parents[1] / "agents"
    agent_dir_name: str | None = None
    for entry in agents_dir.iterdir():
        if not entry.is_dir():
            continue
        cfg_path = entry / "config.yaml"
        if not cfg_path.is_file():
            continue
        try:
            raw_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            agent_id_val = raw_cfg.get('agent', {}).get('id')
            if agent_id_val == req.model:
                agent_dir_name = entry.name
                break
        except Exception:
            continue
    if agent_dir_name is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Extract metadata for memory scoping
    user_id = req.metadata.get("user_id", "default_user") if hasattr(req, "metadata") else "default_user"
    chat_id = req.metadata.get("chat_id", "default_chat") if hasattr(req, "metadata") else "default_chat"

    # Convert Pydantic Message list to plain dicts for WorkflowRunner / StrandsFactory
    messages_dicts = [{"role": m.role, "content": m.content} for m in req.messages]

    # Extract last user message as query
    user_messages = [m for m in req.messages if m.role.lower() == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message provided")
    query = user_messages[-1].content

    # Run agent using WorkflowRunner for full workflow handling
    from .engine.workflow_runner import WorkflowRunner
    runner = WorkflowRunner()
    if req.stream:
        from fastapi.responses import StreamingResponse
        import json, asyncio
        async def event_generator():
            yield f"data: {{\"role\": \"assistant\", \"content\": \"[開始]\"}}\n\n"
            await asyncio.sleep(0.1)
            answer = runner.run(
                agent_dir_name, query,
                messages=messages_dicts, user_id=user_id, chat_id=chat_id,
            )
            for line in answer.split('\n'):
                chunk = json.dumps({"role": "assistant", "content": line}, ensure_ascii=False)
                yield f"data: {chunk}\n\n"
                await asyncio.sleep(0.05)
            yield "data: [DONE]\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    else:
        try:
            answer = runner.run(
                agent_dir_name, query,
                messages=messages_dicts, user_id=user_id, chat_id=chat_id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Agent execution error: {e}")
        import time as _time
        resp = ChatCompletionResponse(
            created=int(_time.time()),
            model=req.model,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=answer),
                    finish_reason="stop",
                )
            ],
        )
        return resp
