"""All agent-readiness checks."""

from .structured_errors import check_structured_errors
from .discovery import check_discovery
from .llms_txt import check_llms_txt
from .robots_txt import check_robots_txt
from .rate_limits import check_rate_limits
from .openapi import check_openapi
from .content_type import check_content_type
from .cors import check_cors
from .security_headers import check_security_headers
from .response_time import check_response_time
from .x402 import check_x402
from .agents_txt import check_agents_txt
from .ag_ui import check_ag_ui

from ..types import CheckFn

all_checks: list[CheckFn] = [
    check_structured_errors,
    check_discovery,
    check_llms_txt,
    check_robots_txt,
    check_rate_limits,
    check_openapi,
    check_content_type,
    check_cors,
    check_security_headers,
    check_response_time,
    check_x402,
    check_agents_txt,
    check_ag_ui,
]

__all__ = [
    "all_checks",
    "check_structured_errors",
    "check_discovery",
    "check_llms_txt",
    "check_robots_txt",
    "check_rate_limits",
    "check_openapi",
    "check_content_type",
    "check_cors",
    "check_security_headers",
    "check_response_time",
    "check_x402",
    "check_agents_txt",
    "check_ag_ui",
]
