"""Backward-compatible re-exports from split adapter modules.

Previously this file contained a2a_urlpatterns, discovery_urlpatterns, and
llms_txt_urlpatterns directly. They have been split into separate files
(a2a.py, discovery.py, llms_txt.py) for parity with FastAPI/Flask adapters.
This module re-exports them so existing imports continue to work.
"""

from agent_layer.django.a2a import a2a_urlpatterns
from agent_layer.django.discovery import discovery_urlpatterns
from agent_layer.django.llms_txt import llms_txt_urlpatterns

__all__ = [
    "a2a_urlpatterns",
    "discovery_urlpatterns",
    "llms_txt_urlpatterns",
]
