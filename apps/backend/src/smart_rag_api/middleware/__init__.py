"""FastAPI middleware helpers owned by the backend transport package."""

from __future__ import annotations

from smart_rag_api.middleware.correlation import normalized_request_id
from smart_rag_api.middleware.cors import add_cors
from smart_rag_api.middleware.errors import install_error_handlers
from smart_rag_api.middleware.preauth import limit_preauth_ip
from smart_rag_api.middleware.request_limits import limit_request_body
from smart_rag_api.middleware.security_headers import add_security_headers

__all__ = [
    "add_cors",
    "add_security_headers",
    "install_error_handlers",
    "limit_preauth_ip",
    "limit_request_body",
    "normalized_request_id",
]
