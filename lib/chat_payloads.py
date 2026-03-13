from typing import Any, Dict, Optional


def build_chat_payload(
	message: Any,
	inquiry_payload: Optional[Dict[str, Any]] = None,
	sender: Optional[str] = None,
	hashed_username: Optional[str] = None,
) -> Dict[str, Any]:
	if isinstance(message, dict):
		payload: Dict[str, Any] = dict(message)
		payload["message"] = payload.get("message") or payload.get("question") or ((payload.get("inquiry") or {}).get("question")) or ""
	else:
		payload = {
			"message": message,
		}
	if sender is not None:
		payload["sender"] = sender
	if hashed_username is not None:
		payload["hashed_username"] = hashed_username
	if inquiry_payload:
		payload["question"] = inquiry_payload.get("question") or payload.get("message")
		payload["inquiry"] = inquiry_payload.get("inquiry")
		payload["explanation"] = inquiry_payload.get("explanation")
	if payload.get("question") is None:
		payload["question"] = ((payload.get("inquiry") or {}).get("question")) or payload.get("message")
	return payload