# Mock Dify MCP Server for testing
# Provides a simple FastAPI server that mimics the Dify knowledge search endpoint.
# It returns a fixed dummy response regardless of the input query.

from fastapi import FastAPI, Request
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Mock Dify MCP Server")

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    # Additional fields can be added to match real Dify payload if needed.

@app.post("/search")
async def search(req: SearchRequest):
    # Dummy response structure resembling Dify's API.
    dummy_results = [
        {
            "id": f"doc-{i}",
            "title": f"Dummy Document {i}",
            "content": f"This is a mock content for document {i} related to query '{req.query}'.",
            "score": 1.0 - i * 0.1,
        }
        for i in range(1, req.top_k + 1)
    ]
    return {"query": req.query, "results": dummy_results}

if __name__ == "__main__":
    # Run on localhost port 8001 for testing.
    uvicorn.run(app, host="0.0.0.0", port=8001)
