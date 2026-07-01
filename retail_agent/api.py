from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Any

from bson.decimal128 import Decimal128
from bson.objectid import ObjectId
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agent import RetailAgent
from .auth import (
    AuthError,
    AuthService,
    FeatureService,
    SESSION_TTL,
    public_user,
)
from .store_factory import create_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class ChatResponse(BaseModel):
    reply: str


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    account_type: str


class AuthResponse(BaseModel):
    user: UserResponse


class FeaturesResponse(BaseModel):
    authentication: bool


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

# One agent instance preserves conversation context while MongoDB provides
# shared business state across processes and serverless instances.
agent = RetailAgent(create_store(PROJECT_ROOT / "data"), provider=os.getenv("LLM_PROVIDER"))
agent_lock = Lock()
agents_by_user: dict[str, RetailAgent] = {}
auth_service = (
    AuthService(agent.store.database)
    if hasattr(agent.store, "database")
    else None
)
feature_service = (
    FeatureService(agent.store.database)
    if hasattr(agent.store, "database")
    else None
)
SESSION_COOKIE = "retail_session"
GUEST_COOKIE = "retail_guest"
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
ANONYMOUS_USER = {
    "_id": "anonymous",
    "name": "Workspace Guest",
    "email": "guest@local",
    "role": "staff",
    "account_type": "guest",
}


def authentication_enabled() -> bool:
    return feature_service.authentication_enabled() if feature_service else False


def require_auth_service() -> AuthService:
    if auth_service is None:
        raise HTTPException(
            status_code=503,
            detail="Authentication requires MongoDB configuration.",
        )
    return auth_service


def current_user(request: Request) -> dict[str, Any]:
    if not authentication_enabled():
        return ANONYMOUS_USER
    service = require_auth_service()
    user = service.user_for_session(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def current_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role", "staff") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def cookie_secure(request: Request) -> bool:
    configured = os.getenv("AUTH_COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return request.url.scheme == "https" or bool(os.getenv("VERCEL"))


def set_session_cookie(
    response: Response, request: Request, token: str
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        path="/",
    )


def set_guest_cookie(
    response: Response, request: Request, browser_key: str
) -> None:
    response.set_cookie(
        key=GUEST_COOKIE,
        value=browser_key,
        max_age=GUEST_COOKIE_MAX_AGE,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        path="/",
    )


def user_agent(user: dict[str, Any]) -> RetailAgent:
    user_id = str(user["_id"])
    existing = agents_by_user.get(user_id)
    if existing is None:
        existing = RetailAgent(agent.store, provider=agent.provider)
        agents_by_user[user_id] = existing
    return existing


def require_authentication_feature() -> None:
    if not authentication_enabled():
        raise HTTPException(status_code=404, detail="Authentication is disabled.")


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, ObjectId):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "provider": agent.provider,
        "storage": agent.store.backend,
    }


@app.get("/api/features", response_model=FeaturesResponse)
def features() -> FeaturesResponse:
    return FeaturesResponse(authentication=authentication_enabled())


@app.post("/api/auth/signup", response_model=AuthResponse, status_code=201)
def signup(payload: SignupRequest, request: Request, response: Response) -> AuthResponse:
    require_authentication_feature()
    service = require_auth_service()
    try:
        user = service.create_user(payload.name, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    token = service.create_session(user["_id"])
    set_session_cookie(response, request, token)
    return AuthResponse(user=UserResponse(**public_user(user)))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
    require_authentication_feature()
    service = require_auth_service()
    user = service.authenticate(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = service.create_session(user["_id"])
    set_session_cookie(response, request, token)
    return AuthResponse(user=UserResponse(**public_user(user)))


@app.post("/api/auth/guest", response_model=AuthResponse)
def guest(request: Request, response: Response) -> AuthResponse:
    require_authentication_feature()
    service = require_auth_service()
    user, browser_key = service.get_or_create_guest(
        request.cookies.get(GUEST_COOKIE)
    )
    token = service.create_session(user["_id"])
    set_session_cookie(response, request, token)
    set_guest_cookie(response, request, browser_key)
    return AuthResponse(user=UserResponse(**public_user(user)))


@app.get("/api/auth/me", response_model=AuthResponse)
def me(user: dict[str, Any] = Depends(current_user)) -> AuthResponse:
    return AuthResponse(user=UserResponse(**public_user(user)))


@app.post("/api/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: dict[str, Any] = Depends(current_user),
) -> Response:
    service = require_auth_service()
    service.delete_session(request.cookies.get(SESSION_COOKIE))
    with agent_lock:
        agents_by_user.pop(str(user["_id"]), None)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=cookie_secure(request),
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/admin/{resource}")
def admin_resource(
    resource: str,
    _: dict[str, Any] = Depends(current_admin),
) -> list[dict[str, Any]]:
    if not hasattr(agent.store, "database"):
        raise HTTPException(status_code=503, detail="MongoDB is required.")
    database = agent.store.database

    if resource == "orders":
        lines_by_order: dict[str, list[dict[str, Any]]] = {}
        for line in database.order_lines.find({}, {"_id": 0}).sort(
            [("order_id", -1), ("line_no", 1)]
        ):
            lines_by_order.setdefault(line["order_id"], []).append(line)
        rows = []
        for order in database.orders.find({}, {"_id": 0}).sort("order_date", -1):
            order["lines"] = lines_by_order.get(order["order_id"], [])
            rows.append(order)
        return json_value(rows)

    if resource == "suppliers":
        catalog_by_supplier: dict[str, list[dict[str, Any]]] = {}
        for item in database.supplier_catalog.find({}, {"_id": 0}).sort(
            [("supplier_id", 1), ("product_id", 1)]
        ):
            catalog_by_supplier.setdefault(item["supplier_id"], []).append(item)
        rows = []
        for supplier in database.suppliers.find({}, {"_id": 0}).sort(
            "supplier_name", 1
        ):
            supplier["catalog"] = catalog_by_supplier.get(
                supplier["supplier_id"], []
            )
            rows.append(supplier)
        return json_value(rows)

    collections = {
        "customers": ("customers", "name"),
        "returns": ("returns", "return_date"),
        "purchase-orders": ("purchase_orders", "order_date"),
    }
    collection_config = collections.get(resource)
    if collection_config is None:
        raise HTTPException(status_code=404, detail="Unknown admin resource.")
    collection_name, sort_field = collection_config
    direction = 1 if resource == "customers" else -1
    rows = list(
        database[collection_name]
        .find({}, {"_id": 0})
        .sort(sort_field, direction)
        .limit(500)
    )
    return json_value(rows)


@app.get("/api/products", response_model=list[ProductResponse])
def products(_: dict[str, Any] = Depends(current_user)) -> list[ProductResponse]:
    with agent_lock:
        refresh = getattr(agent.store, "refresh", None)
        if refresh:
            refresh()
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
def chat(
    request: ChatRequest,
    user: dict[str, Any] = Depends(current_user),
) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    try:
        # RetailAgent mutates conversation and store state, so calls must be serialized.
        with agent_lock:
            reply = user_agent(user).handle(message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="The retail agent could not process the request.") from exc

    return ChatResponse(reply=reply)
