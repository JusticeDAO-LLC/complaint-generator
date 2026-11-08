from applications.review_ui import create_review_surface_app
from mediator.interface import Mediator


def build_chat_payload(message, *, sender=None, hashed_username=None, inquiry_payload=None):
    """Normalize legacy chat messages and structured inquiry payloads."""

    payload = {}
    if isinstance(message, dict):
        payload.update(message)
    else:
        payload["message"] = message

    if inquiry_payload:
        payload.update(inquiry_payload)

    if "message" not in payload:
        inquiry = payload.get("inquiry")
        if isinstance(inquiry, dict) and inquiry.get("question"):
            payload["message"] = inquiry["question"]
        elif payload.get("question"):
            payload["message"] = payload["question"]

    if "question" not in payload and payload.get("message") is not None:
        payload["question"] = payload["message"]
    if sender is not None:
        payload["sender"] = sender
    if hashed_username is not None:
        payload["hashed_username"] = hashed_username
    return payload


def create_app():
    return create_review_surface_app(Mediator([]))


app = create_app()
