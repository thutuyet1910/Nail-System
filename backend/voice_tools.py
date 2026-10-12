import json

import voice_foundation


READ_ONLY_TOOL_DEFINITIONS = [
    {"type": "function", "name": "get_salon_info", "description": "Get authoritative public salon details and business hours.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "list_services", "description": "List active services, durations, and configured prices.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "get_service_details", "description": "Get authoritative details for one active service.", "parameters": {"type": "object", "properties": {"service_id": {"type": "integer"}}, "required": ["service_id"], "additionalProperties": False}},
    {"type": "function", "name": "get_available_slots", "description": "Check real availability for one date and the chosen service_ids. This never reserves anything. Every returned slot has a slot_id: offer only returned slots, and use a slot_id exactly as returned when booking. Optionally pass technician_name if the caller asks for a specific technician.", "parameters": {"type": "object", "properties": {"date": {"type": "string", "description": "Salon-local date in YYYY-MM-DD format"}, "service_ids": {"type": "array", "items": {"type": "integer"}}, "technician_id": {"type": ["integer", "null"]}, "technician_name": {"type": "string", "maxLength": 60}}, "required": ["date", "service_ids"], "additionalProperties": False}},
    {"type": "function", "name": "identify_customer_candidate", "description": "Check whether the trusted caller ID matches a customer. Returns only matched true/false; never a name, account or appointment detail, and never proof of identity.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "create_booking", "description": "Book ONE new appointment in a slot returned by get_available_slots, after the caller agrees. Two steps. Step 1: call with slot_id and customer_name only; nothing is booked and you get a summary to read to the caller. Step 2: only after the caller clearly says yes to that summary, call again with the same slot_id and customer_name plus caller_confirmation (the caller's own words). Only pass customer_phone when caller ID is unavailable. Never tell the caller it is booked unless this returns status booked.", "parameters": {"type": "object", "properties": {"slot_id": {"type": "string", "maxLength": 40}, "customer_name": {"type": "string", "maxLength": 60}, "customer_phone": {"type": "string", "maxLength": 32}, "caller_confirmation": {"type": "string", "maxLength": 120}}, "required": ["slot_id", "customer_name"], "additionalProperties": False}},
    {"type": "function", "name": "request_owner_callback", "description": "Request one owner callback for this call (further requests return the same result). This is the only allowed write. Only pass callback_phone when caller ID is unavailable; a spoken number is for contacting the caller only and never identifies or verifies them.", "parameters": {"type": "object", "properties": {"category": {"type": "string", "enum": ["general", "booking", "reschedule", "cancellation", "complaint", "other"]}, "urgency": {"type": "string", "enum": ["normal", "urgent"]}, "summary": {"type": "string", "maxLength": 500}, "callback_phone": {"type": "string", "maxLength": 32}}, "required": ["category", "urgency", "summary"], "additionalProperties": False}},
]

ALLOWED_TOOL_NAMES = {item["name"] for item in READ_ONLY_TOOL_DEFINITIONS}


def dispatch_voice_tool(facade: voice_foundation.VoiceBookingFacade, gateway, name: str, arguments: str | dict):
    if name not in ALLOWED_TOOL_NAMES:
        raise voice_foundation.VoiceFoundationError("Tool is not allowed in voice mode")
    args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
    if not isinstance(args, dict):
        raise voice_foundation.VoiceFoundationError("Tool arguments must be an object")
    if name == "get_salon_info":
        result = facade.get_salon_info()
    elif name == "list_services":
        result = facade.list_services()
    elif name == "get_service_details":
        result = facade.get_service_details(args["service_id"])
    elif name == "get_available_slots":
        result = facade.get_available_slots(args["date"], args["service_ids"], args.get("technician_id"), args.get("technician_name"))
    elif name == "create_booking":
        result = facade.create_booking({key: args[key] for key in ("slot_id", "customer_name", "customer_phone", "caller_confirmation") if key in args})
    elif name == "identify_customer_candidate":
        result = facade.identify_customer_candidate(gateway)
    else:
        # Only these fields are honored; anything else the model sends (its own idempotency key,
        # a phone "identity", ...) is ignored. Deduplication is server-owned.
        result = facade.request_owner_callback(**{k: args[k] for k in ("category", "urgency", "summary", "callback_phone") if k in args})
    call = facade.db.get(__import__("models").VoiceCall, facade.context.call_database_id)
    voice_foundation.append_call_event(
        facade.db, call=call, event_type="tool_called", result_status="success",
        operation_key=None,
        metadata={"tool": name},
    )
    return result
