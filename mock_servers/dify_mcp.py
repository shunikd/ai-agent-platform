"""Mock Dify MCP server exposing FastMCP‑style endpoint.
It provides a single tool `dify_search` under the path `/mcp/dify_search`.
The server runs on http://localhost:8001 and is intended for Phase 1 testing.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Mock Dify MCP Server")

class DifySearchRequest(BaseModel):
    query: str
    dataset_ids: list[str] | None = None
    search_method: str = "hybrid"
    top_k: int = 5

@app.post("/mcp/dify_search")
async def dify_search(req: DifySearchRequest):
    # Produce deterministic dummy results.
    dummy_results = [
        {
            "id": f"doc-{i}",
            "title": f"Dummy Document {i}",
            "content": f"This is a mock content for document {i} related to query '{req.query}'.",
            "score": round(1.0 - i * 0.1, 2),
        }
        for i in range(1, req.top_k + 1)
    ]
    return {"tool": "dify_search", "query": req.query, "results": dummy_results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
