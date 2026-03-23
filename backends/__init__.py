"""Backend registry for complaint-generator.

Router-first: prefer `LLMRouterBackend`.

Legacy OpenAI/HuggingFace backends still exist as deprecated modules under
`backends.openai`, `backends.huggingface`, and `backends.openaibackend`, but
they are not imported here to avoid triggering warnings on normal imports.
"""

from .workstation import *
from .llm_router_backend import LLMRouterBackend, LLMRouter
from .multimodal_router_backend import MultimodalRouter, MultimodalRouterBackend
