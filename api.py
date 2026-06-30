from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from retail_agent.agent import RetailAgent
from retail_agent.store import RetailStore


PROJECT_ROOT = Path(__file__).resolve().parent


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class ChatResponse(BaseModel):
    reply: str


class ProductResponse(BaseModel):
    sku: str
    product_id: str
    product_name: str
    category: str
    color: str | None
    size: str | None
    retail_price: float
    quantity: int


app = FastAPI(title="Retail Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# One long-lived agent preserves its conversation and in-memory store changes
# for as long as the API process is running.
agent = RetailAgent(RetailStore(PROJECT_ROOT / "data"), provider=os.getenv("LLM_PROVIDER"))
agent_lock = Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": agent.provider}


@app.get("/api/products", response_model=list[ProductResponse])
def products() -> list[ProductResponse]:
    with agent_lock:
        return [
            ProductResponse(
                sku=product.sku,
                product_id=product.product_id,
                product_name=product.product_name,
                category=product.category,
                color=product.color,
                size=product.size,
                retail_price=float(product.retail_price),
                quantity=agent.store.inventory_by_sku[product.sku].on_hand_qty,
            )
            for product in agent.store.products_by_sku.values()
        ]


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    try:
        # RetailAgent mutates conversation and store state, so calls must be serialized.
        with agent_lock:
            reply = agent.handle(message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The retail agent could not process the request.") from exc

    return ChatResponse(reply=reply)
