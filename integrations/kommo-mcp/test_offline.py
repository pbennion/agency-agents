"""
Offline tests for Kommo MCP server.
No API keys or tokens required.
"""

import sys
import os
import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")

# ── 1. Check imports ──────────────────────────────────────
print("=" * 60)
print("TEST 1: Imports")
print("=" * 60)

for mod, attr in [("httpx", "__version__"), ("pydantic", "__version__"), ("fastmcp", None)]:
    try:
        m = __import__(mod)
        ver = getattr(m, attr, "ok") if attr else "ok"
        ok(f"{mod} {ver}")
    except ImportError as e:
        fail(f"{mod}: {e}")

# ── 2. Load server module ─────────────────────────────────
print()
print("=" * 60)
print("TEST 2: Module load")
print("=" * 60)

os.environ["KOMMO_TOKEN"] = "test_token"
os.environ["KOMMO_SUBDOMAIN"] = "test_subdomain"

sys.path.insert(0, "/Users/dmitrijcernov/Documents/VASILIJ/kommo_mcp")

try:
    import server as K
    ok("server.py loaded successfully")
except Exception as e:
    fail(f"Failed to load server.py: {e}")
    sys.exit(1)

# ── 3. Check all tools registered ────────────────────────
print()
print("=" * 60)
print("TEST 3: Tool registration")
print("=" * 60)

try:
    registered = {t.name for t in K.mcp._tool_manager.list_tools()}
    print(f"  Registered: {len(registered)} tools\n")

    EXPECTED = {
        "kommo_list_leads", "kommo_get_lead", "kommo_create_leads",
        "kommo_update_lead", "kommo_delete_lead",
        "kommo_list_contacts", "kommo_get_contact", "kommo_create_contacts",
        "kommo_update_contact",
        "kommo_list_companies", "kommo_get_company", "kommo_create_companies",
        "kommo_update_company",
        "kommo_list_tasks", "kommo_create_tasks", "kommo_update_task",
        "kommo_list_notes", "kommo_add_note",
        "kommo_list_pipelines", "kommo_list_pipeline_statuses",
        "kommo_list_unsorted",
        "kommo_list_users", "kommo_get_user",
        "kommo_list_custom_fields",
        "kommo_list_tags", "kommo_create_tags",
        "kommo_list_events",
        "kommo_add_call",
    }

    for name in sorted(EXPECTED):
        if name in registered:
            ok(name)
        else:
            fail(f"MISSING: {name}")

    extra = registered - EXPECTED
    if extra:
        print(f"\n  ℹ️  Additional registered tools:")
        for t in sorted(extra):
            print(f"     + {t}")
except Exception as e:
    fail(f"Could not inspect tools: {e}")

# ── 4. Test env var validation ────────────────────────────
print()
print("=" * 60)
print("TEST 4: Env var validation")
print("=" * 60)

async def test_env_validation():
    # Missing KOMMO_TOKEN
    os.environ.pop("KOMMO_TOKEN", None)
    os.environ.pop("KOMMO_SUBDOMAIN", None)
    result = await K.kommo_list_leads(K.ListLeadsInput())
    if "Config error" in result or "must be set" in result:
        ok("Missing KOMMO_TOKEN → proper error returned")
    else:
        fail(f"Unexpected response for missing token: {result[:80]}")

    # Token present, missing subdomain
    os.environ["KOMMO_TOKEN"] = "test_token"
    result2 = await K.kommo_list_leads(K.ListLeadsInput())
    if "Config error" in result2 or "must be set" in result2:
        ok("Missing KOMMO_SUBDOMAIN → proper error returned")
    else:
        fail(f"Unexpected response for missing subdomain: {result2[:80]}")

    # Restore
    os.environ["KOMMO_SUBDOMAIN"] = "test_subdomain"

asyncio.run(test_env_validation())

# ── 5. Pydantic model validation ──────────────────────────
print()
print("=" * 60)
print("TEST 5: Pydantic model validation")
print("=" * 60)

from pydantic import ValidationError

# 5a. ListLeadsInput defaults
try:
    m = K.ListLeadsInput()
    assert m.limit == 20
    assert m.page == 1
    ok("ListLeadsInput — defaults OK")
except Exception as e:
    fail(f"ListLeadsInput defaults: {e}")

# 5b. ListLeadsInput valid values
try:
    m = K.ListLeadsInput(limit=50, page=3, pipeline_id=123)
    assert m.limit == 50
    assert m.pipeline_id == 123
    ok("ListLeadsInput — custom values OK")
except Exception as e:
    fail(f"ListLeadsInput custom: {e}")

# 5c. ListLeadsInput — limit too high
try:
    m = K.ListLeadsInput(limit=999)
    fail(f"Should reject limit=999 (got {m.limit})")
except ValidationError:
    ok("ListLeadsInput — rejects limit > 250")

# 5d. GetLeadInput — lead_id required
try:
    m = K.GetLeadInput()
    fail("Should require lead_id")
except ValidationError:
    ok("GetLeadInput — requires lead_id")

# 5e. GetLeadInput — valid
try:
    m = K.GetLeadInput(lead_id=12345)
    assert m.lead_id == 12345
    ok("GetLeadInput — valid input OK")
except Exception as e:
    fail(f"GetLeadInput valid: {e}")

# 5f. AddCallInput — valid
try:
    m = K.KommoAddCallInput(
        direction="inbound", duration=120,
        source="Zadarma", phone="+37060000000", call_status=4,
    )
    assert m.direction == "inbound"
    ok("KommoAddCallInput — valid input OK")
except Exception as e:
    fail(f"KommoAddCallInput valid: {e}")

# 5g. AddCallInput — missing required fields
try:
    m = K.KommoAddCallInput(direction="inbound")
    fail("Should reject incomplete call input")
except ValidationError:
    ok("KommoAddCallInput — rejects incomplete input")

# ── 6. Mock HTTP responses ────────────────────────────────
print()
print("=" * 60)
print("TEST 6: Mock HTTP responses")
print("=" * 60)

os.environ["KOMMO_TOKEN"] = "fake_token"
os.environ["KOMMO_SUBDOMAIN"] = "testcompany"

MOCK_LEADS = {
    "_embedded": {
        "leads": [
            {"id": 1, "name": "Test Lead 1", "price": 10000, "status_id": 142, "pipeline_id": 100},
            {"id": 2, "name": "Test Lead 2", "price": 5000,  "status_id": 143, "pipeline_id": 100},
        ]
    },
    "_page_count": 1,
}

def _mock_client(response_data):
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()
    mock_cl = AsyncMock()
    mock_cl.__aenter__ = AsyncMock(return_value=mock_cl)
    mock_cl.__aexit__ = AsyncMock(return_value=False)
    mock_cl.get = AsyncMock(return_value=mock_resp)
    mock_cl.post = AsyncMock(return_value=mock_resp)
    mock_cl.patch = AsyncMock(return_value=mock_resp)
    mock_cl.delete = AsyncMock(return_value=mock_resp)
    return mock_cl

async def test_mock_leads_json():
    with patch("httpx.AsyncClient", return_value=_mock_client(MOCK_LEADS)):
        from server import ResponseFormat
        result = await K.kommo_list_leads(K.ListLeadsInput(response_format=ResponseFormat.JSON))
    data = json.loads(result)
    leads = data.get("_embedded", {}).get("leads", [])
    assert len(leads) == 2
    assert leads[0]["name"] == "Test Lead 1"
    ok("kommo_list_leads — JSON format, 2 leads returned")

async def test_mock_leads_markdown():
    with patch("httpx.AsyncClient", return_value=_mock_client(MOCK_LEADS)):
        result = await K.kommo_list_leads(K.ListLeadsInput())
    assert "Test Lead 1" in result and "Test Lead 2" in result
    ok("kommo_list_leads — Markdown format OK")

async def test_http_401():
    from httpx import HTTPStatusError, Request, Response
    mock_req = MagicMock(spec=Request)
    mock_res = MagicMock(spec=Response)
    mock_res.status_code = 401
    mock_res.text = "Unauthorized"
    mock_res.json.side_effect = Exception("not json")

    err_resp = MagicMock()
    err_resp.raise_for_status.side_effect = HTTPStatusError("401", request=mock_req, response=mock_res)

    mock_cl = _mock_client({})
    mock_cl.get = AsyncMock(return_value=err_resp)

    with patch("httpx.AsyncClient", return_value=mock_cl):
        result = await K.kommo_list_leads(K.ListLeadsInput())

    if "401" in result or "token" in result.lower():
        ok("HTTP 401 → proper error message")
    else:
        fail(f"HTTP 401 unexpected: {result[:100]}")

async def test_http_404():
    from httpx import HTTPStatusError, Request, Response
    mock_req = MagicMock(spec=Request)
    mock_res = MagicMock(spec=Response)
    mock_res.status_code = 404
    mock_res.text = "Not Found"
    mock_res.json.side_effect = Exception("not json")

    err_resp = MagicMock()
    err_resp.raise_for_status.side_effect = HTTPStatusError("404", request=mock_req, response=mock_res)

    mock_cl = _mock_client({})
    mock_cl.get = AsyncMock(return_value=err_resp)

    with patch("httpx.AsyncClient", return_value=mock_cl):
        result = await K.kommo_get_lead(K.GetLeadInput(lead_id=99999))

    if "404" in result or "not found" in result.lower():
        ok("HTTP 404 → proper error message")
    else:
        fail(f"HTTP 404 unexpected: {result[:100]}")

for coro in [test_mock_leads_json, test_mock_leads_markdown, test_http_401, test_http_404]:
    try:
        asyncio.run(coro())
    except Exception as e:
        fail(f"{coro.__name__}: {e}")

# ── 7. _embedded helper ───────────────────────────────────
print()
print("=" * 60)
print("TEST 7: Internal helpers")
print("=" * 60)

# _embedded with dict
result = K._embedded({"_embedded": {"leads": [{"id": 1}]}}, "leads")
assert result == [{"id": 1}], f"Expected [{{id:1}}], got {result}"
ok("_embedded — extracts from dict correctly")

# _embedded with list (passthrough)
result = K._embedded([{"id": 2}], "leads")
assert result == [{"id": 2}]
ok("_embedded — list passthrough OK")

# _embedded with missing key
result = K._embedded({"_embedded": {}}, "leads")
assert result == []
ok("_embedded — returns [] for missing key")

# _error helper
from httpx import HTTPStatusError, Request, Response as HResp
mock_req = MagicMock(spec=Request)
mock_res = MagicMock(spec=HResp)
mock_res.status_code = 429
mock_res.text = "Too Many Requests"
mock_res.json.side_effect = Exception()

e = HTTPStatusError("429", request=mock_req, response=mock_res)
msg = K._error(e)
assert "429" in msg
ok("_error — 429 rate limit message OK")

# Config error
msg = K._error(ValueError("KOMMO_TOKEN environment variable must be set."))
assert "Config error" in msg
ok("_error — ValueError → Config error message OK")

# ── Summary ───────────────────────────────────────────────
print()
print("=" * 60)
print(f"RESULTS: {PASS} passed / {FAIL} failed")
print("=" * 60)
if FAIL > 0:
    sys.exit(1)
