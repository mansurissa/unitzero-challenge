"""Domain errors raised by service functions, and how DRF turns them into responses."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """A business-rule violation. `code` is a stable machine-readable identifier for clients and tests."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid"

    def __init__(self, detail, code=None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code


class NotAllowed(DomainError):
    """The actor's role may not perform this action."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "not_allowed"


class Conflict(DomainError):
    """The action collides with current state (e.g. the episode is already assigned)."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response({"detail": exc.detail, "code": exc.code}, status=exc.status_code)
    return drf_exception_handler(exc, context)
