from __future__ import annotations

import hmac
import logging
import math
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.catalog import Catalog
from app.config import Settings
from app.errors import AppError, AuthenticationError, AuthorizationError, NotFoundError
from app.ingestion import IngestionService
from app.observability import (
    MetricRegistry,
    Tracer,
    configure_logging,
    new_request_id,
    request_id_context,
)
from app.ranking import SearchIndex
from app.schemas import (
    AuthResponse,
    CollectionCreate,
    CollectionItemRequest,
    CollectionOut,
    CollectionPatch,
    IngestionRequest,
    InteractionOut,
    InteractionRequest,
    InteractionType,
    LoginRequest,
    MovieOut,
    ProfileOut,
    ProfilePatch,
    RegisterRequest,
    SearchRequest,
    SearchResponse,
)
from app.security import AuthenticatedUser, csrf_token, verify_token
from app.services import (
    AuthService,
    CollectionService,
    SearchService,
    ServiceContainer,
    interaction_state,
    movie_payload,
)
from app.storage import create_store

logger = logging.getLogger("tamiltrove.api")
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="TamilTrove access token")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
AUTH_CSRF_EXEMPT = {"/api/v1/auth/register", "/api/v1/auth/login"}


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, key: str, group: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        events = self._events[(key, group)]
        cutoff = now - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, math.ceil(events[0] + window_seconds - now))
            return False, 0, retry_after
        events.append(now)
        return True, max(0, limit - len(events)), 0


def error_payload(request_id: str, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": jsonable_encoder(details) if details is not None else None,
            "request_id": request_id,
        }
    }


def container_dependency(request: Request) -> ServiceContainer:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise AppError(
            503,
            "service_unavailable",
            "Required service components are not ready",
            {"reason": getattr(request.app.state, "startup_error", None)},
        )
    return container


Container = Annotated[ServiceContainer, Depends(container_dependency)]


def optional_user_dependency(
    request: Request,
    container: Container,
    authorization: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
) -> AuthenticatedUser | None:
    token_value = (
        authorization.credentials
        if authorization
        else request.cookies.get(container.settings.session_cookie_name)
    )
    if not token_value:
        return None
    payload = verify_token(token_value, container.settings.secret_key)
    if container.store.is_token_revoked(str(payload.get("jti", ""))):
        raise AuthenticationError("The access token has been revoked")
    user = container.store.get_user(str(payload["sub"]))
    if not user:
        raise AuthenticationError("The account no longer exists")
    request.state.auth_payload = payload
    return AuthenticatedUser(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        is_admin=user["email"].casefold() in container.settings.admin_emails,
    )


OptionalUser = Annotated[AuthenticatedUser | None, Depends(optional_user_dependency)]


def required_user_dependency(user: OptionalUser) -> AuthenticatedUser:
    if user is None:
        raise AuthenticationError()
    return user


User = Annotated[AuthenticatedUser, Depends(required_user_dependency)]


def admin_dependency(user: User) -> AuthenticatedUser:
    if not user.is_admin:
        raise AuthorizationError("Administrator access is required")
    return user


Admin = Annotated[AuthenticatedUser, Depends(admin_dependency)]


def create_app(settings_override: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        settings = settings_override or Settings.from_env()
        configure_logging(settings.environment)
        application.state.settings = settings
        application.state.container = None
        application.state.startup_error = None
        store: Any | None = None
        try:
            catalog = Catalog.load(settings.data_path, settings.embeddings_path)
            store = create_store(settings.database_url)
            store.initialize()
            index = SearchIndex(catalog, settings)
            sync_report = None
            if hasattr(store, "sync_catalog"):
                sync_report = store.sync_catalog(
                    catalog,
                    index.semantic_backend,
                    settings.model_version,
                    index.dense_embeddings(),
                )
            metrics = MetricRegistry()
            tracer = Tracer("tamiltrove-api", settings.app_version)
            ingestion = IngestionService(
                settings.trusted_poster_hosts,
                Path(settings.data_path).parent / "versions",
            )
            application.state.container = ServiceContainer(
                settings=settings,
                catalog=catalog,
                store=store,
                index=index,
                metrics=metrics,
                tracer=tracer,
                ingestion=ingestion,
            )
            logger.info(
                "service_ready",
                extra={
                    "dataset_version": catalog.dataset_version,
                    "movie_count": len(catalog.movies),
                    "semantic_backend": index.semantic_backend,
                    "storage_backend": type(store).__name__,
                    "catalog_sync": sync_report,
                },
            )
        except Exception as exc:
            application.state.startup_error = f"{type(exc).__name__}: {exc}"
            logger.exception("service_initialization_failed")
        yield
        if store is not None:
            store.close()

    app = FastAPI(
        title="TamilTrove API",
        version="2.0.0",
        summary="Multilingual, evidence-grounded Tamil-film discovery",
        description=(
            "Hybrid English, Tamil, and Tanglish search with explicit filters, "
            "personalization, interactions, collections, ingestion quality, and observability."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    rate_limiter = SlidingWindowRateLimiter()

    configured = settings_override or Settings.from_env()
    if any(origin == "*" for origin in configured.allowed_origins):
        raise RuntimeError("Credentialed CORS requires explicit ALLOWED_ORIGINS")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_controls(request: Request, call_next: Any) -> Response:
        settings: Settings = getattr(request.app.state, "settings", configured)
        request_id = new_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        response_status = 500
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > settings.max_request_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    response_status = 413
                    return JSONResponse(
                        error_payload(request_id, "request_too_large", "Request body is too large"),
                        status_code=413,
                        headers={"X-Request-ID": request_id},
                    )

            if request.url.path.startswith("/api/"):
                client_key = request.client.host if request.client else "unknown"
                group = "auth" if "/auth/" in request.url.path else "api"
                limit = (
                    min(settings.rate_limit_requests, 20)
                    if group == "auth"
                    else settings.rate_limit_requests
                )
                allowed, remaining, retry_after = rate_limiter.check(
                    client_key, group, limit, settings.rate_limit_window_seconds
                )
                if not allowed:
                    response_status = 429
                    return JSONResponse(
                        error_payload(request_id, "rate_limited", "Too many requests; retry later"),
                        status_code=429,
                        headers={
                            "Retry-After": str(retry_after),
                            "X-RateLimit-Remaining": "0",
                            "X-Request-ID": request_id,
                        },
                    )
                request.state.rate_limit_remaining = remaining

            cookie_auth = request.cookies.get(settings.session_cookie_name)
            authorization = request.headers.get("authorization")
            if (
                request.method not in SAFE_METHODS
                and request.url.path not in AUTH_CSRF_EXEMPT
                and cookie_auth
                and not authorization
            ):
                supplied = request.headers.get("X-CSRF-Token", "")
                expected = request.cookies.get(settings.csrf_cookie_name, "")
                origin = request.headers.get("origin")
                origin_valid = not origin or origin in settings.allowed_origins
                if (
                    not supplied
                    or not expected
                    or not hmac.compare_digest(supplied, expected)
                    or not origin_valid
                ):
                    response_status = 403
                    return JSONResponse(
                        error_payload(request_id, "csrf_failed", "CSRF validation failed"),
                        status_code=403,
                        headers={"X-Request-ID": request_id},
                    )

            response = await call_next(request)
            response_status = response.status_code
            response.headers["X-Request-ID"] = request_id
            if hasattr(request.state, "rate_limit_remaining"):
                response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
            return response
        finally:
            elapsed = time.perf_counter() - started
            container = getattr(request.app.state, "container", None)
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            if container is not None:
                labels = {
                    "method": request.method,
                    "route": route_path,
                    "status": str(response_status),
                }
                container.metrics.increment("tamiltrove_http_requests_total", labels)
                container.metrics.observe(
                    "tamiltrove_http_request_duration_seconds", elapsed, labels
                )
            logger.info(
                "request_complete",
                extra={
                    "method": request.method,
                    "route": route_path,
                    "status": response_status,
                    "duration_ms": round(elapsed * 1000, 3),
                },
            )
            request_id_context.reset(token)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_request_id())
        return JSONResponse(
            error_payload(request_id, exc.code, exc.message, exc.details),
            status_code=exc.status_code,
            headers={**exc.headers, "X-Request-ID": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_request_id())
        details = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            error_payload(request_id, "validation_error", "Request validation failed", details),
            status_code=422,
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_request_id())
        message = str(exc.detail) if exc.detail else "Request failed"
        return JSONResponse(
            error_payload(request_id, "http_error", message),
            status_code=exc.status_code,
            headers={**(exc.headers or {}), "X-Request-ID": request_id},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", new_request_id())
        logger.exception("unhandled_request_error", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            error_payload(request_id, "internal_error", "An unexpected server error occurred"),
            status_code=500,
            headers={"X-Request-ID": request_id},
        )

    def set_auth_cookies(response: Response, payload: dict[str, Any], settings: Settings) -> None:
        csrf = csrf_token()
        same_site: Literal["lax", "none"] = "none" if settings.secure_cookies else "lax"
        response.set_cookie(
            settings.session_cookie_name,
            payload["access_token"],
            max_age=payload["expires_in"],
            httponly=True,
            secure=settings.secure_cookies,
            samesite=same_site,
            path="/",
        )
        response.set_cookie(
            settings.csrf_cookie_name,
            csrf,
            max_age=payload["expires_in"],
            httponly=False,
            secure=settings.secure_cookies,
            samesite=same_site,
            path="/",
        )

    @app.get("/health", tags=["operations"])
    def health(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "2.0.0",
            "request_id": getattr(request.state, "request_id", ""),
        }

    @app.get("/ready", tags=["operations"])
    def ready(request: Request) -> JSONResponse:
        container = getattr(request.app.state, "container", None)
        database_ready = bool(container and container.store.ping())
        catalog_ready = bool(container and container.catalog.movies)
        is_ready = database_ready and catalog_ready
        payload = {
            "status": "ready" if is_ready else "not_ready",
            "ready": is_ready,
            "checks": {
                "database": database_ready,
                "catalog": catalog_ready,
                "ranking": bool(container and container.index.semantic_matrix is not None),
            },
            "degraded_reasons": list(container.index.degraded_reasons) if container else [],
            "error": getattr(request.app.state, "startup_error", None),
        }
        return JSONResponse(payload, status_code=200 if is_ready else 503)

    @app.get("/metrics", tags=["operations"], response_class=PlainTextResponse)
    def metrics(request: Request) -> PlainTextResponse:
        container = getattr(request.app.state, "container", None)
        if container is None:
            return PlainTextResponse("tamiltrove_ready 0\n", media_type="text/plain; version=0.0.4")
        return PlainTextResponse(
            "tamiltrove_ready 1\n" + container.metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post(
        "/api/v1/auth/register",
        response_model=AuthResponse,
        status_code=201,
        tags=["authentication"],
    )
    def register(body: RegisterRequest, response: Response, container: Container) -> dict[str, Any]:
        payload = AuthService(container).register(
            body.email, body.password, body.display_name, body.locale
        )
        set_auth_cookies(response, payload, container.settings)
        return payload

    @app.post("/api/v1/auth/login", response_model=AuthResponse, tags=["authentication"])
    def login(body: LoginRequest, response: Response, container: Container) -> dict[str, Any]:
        payload = AuthService(container).login(body.email, body.password)
        set_auth_cookies(response, payload, container.settings)
        return payload

    @app.post("/api/v1/auth/logout", status_code=204, tags=["authentication"])
    def logout(request: Request, response: Response, user: User, container: Container) -> Response:
        payload = getattr(request.state, "auth_payload", {})
        if payload.get("jti") and payload.get("exp"):
            container.store.revoke_token(str(payload["jti"]), user.id, int(payload["exp"]))
        response.delete_cookie(container.settings.session_cookie_name, path="/")
        response.delete_cookie(container.settings.csrf_cookie_name, path="/")
        response.status_code = 204
        return response

    @app.get("/api/v1/profile", response_model=ProfileOut, tags=["profile"])
    def get_profile(user: User, container: Container) -> dict[str, Any]:
        return AuthService(container).profile(user.id)

    @app.patch("/api/v1/profile", response_model=ProfileOut, tags=["profile"])
    def patch_profile(body: ProfilePatch, user: User, container: Container) -> dict[str, Any]:
        return AuthService(container).update_profile(
            user.id, body.model_dump(exclude_none=True, mode="json")
        )

    @app.get("/api/v1/profile/export", tags=["profile"])
    def export_profile(user: User, container: Container) -> JSONResponse:
        return JSONResponse(
            jsonable_encoder(container.store.export_user(user.id)),
            headers={"Content-Disposition": 'attachment; filename="tamiltrove-export.json"'},
        )

    @app.delete("/api/v1/profile", status_code=204, tags=["profile"])
    def delete_profile(response: Response, user: User, container: Container) -> Response:
        container.store.delete_user(user.id)
        response.delete_cookie(container.settings.session_cookie_name, path="/")
        response.delete_cookie(container.settings.csrf_cookie_name, path="/")
        response.status_code = 204
        return response

    @app.post("/api/v1/search", response_model=SearchResponse, tags=["discovery"])
    def search(
        body: SearchRequest, request: Request, user: OptionalUser, container: Container
    ) -> dict[str, Any]:
        return SearchService(container).search(
            body, request.state.request_id, user.id if user else None
        )

    @app.post("/api/search", tags=["compatibility"], deprecated=True)
    def legacy_search(
        body: SearchRequest, request: Request, user: OptionalUser, container: Container
    ) -> dict[str, Any]:
        return SearchService(container).search(
            body, request.state.request_id, user.id if user else None
        )

    @app.get("/api/v1/movies/{movie_id}", response_model=MovieOut, tags=["movies"])
    def movie_detail(movie_id: str, user: OptionalUser, container: Container) -> dict[str, Any]:
        movie = container.catalog.get(movie_id)
        if not movie:
            raise NotFoundError("Movie")
        states = interaction_state(container, user.id if user else None)
        payload = movie_payload(movie, states.get(movie.id), provenance=True)
        payload["index"] = movie.source_index
        return payload

    @app.get("/api/v1/movies/{movie_id}/similar", response_model=SearchResponse, tags=["movies"])
    def similar_movies(
        movie_id: str,
        request: Request,
        user: OptionalUser,
        container: Container,
        page: int = Query(1, ge=1),
        page_size: int = Query(12, ge=1, le=50),
    ) -> dict[str, Any]:
        return SearchService(container).similar(
            movie_id, request.state.request_id, page, page_size, user.id if user else None
        )

    @app.get("/api/v1/recommendations", response_model=SearchResponse, tags=["recommendations"])
    def recommendations(
        request: Request,
        user: User,
        container: Container,
        surface: Literal["for_you", "hidden_gems", "recent", "recently_added"] = "for_you",
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
    ) -> dict[str, Any]:
        return SearchService(container).recommendations(
            request.state.request_id, user.id, surface, page, page_size
        )

    @app.post(
        "/api/v1/interactions", response_model=InteractionOut, status_code=201, tags=["feedback"]
    )
    def create_interaction(
        body: InteractionRequest, user: User, container: Container
    ) -> dict[str, Any]:
        if not container.catalog.get(body.movie_id):
            raise NotFoundError("Movie")
        item = container.store.upsert_interaction(
            user.id, body.movie_id, body.type.value, body.value, body.context
        )
        container.metrics.increment("tamiltrove_interactions_total", {"type": body.type.value})
        return item

    @app.get("/api/v1/interactions", tags=["feedback"])
    def list_interactions(
        user: User,
        container: Container,
        interaction_type: InteractionType | None = Query(None, alias="type"),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        values = container.store.list_interactions(
            user.id, interaction_type.value if interaction_type else None, page_size, offset
        )
        return {"items": values, "page": page, "page_size": page_size}

    @app.delete(
        "/api/v1/interactions/{interaction_type}/{movie_id}", status_code=204, tags=["feedback"]
    )
    def delete_interaction(
        interaction_type: InteractionType,
        movie_id: str,
        user: User,
        container: Container,
    ) -> Response:
        container.store.delete_interaction(user.id, movie_id, interaction_type.value)
        return Response(status_code=204)

    @app.get("/api/v1/watchlist", tags=["feedback"])
    def watchlist(user: User, container: Container) -> dict[str, Any]:
        saved = container.store.list_interactions(user.id, "save", limit=10_000)
        seen: set[str] = set()
        items = []
        states = interaction_state(container, user.id)
        for entry in saved:
            movie_id = entry["movie_id"]
            movie = container.catalog.get(movie_id)
            if movie and movie_id not in seen:
                seen.add(movie_id)
                items.append(movie_payload(movie, states.get(movie_id)))
        return {"items": items, "total": len(items)}

    @app.put("/api/v1/watchlist/{movie_id}", response_model=InteractionOut, tags=["feedback"])
    def save_to_watchlist(movie_id: str, user: User, container: Container) -> dict[str, Any]:
        if not container.catalog.get(movie_id):
            raise NotFoundError("Movie")
        return container.store.upsert_interaction(
            user.id, movie_id, "save", None, {"source": "watchlist"}
        )

    @app.delete("/api/v1/watchlist/{movie_id}", status_code=204, tags=["feedback"])
    def remove_from_watchlist(movie_id: str, user: User, container: Container) -> Response:
        container.store.delete_interaction(user.id, movie_id, "save")
        return Response(status_code=204)

    @app.get("/api/v1/history/search", tags=["profile"])
    def search_history(
        user: User, container: Container, limit: int = Query(100, ge=1, le=500)
    ) -> dict[str, Any]:
        values = container.store.list_search_history(user.id, limit)
        return {"items": values, "total": len(values)}

    @app.delete("/api/v1/history/search", status_code=204, tags=["profile"])
    def clear_search_history(user: User, container: Container) -> Response:
        container.store.clear_search_history(user.id)
        return Response(status_code=204)

    @app.get("/api/v1/collections", response_model=list[CollectionOut], tags=["collections"])
    def collections(user: User, container: Container) -> list[dict[str, Any]]:
        return CollectionService(container).list_owned(user.id)

    @app.post(
        "/api/v1/collections", response_model=CollectionOut, status_code=201, tags=["collections"]
    )
    def create_collection(
        body: CollectionCreate, user: User, container: Container
    ) -> dict[str, Any]:
        return CollectionService(container).create(user.id, body.model_dump(mode="json"))

    @app.get(
        "/api/v1/collections/shared/{token}", response_model=CollectionOut, tags=["collections"]
    )
    def shared_collection(token: str, container: Container) -> dict[str, Any]:
        return CollectionService(container).shared(token)

    @app.get(
        "/api/v1/collections/{collection_id}", response_model=CollectionOut, tags=["collections"]
    )
    def collection_detail(
        collection_id: str, user: OptionalUser, container: Container
    ) -> dict[str, Any]:
        return CollectionService(container).get(collection_id, user.id if user else None)

    @app.patch(
        "/api/v1/collections/{collection_id}", response_model=CollectionOut, tags=["collections"]
    )
    def update_collection(
        collection_id: str, body: CollectionPatch, user: User, container: Container
    ) -> dict[str, Any]:
        return CollectionService(container).update(
            collection_id, user.id, body.model_dump(exclude_none=True, mode="json")
        )

    @app.delete("/api/v1/collections/{collection_id}", status_code=204, tags=["collections"])
    def delete_collection(collection_id: str, user: User, container: Container) -> Response:
        CollectionService(container).delete(collection_id, user.id)
        return Response(status_code=204)

    @app.post(
        "/api/v1/collections/{collection_id}/share",
        response_model=CollectionOut,
        tags=["collections"],
    )
    def share_collection(collection_id: str, user: User, container: Container) -> dict[str, Any]:
        return CollectionService(container).share(collection_id, user.id)

    @app.post(
        "/api/v1/collections/{collection_id}/items",
        response_model=CollectionOut,
        tags=["collections"],
    )
    def add_collection_item(
        collection_id: str,
        body: CollectionItemRequest,
        user: User,
        container: Container,
    ) -> dict[str, Any]:
        return CollectionService(container).add_item(
            collection_id, user.id, body.movie_id, body.position
        )

    @app.delete(
        "/api/v1/collections/{collection_id}/items/{movie_id}",
        response_model=CollectionOut,
        tags=["collections"],
    )
    def remove_collection_item(
        collection_id: str, movie_id: str, user: User, container: Container
    ) -> dict[str, Any]:
        return CollectionService(container).remove_item(collection_id, user.id, movie_id)

    def quality_payload(container: ServiceContainer) -> dict[str, Any]:
        report = dict(container.catalog.validation_report)
        distribution: dict[str, int] = defaultdict(int)
        for movie in container.catalog.movies:
            distribution[movie.data_quality_status] += 1
        report.update(
            {
                "quality_distribution": dict(distribution),
                "semantic_backend": container.index.semantic_backend,
                "degraded_reasons": container.index.degraded_reasons,
                "ranking_version": container.settings.ranking_version,
                "dataset_versions": container.store.list_dataset_versions(),
            }
        )
        return report

    @app.get("/api/v1/admin/data-quality", tags=["administration"])
    def data_quality(_: Admin, container: Container) -> dict[str, Any]:
        return quality_payload(container)

    @app.get("/api/v1/admin/experiments", tags=["administration"])
    def experiments(_: Admin, container: Container) -> dict[str, Any]:
        settings = container.settings
        return {
            "ranking_version": settings.ranking_version,
            "feature_flags": {
                "transformer": settings.enable_transformer,
                "debug_scores": settings.debug_scores,
                "personalization": True,
                "diversity": settings.ranking_diversity > 0,
            },
            "weights": {
                "semantic": settings.ranking_semantic_weight,
                "lexical": settings.ranking_lexical_weight,
                "preference": settings.ranking_preference_weight,
                "quality": settings.ranking_quality_weight,
                "hidden_gem": settings.ranking_hidden_gem_weight,
            },
        }

    @app.post("/api/v1/admin/ingestion/validate", tags=["administration"])
    def validate_ingestion(
        body: IngestionRequest, _: Admin, container: Container
    ) -> dict[str, Any]:
        records = [item.model_dump(mode="json") for item in body.records]
        outcome = container.ingestion.validate(records, body.transformation_version)
        return {
            "accepted_count": len(outcome.accepted),
            "quarantined_count": len(outcome.quarantined),
            "quarantined": outcome.quarantined,
            "warnings": outcome.warnings,
            "dry_run": True,
        }

    @app.post("/api/v1/admin/ingestion/run", tags=["administration"])
    def run_ingestion(body: IngestionRequest, _: Admin, container: Container) -> dict[str, Any]:
        records = [item.model_dump(mode="json") for item in body.records]
        report = container.ingestion.run(records, body.transformation_version, body.dry_run)
        run = container.store.record_ingestion_run(
            body.transformation_version, body.dry_run, report
        )
        container.metrics.increment(
            "tamiltrove_ingestion_runs_total",
            {"status": run["status"], "dry_run": str(body.dry_run).lower()},
        )
        if report["quarantined_count"]:
            container.metrics.increment(
                "tamiltrove_ingestion_quarantined_records_total",
                amount=report["quarantined_count"],
            )
        return run

    @app.get("/api/v1/admin/dataset/versions", tags=["administration"])
    def dataset_versions(_: Admin, container: Container) -> dict[str, Any]:
        return {"items": container.store.list_dataset_versions()}

    return app


app = create_app()
