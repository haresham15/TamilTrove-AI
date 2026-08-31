from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


class NotFoundError(AppError):
    def __init__(self, resource: str, details: Any | None = None) -> None:
        super().__init__(404, "not_found", f"{resource} was not found", details)


class ConflictError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(409, "conflict", message, details)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication is required") -> None:
        super().__init__(
            401, "authentication_required", message, headers={"WWW-Authenticate": "Bearer"}
        )


class AuthorizationError(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(403, "permission_denied", message)
