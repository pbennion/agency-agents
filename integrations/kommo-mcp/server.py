#!/usr/bin/env python3
"""
Kommo CRM MCP Server

MCP server for working with Kommo CRM via Claude Desktop.
Provides tools for leads, contacts, companies, tasks, notes,
pipelines, users, custom fields, tags, events, and calls.

Authentication via environment variables:
  KOMMO_TOKEN      - long-lived token (from Settings → Integrations → Keys and scopes)
  KOMMO_SUBDOMAIN  - account subdomain (e.g. 'mycompany' from mycompany.kommo.com)
"""

import json
import os
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

mcp = FastMCP("kommo_mcp")


def _base_url() -> str:
    subdomain = os.environ.get("KOMMO_SUBDOMAIN", "")
    if not subdomain:
        raise ValueError("KOMMO_SUBDOMAIN environment variable must be set.")
    return f"https://{subdomain}.kommo.com/api/v4"


def _headers() -> dict:
    token = os.environ.get("KOMMO_TOKEN", "")
    if not token:
        raise ValueError("KOMMO_TOKEN environment variable must be set.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────
# Shared HTTP helpers
# ─────────────────────────────────────────────

async def _get(path: str, params: Dict[str, Any] = {}) -> Any:
    clean = {k: v for k, v in params.items() if v is not None}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{_base_url()}{path}", headers=_headers(), params=clean)
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: Any) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{_base_url()}{path}", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


async def _patch(path: str, body: Any) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.patch(f"{_base_url()}{path}", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


def _error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        if code == 401:
            return "Error 401: Invalid token. Check KOMMO_TOKEN."
        if code == 403:
            return "Error 403: Access denied. Check integration permissions."
        if code == 404:
            return "Error 404: Resource not found. Check the ID."
        if code == 429:
            return "Error 429: Rate limit exceeded. Try again later."
        return f"Error {code}: {detail}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out after 30s."
    if isinstance(e, ValueError):
        return f"Config error: {e}"
    return f"Error: {type(e).__name__}: {e}"


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _embedded(data: Any, key: str) -> List[dict]:
    """Extract items from Kommo _embedded response."""
    if isinstance(data, list):
        return data
    return data.get("_embedded", {}).get(key, [])


# ─────────────────────────────────────────────
# Shared Pydantic models
# ─────────────────────────────────────────────

class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


# ═══════════════════════════════════════════════════════════
# LEADS
# ═══════════════════════════════════════════════════════════

class ListLeadsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    page: Optional[int] = Field(default=1, ge=1, description="Page number (default 1)")
    limit: Optional[int] = Field(default=20, ge=1, le=250, description="Results per page, max 250 (default 20)")
    query: Optional[str] = Field(default=None, description="Search query across lead fields")
    pipeline_id: Optional[int] = Field(default=None, description="Filter by pipeline ID")
    responsible_user_id: Optional[int] = Field(default=None, description="Filter by responsible user ID")
    with_contacts: Optional[bool] = Field(default=False, description="Include linked contacts in response")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_leads",
    annotations={"title": "List Kommo Leads/Deals", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_leads(params: ListLeadsInput) -> str:
    """List leads/deals from Kommo CRM with optional filters and search.

    Fetches from GET /api/v4/leads.
    Returns lead ID, name, price, status, pipeline, and responsible user.

    Args:
        params: page, limit, query, pipeline_id, responsible_user_id, with_contacts

    Returns:
        str: List of leads with key fields.
    """
    try:
        p: Dict[str, Any] = {"page": params.page, "limit": params.limit}
        if params.query:
            p["query"] = params.query
        if params.pipeline_id:
            p["filter[pipeline_id][]"] = params.pipeline_id
        if params.responsible_user_id:
            p["filter[responsible_user_id][]"] = params.responsible_user_id
        if params.with_contacts:
            p["with"] = "contacts"

        data = await _get("/leads", p)

        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        leads = _embedded(data, "leads")
        if not leads:
            return "No leads found."

        total = data.get("_page_count", "?")
        lines = [f"## Kommo Leads (page {params.page}/{total})", ""]
        for lead in leads:
            lid = lead.get("id", "")
            name = lead.get("name", "")
            price = lead.get("price", 0)
            status = lead.get("status_id", "")
            pipeline = lead.get("pipeline_id", "")
            lines.append(f"- **#{lid}** {name} | {price} | pipeline: {pipeline} | status: {status}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetLeadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    lead_id: int = Field(..., description="Lead ID", gt=0)
    with_contacts: Optional[bool] = Field(default=True, description="Include linked contacts")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_get_lead",
    annotations={"title": "Get Kommo Lead Details", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_get_lead(params: GetLeadInput) -> str:
    """Get full details of a specific lead/deal from Kommo CRM.

    Fetches from GET /api/v4/leads/{id}.
    Returns all fields including custom fields, contacts, and pipeline info.

    Args:
        params: lead_id, with_contacts

    Returns:
        str: Full lead details.
    """
    try:
        p = {}
        if params.with_contacts:
            p["with"] = "contacts"
        data = await _get(f"/leads/{params.lead_id}", p)

        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        lines = [f"## Lead #{params.lead_id}: {data.get('name', '')}", ""]
        lines.append(f"**Price:** {data.get('price', 0)}")
        lines.append(f"**Pipeline:** {data.get('pipeline_id', '')}")
        lines.append(f"**Status:** {data.get('status_id', '')}")
        lines.append(f"**Responsible user:** {data.get('responsible_user_id', '')}")
        lines.append(f"**Created:** {data.get('created_at', '')}")
        lines.append(f"**Updated:** {data.get('updated_at', '')}")

        custom = data.get("custom_fields_values") or []
        if custom:
            lines.append("\n**Custom fields:**")
            for cf in custom:
                fname = cf.get("field_name", cf.get("field_id", ""))
                vals = [v.get("value", "") for v in (cf.get("values") or [])]
                lines.append(f"- {fname}: {', '.join(str(v) for v in vals)}")

        contacts = _embedded(data, "contacts")
        if contacts:
            lines.append("\n**Contacts:**")
            for c in contacts:
                lines.append(f"- #{c.get('id')} {c.get('name', '')}")

        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateLeadsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    leads: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "List of lead objects. Each can have: 'name' (required), 'price' (int), "
            "'pipeline_id' (int), 'status_id' (int), 'responsible_user_id' (int), "
            "'custom_fields_values' (list of {field_id, values: [{value}]})"
        )
    )


@mcp.tool(
    name="kommo_create_leads",
    annotations={"title": "Create Kommo Leads", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def kommo_create_leads(params: CreateLeadsInput) -> str:
    """Create one or more leads/deals in Kommo CRM.

    Posts to POST /api/v4/leads.
    Supports batch creation of multiple leads in one request.

    Args:
        params: leads — list of lead objects with name, price, pipeline_id, etc.

    Returns:
        str: Created lead IDs and details.
    """
    try:
        data = await _post("/leads", params.leads)
        leads = _embedded(data, "leads")
        if not leads:
            return f"Leads created.\n{_fmt(data)}"
        lines = ["## Created Leads", ""]
        for lead in leads:
            lines.append(f"- **#{lead.get('id')}** {lead.get('name', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class UpdateLeadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    lead_id: int = Field(..., description="Lead ID to update", gt=0)
    name: Optional[str] = Field(default=None, description="New lead name")
    price: Optional[int] = Field(default=None, description="New deal value")
    pipeline_id: Optional[int] = Field(default=None, description="New pipeline ID")
    status_id: Optional[int] = Field(default=None, description="New status ID (use kommo_list_pipeline_statuses)")
    responsible_user_id: Optional[int] = Field(default=None, description="New responsible user ID")
    custom_fields_values: Optional[List[Dict[str, Any]]] = Field(default=None, description="Custom fields to update")


@mcp.tool(
    name="kommo_update_lead",
    annotations={"title": "Update Kommo Lead", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_update_lead(params: UpdateLeadInput) -> str:
    """Update an existing lead/deal in Kommo CRM.

    Patches PATCH /api/v4/leads/{id}.

    Args:
        params: lead_id + fields to update

    Returns:
        str: Updated lead details or confirmation.
    """
    try:
        body: Dict[str, Any] = {}
        for field in ["name", "price", "pipeline_id", "status_id", "responsible_user_id", "custom_fields_values"]:
            val = getattr(params, field)
            if val is not None:
                body[field] = val
        data = await _patch(f"/leads/{params.lead_id}", body)
        return f"Lead #{params.lead_id} updated.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class DeleteLeadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    lead_id: int = Field(..., description="Lead ID to delete", gt=0)


@mcp.tool(
    name="kommo_delete_lead",
    annotations={"title": "Delete Kommo Lead", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
)
async def kommo_delete_lead(params: DeleteLeadInput) -> str:
    """Delete a lead/deal from Kommo CRM by ID.

    Sends DELETE to /api/v4/leads/{id}.

    Args:
        params: lead_id

    Returns:
        str: Confirmation or error.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.delete(
                f"{_base_url()}/leads/{params.lead_id}",
                headers=_headers(),
            )
            r.raise_for_status()
        return f"Lead #{params.lead_id} deleted successfully."
    except Exception as e:
        return _error(e)


class ListUnsortedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    page: Optional[int] = Field(default=1, ge=1)
    limit: Optional[int] = Field(default=20, ge=1, le=250)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_unsorted",
    annotations={"title": "List Kommo Unsorted Leads", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_unsorted(params: ListUnsortedInput) -> str:
    """List unsorted/incoming leads in Kommo CRM (leads not yet assigned to a pipeline).

    Fetches from GET /api/v4/leads/unsorted.

    Returns:
        str: List of unsorted leads with source info.
    """
    try:
        data = await _get("/leads/unsorted", {"page": params.page, "limit": params.limit})
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = _embedded(data, "unsorted")
        if not items:
            return "No unsorted leads found."
        lines = ["## Unsorted Leads", ""]
        for item in items:
            uid = item.get("uid", "")
            source = item.get("source_name") or item.get("category", "")
            created = item.get("created_at", "")
            lines.append(f"- **{uid}** | source: {source} | {created}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# CONTACTS
# ═══════════════════════════════════════════════════════════

class ListContactsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    page: Optional[int] = Field(default=1, ge=1)
    limit: Optional[int] = Field(default=20, ge=1, le=250)
    query: Optional[str] = Field(default=None, description="Search query (name, phone, email)")
    responsible_user_id: Optional[int] = Field(default=None, description="Filter by responsible user ID")
    with_leads: Optional[bool] = Field(default=False, description="Include linked leads in response")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_contacts",
    annotations={"title": "List Kommo Contacts", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_contacts(params: ListContactsInput) -> str:
    """List contacts from Kommo CRM with optional search and filters.

    Fetches from GET /api/v4/contacts.

    Args:
        params: page, limit, query, responsible_user_id, with_leads

    Returns:
        str: List of contacts with name, phone, email.
    """
    try:
        p: Dict[str, Any] = {"page": params.page, "limit": params.limit}
        if params.query:
            p["query"] = params.query
        if params.responsible_user_id:
            p["filter[responsible_user_id][]"] = params.responsible_user_id
        if params.with_leads:
            p["with"] = "leads"

        data = await _get("/contacts", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        contacts = _embedded(data, "contacts")
        if not contacts:
            return "No contacts found."

        lines = ["## Kommo Contacts", ""]
        for c in contacts:
            cid = c.get("id", "")
            name = c.get("name", "")
            custom = c.get("custom_fields_values") or []
            phone = email = ""
            for cf in custom:
                fname = (cf.get("field_name") or "").lower()
                vals = cf.get("values") or []
                val = vals[0].get("value", "") if vals else ""
                if "phone" in fname:
                    phone = val
                elif "email" in fname:
                    email = val
            lines.append(f"- **#{cid}** {name}" + (f" | {phone}" if phone else "") + (f" | {email}" if email else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetContactInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    contact_id: int = Field(..., description="Contact ID", gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_get_contact",
    annotations={"title": "Get Kommo Contact Details", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_get_contact(params: GetContactInput) -> str:
    """Get full details of a specific contact from Kommo CRM.

    Fetches from GET /api/v4/contacts/{id}.

    Args:
        params: contact_id

    Returns:
        str: Full contact details including all custom fields.
    """
    try:
        data = await _get(f"/contacts/{params.contact_id}", {"with": "leads,companies"})
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        lines = [f"## Contact #{params.contact_id}: {data.get('name', '')}", ""]
        lines.append(f"**Responsible:** {data.get('responsible_user_id', '')}")
        lines.append(f"**Created:** {data.get('created_at', '')}")

        custom = data.get("custom_fields_values") or []
        if custom:
            lines.append("\n**Fields:**")
            for cf in custom:
                fname = cf.get("field_name", cf.get("field_id", ""))
                vals = [v.get("value", "") for v in (cf.get("values") or [])]
                lines.append(f"- {fname}: {', '.join(str(v) for v in vals)}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateContactsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    contacts: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "List of contact objects. Each can have: 'name' (required), "
            "'responsible_user_id' (int), "
            "'custom_fields_values' (list of {field_id, values: [{value, enum_id?}]}). "
            "Example for phone: {field_id: 123, values: [{value: '+1234567890', enum_id: 1}]}"
        )
    )


@mcp.tool(
    name="kommo_create_contacts",
    annotations={"title": "Create Kommo Contacts", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def kommo_create_contacts(params: CreateContactsInput) -> str:
    """Create one or more contacts in Kommo CRM.

    Posts to POST /api/v4/contacts.

    Args:
        params: contacts — list of contact objects

    Returns:
        str: Created contact IDs.
    """
    try:
        data = await _post("/contacts", params.contacts)
        contacts = _embedded(data, "contacts")
        if not contacts:
            return f"Contacts created.\n{_fmt(data)}"
        lines = ["## Created Contacts", ""]
        for c in contacts:
            lines.append(f"- **#{c.get('id')}** {c.get('name', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class UpdateContactInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    contact_id: int = Field(..., description="Contact ID to update", gt=0)
    name: Optional[str] = Field(default=None, description="New name")
    responsible_user_id: Optional[int] = Field(default=None, description="New responsible user ID")
    custom_fields_values: Optional[List[Dict[str, Any]]] = Field(default=None, description="Custom fields to update")


@mcp.tool(
    name="kommo_update_contact",
    annotations={"title": "Update Kommo Contact", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_update_contact(params: UpdateContactInput) -> str:
    """Update an existing contact in Kommo CRM.

    Patches PATCH /api/v4/contacts/{id}.

    Args:
        params: contact_id + fields to update

    Returns:
        str: Updated contact details.
    """
    try:
        body: Dict[str, Any] = {}
        for field in ["name", "responsible_user_id", "custom_fields_values"]:
            val = getattr(params, field)
            if val is not None:
                body[field] = val
        data = await _patch(f"/contacts/{params.contact_id}", body)
        return f"Contact #{params.contact_id} updated.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# COMPANIES
# ═══════════════════════════════════════════════════════════

class ListCompaniesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    page: Optional[int] = Field(default=1, ge=1)
    limit: Optional[int] = Field(default=20, ge=1, le=250)
    query: Optional[str] = Field(default=None, description="Search query")
    responsible_user_id: Optional[int] = Field(default=None)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_companies",
    annotations={"title": "List Kommo Companies", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_companies(params: ListCompaniesInput) -> str:
    """List companies from Kommo CRM.

    Fetches from GET /api/v4/companies.

    Returns:
        str: List of companies with name and contact count.
    """
    try:
        p: Dict[str, Any] = {"page": params.page, "limit": params.limit}
        if params.query:
            p["query"] = params.query
        if params.responsible_user_id:
            p["filter[responsible_user_id][]"] = params.responsible_user_id

        data = await _get("/companies", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        companies = _embedded(data, "companies")
        if not companies:
            return "No companies found."

        lines = ["## Kommo Companies", ""]
        for c in companies:
            lines.append(f"- **#{c.get('id')}** {c.get('name', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetCompanyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    company_id: int = Field(..., description="Company ID", gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_get_company",
    annotations={"title": "Get Kommo Company Details", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_get_company(params: GetCompanyInput) -> str:
    """Get full details of a company from Kommo CRM.

    Fetches from GET /api/v4/companies/{id}.

    Returns:
        str: Full company details with custom fields.
    """
    try:
        data = await _get(f"/companies/{params.company_id}", {"with": "leads,contacts"})
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        lines = [f"## Company #{params.company_id}: {data.get('name', '')}", ""]
        custom = data.get("custom_fields_values") or []
        if custom:
            for cf in custom:
                fname = cf.get("field_name", cf.get("field_id", ""))
                vals = [v.get("value", "") for v in (cf.get("values") or [])]
                lines.append(f"**{fname}**: {', '.join(str(v) for v in vals)}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateCompaniesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    companies: List[Dict[str, Any]] = Field(
        ...,
        description="List of company objects. Each needs 'name' (required) and optionally 'responsible_user_id', 'custom_fields_values'."
    )


@mcp.tool(
    name="kommo_create_companies",
    annotations={"title": "Create Kommo Companies", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def kommo_create_companies(params: CreateCompaniesInput) -> str:
    """Create one or more companies in Kommo CRM.

    Posts to POST /api/v4/companies.

    Returns:
        str: Created company IDs.
    """
    try:
        data = await _post("/companies", params.companies)
        companies = _embedded(data, "companies")
        if not companies:
            return f"Companies created.\n{_fmt(data)}"
        lines = ["## Created Companies", ""]
        for c in companies:
            lines.append(f"- **#{c.get('id')}** {c.get('name', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class UpdateCompanyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    company_id: int = Field(..., description="Company ID to update", gt=0)
    name: Optional[str] = Field(default=None)
    responsible_user_id: Optional[int] = Field(default=None)
    custom_fields_values: Optional[List[Dict[str, Any]]] = Field(default=None)


@mcp.tool(
    name="kommo_update_company",
    annotations={"title": "Update Kommo Company", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_update_company(params: UpdateCompanyInput) -> str:
    """Update an existing company in Kommo CRM.

    Patches PATCH /api/v4/companies/{id}.

    Returns:
        str: Updated company details.
    """
    try:
        body: Dict[str, Any] = {}
        for field in ["name", "responsible_user_id", "custom_fields_values"]:
            val = getattr(params, field)
            if val is not None:
                body[field] = val
        data = await _patch(f"/companies/{params.company_id}", body)
        return f"Company #{params.company_id} updated.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# TASKS
# ═══════════════════════════════════════════════════════════

class ListTasksInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    page: Optional[int] = Field(default=1, ge=1)
    limit: Optional[int] = Field(default=20, ge=1, le=250)
    responsible_user_id: Optional[int] = Field(default=None, description="Filter by responsible user")
    is_completed: Optional[bool] = Field(default=None, description="Filter: True=completed, False=active")
    entity_id: Optional[int] = Field(default=None, description="Filter tasks linked to a specific lead/contact ID")
    entity_type: Optional[str] = Field(default=None, description="Entity type: 'leads' or 'contacts'")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_tasks",
    annotations={"title": "List Kommo Tasks", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_tasks(params: ListTasksInput) -> str:
    """List tasks from Kommo CRM with optional filters.

    Fetches from GET /api/v4/tasks.

    Args:
        params: page, limit, responsible_user_id, is_completed, entity_id, entity_type

    Returns:
        str: List of tasks with text, deadline, and linked entity.
    """
    try:
        p: Dict[str, Any] = {"page": params.page, "limit": params.limit}
        if params.responsible_user_id:
            p["filter[responsible_user_id][]"] = params.responsible_user_id
        if params.is_completed is not None:
            p["filter[is_completed]"] = 1 if params.is_completed else 0
        if params.entity_id and params.entity_type:
            p["filter[entity_id][]"] = params.entity_id
            p["filter[entity_type]"] = params.entity_type

        data = await _get("/tasks", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        tasks = _embedded(data, "tasks")
        if not tasks:
            return "No tasks found."

        lines = ["## Kommo Tasks", ""]
        for t in tasks:
            tid = t.get("id", "")
            text = t.get("text", "")
            deadline = t.get("complete_till", "")
            completed = "✅" if t.get("is_completed") else "⬜"
            entity = f"{t.get('entity_type', '')} #{t.get('entity_id', '')}"
            lines.append(f"- {completed} **#{tid}** {text} | до: {deadline} | {entity}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateTasksInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    tasks: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "List of task objects. Each needs: 'text' (required), "
            "'complete_till' (unix timestamp, required), "
            "'entity_id' (int), 'entity_type' ('leads' or 'contacts'), "
            "'responsible_user_id' (int), 'task_type_id' (int, default 1=call)"
        )
    )


@mcp.tool(
    name="kommo_create_tasks",
    annotations={"title": "Create Kommo Tasks", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def kommo_create_tasks(params: CreateTasksInput) -> str:
    """Create one or more tasks in Kommo CRM.

    Posts to POST /api/v4/tasks.

    Args:
        params: tasks — list of task objects with text, deadline, entity

    Returns:
        str: Created task IDs.
    """
    try:
        data = await _post("/tasks", params.tasks)
        tasks = _embedded(data, "tasks")
        if not tasks:
            return f"Tasks created.\n{_fmt(data)}"
        lines = ["## Created Tasks", ""]
        for t in tasks:
            lines.append(f"- **#{t.get('id')}** {t.get('text', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class UpdateTaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    task_id: int = Field(..., description="Task ID to update", gt=0)
    text: Optional[str] = Field(default=None, description="New task text")
    complete_till: Optional[int] = Field(default=None, description="New deadline as unix timestamp")
    responsible_user_id: Optional[int] = Field(default=None)
    is_completed: Optional[bool] = Field(default=None, description="Mark task as completed/uncompleted")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Completion result: {'text': 'Done'}")


@mcp.tool(
    name="kommo_update_task",
    annotations={"title": "Update Kommo Task", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_update_task(params: UpdateTaskInput) -> str:
    """Update or complete a task in Kommo CRM.

    Patches PATCH /api/v4/tasks/{id}.

    Args:
        params: task_id + fields to update (set is_completed=true to complete)

    Returns:
        str: Updated task details.
    """
    try:
        body: Dict[str, Any] = {}
        for field in ["text", "complete_till", "responsible_user_id", "is_completed", "result"]:
            val = getattr(params, field)
            if val is not None:
                body[field] = val
        data = await _patch(f"/tasks/{params.task_id}", body)
        return f"Task #{params.task_id} updated.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# NOTES
# ═══════════════════════════════════════════════════════════

class ListNotesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    entity_type: str = Field(..., description="Entity type: 'leads', 'contacts', or 'companies'")
    entity_id: Optional[int] = Field(default=None, description="Specific entity ID to get notes for")
    page: Optional[int] = Field(default=1, ge=1)
    limit: Optional[int] = Field(default=20, ge=1, le=250)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_notes",
    annotations={"title": "List Kommo Notes", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_notes(params: ListNotesInput) -> str:
    """List notes for leads, contacts, or companies in Kommo CRM.

    Fetches from GET /api/v4/{entity_type}/notes.

    Args:
        params: entity_type ('leads'/'contacts'/'companies'), entity_id, page, limit

    Returns:
        str: List of notes with text and timestamps.
    """
    try:
        p: Dict[str, Any] = {"page": params.page, "limit": params.limit}
        if params.entity_id:
            p["filter[entity_id][]"] = params.entity_id

        data = await _get(f"/{params.entity_type}/notes", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        notes = _embedded(data, "notes")
        if not notes:
            return "No notes found."

        lines = [f"## Notes for {params.entity_type}", ""]
        for n in notes:
            nid = n.get("id", "")
            ntype = n.get("note_type", "")
            params_data = n.get("params", {})
            text = params_data.get("text", "") or params_data.get("note", "")
            created = n.get("created_at", "")
            lines.append(f"- **#{nid}** [{ntype}] {text[:100]} | {created}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class AddNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    entity_type: str = Field(..., description="Entity type: 'leads', 'contacts', or 'companies'")
    entity_id: int = Field(..., description="Entity ID to attach note to", gt=0)
    text: str = Field(..., description="Note text content", min_length=1)
    note_type: Optional[str] = Field(default="common", description="Note type: 'common' (default), 'call_in', 'call_out', 'service_message'")


@mcp.tool(
    name="kommo_add_note",
    annotations={"title": "Add Note to Kommo Entity", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def kommo_add_note(params: AddNoteInput) -> str:
    """Add a note to a lead, contact, or company in Kommo CRM.

    Posts to POST /api/v4/{entity_type}/notes.

    Args:
        params: entity_type, entity_id, text, note_type

    Returns:
        str: Created note ID and confirmation.
    """
    try:
        body = [{
            "entity_id": params.entity_id,
            "note_type": params.note_type or "common",
            "params": {"text": params.text},
        }]
        data = await _post(f"/{params.entity_type}/notes", body)
        notes = _embedded(data, "notes")
        if notes:
            return f"Note #{notes[0].get('id')} added to {params.entity_type} #{params.entity_id}."
        return f"Note added.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# PIPELINES & STAGES
# ═══════════════════════════════════════════════════════════

class PipelinesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_pipelines",
    annotations={"title": "List Kommo Sales Pipelines", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_pipelines(params: PipelinesInput) -> str:
    """List all sales pipelines in Kommo CRM.

    Fetches from GET /api/v4/leads/pipelines.
    Returns pipeline IDs and names needed for lead creation/filtering.

    Returns:
        str: List of pipelines with IDs and names.
    """
    try:
        data = await _get("/leads/pipelines")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        pipelines = _embedded(data, "pipelines")
        if not pipelines:
            return "No pipelines found."

        lines = ["## Kommo Pipelines", ""]
        for p in pipelines:
            lines.append(f"- **#{p.get('id')}** {p.get('name', '')} (is_main: {p.get('is_main', False)})")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class ListStatusesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pipeline_id: int = Field(..., description="Pipeline ID (use kommo_list_pipelines to get IDs)", gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_pipeline_statuses",
    annotations={"title": "List Kommo Pipeline Statuses/Stages", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_pipeline_statuses(params: ListStatusesInput) -> str:
    """List all statuses/stages of a specific pipeline in Kommo CRM.

    Fetches from GET /api/v4/leads/pipelines/{id}/statuses.
    Returns status IDs and names needed for lead updates.

    Args:
        params: pipeline_id

    Returns:
        str: List of stages with IDs, names, and colors.
    """
    try:
        data = await _get(f"/leads/pipelines/{params.pipeline_id}/statuses")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        statuses = _embedded(data, "statuses")
        if not statuses:
            return f"No statuses found for pipeline #{params.pipeline_id}."

        lines = [f"## Pipeline #{params.pipeline_id} Statuses", ""]
        for s in statuses:
            lines.append(f"- **#{s.get('id')}** {s.get('name', '')} | sort: {s.get('sort', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════

class UsersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_list_users",
    annotations={"title": "List Kommo Users", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_list_users(params: UsersInput) -> str:
    """List all users in the Kommo CRM account.

    Fetches from GET /api/v4/users.
    Returns user IDs, names, emails, and roles needed for responsible_user_id fields.

    Returns:
        str: List of users.
    """
    try:
        data = await _get("/users")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        users = _embedded(data, "users")
        if not users:
            return "No users found."

        lines = ["## Kommo Users", ""]
        for u in users:
            uid = u.get("id", "")
            name = u.get("name", "")
            email = u.get("email", "")
            role = u.get("role", {})
            role_name = role.get("name", "") if isinstance(role, dict) else ""
            lines.append(f"- **#{uid}** {name} | {email}" + (f" | {role_name}" if role_name else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetUserInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: int = Field(..., description="User ID", gt=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="kommo_get_user",
    annotations={"title": "Get Kommo User Details", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def kommo_get_user(params: GetUserInput) -> str:
    """Get details of a specific user in Kommo CRM.

    Fetches from GET /api/v4/users/{id}.

    Returns:
        str: User details with role and permissions.
    """
    try:
        data = await _get(f"/users/{params.user_id}")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)

        lines = [f"## User #{params.user_id}: {data.get('name', '')}", ""]
        lines.append(f"**Email:** {data.get('email', '')}")
        lines.append(f"**Lang:** {data.get('lang', '')}")
        role = data.get("role", {})
        if isinstance(role, dict):
            lines.append(f"**Role:** #{role.get('id')} {role.get('name', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# CUSTOM FIELDS
# ═══════════════════════════════════════════════════════════

class KommoListCustomFieldsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: str = Field(
        description="Entity type: leads, contacts, companies, customers, segments, catalog_elements"
    )
    response_format: str = Field(default="markdown", description="'markdown' or 'json'")


@mcp.tool(
    name="kommo_list_custom_fields",
    description="List all custom fields defined for a given entity type (leads, contacts, companies, etc.) in Kommo CRM.",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def kommo_list_custom_fields(params: KommoListCustomFieldsInput) -> str:
    try:
        url = f"{_base_url()}/leads/custom_fields"
        entity_map = {
            "leads": "leads",
            "contacts": "contacts",
            "companies": "companies",
            "customers": "customers",
            "segments": "segments",
            "catalog_elements": "catalog_elements",
        }
        entity = entity_map.get(params.entity_type.lower(), params.entity_type.lower())
        url = f"{_base_url()}/{entity}/custom_fields"

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=_headers())
            r.raise_for_status()
            data = r.json()

        fields = _embedded(data, "custom_fields")

        if params.response_format == "json":
            return json.dumps({"entity_type": entity, "custom_fields": fields, "count": len(fields)}, ensure_ascii=False, indent=2)

        if not fields:
            return f"No custom fields found for entity type '{entity}'."

        lines = [f"## Custom Fields — {entity} ({len(fields)} total)\n"]
        for f in fields:
            ftype = f.get("type", "unknown")
            fid = f.get("id", "")
            fname = f.get("name", "")
            code = f.get("code", "")
            required = "✅ required" if f.get("is_required") else ""
            enums = f.get("enums", [])
            lines.append(f"- **{fname}** (ID: {fid}, type: `{ftype}`{', code: ' + code if code else ''}) {required}")
            if enums:
                enum_vals = ", ".join(str(e.get("value", e)) for e in enums[:5])
                if len(enums) > 5:
                    enum_vals += f" ... +{len(enums)-5} more"
                lines.append(f"  Values: {enum_vals}")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        if isinstance(e, ValueError):
            return f"Config error: {e}"
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
# TAGS
# ═══════════════════════════════════════════════════════════

class KommoListTagsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: str = Field(
        default="leads",
        description="Entity type: leads, contacts, companies"
    )
    limit: int = Field(default=50, ge=1, le=250, description="Results per page (max 250)")
    page: int = Field(default=1, ge=1, description="Page number")
    response_format: str = Field(default="markdown", description="'markdown' or 'json'")


@mcp.tool(
    name="kommo_list_tags",
    description="List all tags available for a given entity type (leads, contacts, companies) in Kommo CRM.",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def kommo_list_tags(params: KommoListTagsInput) -> str:
    try:
        url = f"{_base_url()}/{params.entity_type}/tags"
        query: Dict[str, Any] = {"limit": params.limit, "page": params.page}

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=_headers(), params=query)
            r.raise_for_status()
            data = r.json()

        tags = _embedded(data, "tags")

        if params.response_format == "json":
            return json.dumps({"entity_type": params.entity_type, "page": params.page, "tags": tags, "count": len(tags)}, ensure_ascii=False, indent=2)

        if not tags:
            return f"No tags found for entity type '{params.entity_type}'."

        lines = [f"## Tags — {params.entity_type} (page {params.page}, {len(tags)} items)\n"]
        for t in tags:
            tid = t.get("id", "")
            tname = t.get("name", "")
            color = t.get("color", "")
            lines.append(f"- **{tname}** (ID: {tid}{', color: ' + color if color else ''})")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        if isinstance(e, ValueError):
            return f"Config error: {e}"
        return f"Error: {e}"


class KommoCreateTagsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: str = Field(
        default="leads",
        description="Entity type: leads, contacts, companies"
    )
    tag_names: List[str] = Field(description="List of tag names to create")
    response_format: str = Field(default="markdown", description="'markdown' or 'json'")


@mcp.tool(
    name="kommo_create_tags",
    description="Create one or more new tags for a given entity type in Kommo CRM.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def kommo_create_tags(params: KommoCreateTagsInput) -> str:
    try:
        url = f"{_base_url()}/{params.entity_type}/tags"
        body = [{"name": name} for name in params.tag_names]

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=_headers(), json=body)
            r.raise_for_status()
            data = r.json()

        created = _embedded(data, "tags")

        if params.response_format == "json":
            return json.dumps({"created": created, "count": len(created)}, ensure_ascii=False, indent=2)

        lines = [f"## Created {len(created)} tag(s) for {params.entity_type}\n"]
        for t in created:
            lines.append(f"- **{t.get('name', '')}** (ID: {t.get('id', '')})")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        if isinstance(e, ValueError):
            return f"Config error: {e}"
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════

class KommoListEventsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter_entity: Optional[str] = Field(default=None, description="Entity type filter: leads, contacts, companies")
    filter_entity_id: Optional[int] = Field(default=None, description="Entity ID to filter events for")
    filter_types: Optional[List[str]] = Field(default=None, description="Event types to filter (e.g. lead_added, contact_added)")
    limit: int = Field(default=20, ge=1, le=100, description="Results per page")
    page: int = Field(default=1, ge=1, description="Page number")
    response_format: str = Field(default="markdown", description="'markdown' or 'json'")


@mcp.tool(
    name="kommo_list_events",
    description="List account events (activity feed) in Kommo CRM. Can be filtered by entity type, entity ID, or event type.",
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
async def kommo_list_events(params: KommoListEventsInput) -> str:
    try:
        url = f"{_base_url()}/events"
        query: Dict[str, Any] = {"limit": params.limit, "page": params.page}

        if params.filter_entity and params.filter_entity_id:
            query[f"filter[entity]"] = params.filter_entity
            query[f"filter[entity_id][]"] = params.filter_entity_id
        elif params.filter_entity:
            query["filter[entity]"] = params.filter_entity

        if params.filter_types:
            for i, t in enumerate(params.filter_types):
                query[f"filter[type][{i}]"] = t

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=_headers(), params=query)
            r.raise_for_status()
            data = r.json()

        events = _embedded(data, "events")

        if params.response_format == "json":
            return json.dumps({"page": params.page, "events": events, "count": len(events)}, ensure_ascii=False, indent=2)

        if not events:
            return "No events found for the given filters."

        lines = [f"## Events (page {params.page}, {len(events)} items)\n"]
        for ev in events:
            eid = ev.get("id", "")
            etype = ev.get("type", "")
            created_at = ev.get("created_at", "")
            created_by = ev.get("created_by", "")
            entity_id = ev.get("entity_id", "")
            entity_type = ev.get("entity_type", "")

            ts = ""
            if created_at:
                from datetime import datetime
                try:
                    ts = datetime.utcfromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts = str(created_at)

            lines.append(f"- **{etype}** (ID: {eid}) | {entity_type} #{entity_id} | {ts} | by user {created_by}")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        if isinstance(e, ValueError):
            return f"Config error: {e}"
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
# CALLS
# ═══════════════════════════════════════════════════════════

class KommoAddCallInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: str = Field(description="Call direction: 'inbound' or 'outbound'")
    duration: int = Field(ge=0, description="Call duration in seconds")
    source: str = Field(description="Call source/name (e.g. 'Telephony', 'Zadarma')")
    phone: str = Field(description="Phone number involved in the call")
    call_status: int = Field(
        description="Call status: 1=left voicemail, 2=missed, 3=called back, 4=successful, 5=not reached, 6=wrong number"
    )
    created_at: Optional[int] = Field(default=None, description="Unix timestamp of call. Defaults to current time.")
    link: Optional[str] = Field(default=None, description="URL to call recording (mp3/wav)")
    uniq: Optional[str] = Field(default=None, description="Unique call identifier to prevent duplicates")
    response_format: str = Field(default="markdown", description="'markdown' or 'json'")


@mcp.tool(
    name="kommo_add_call",
    description="Add a call record to Kommo CRM. The system will automatically match the phone number to an existing contact or lead.",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def kommo_add_call(params: KommoAddCallInput) -> str:
    try:
        import time
        url = f"{_base_url()}/calls"
        body: Dict[str, Any] = {
            "direction": params.direction,
            "duration": params.duration,
            "source": params.source,
            "phone": params.phone,
            "call_status": params.call_status,
            "created_at": params.created_at or int(time.time()),
        }
        if params.link:
            body["link"] = params.link
        if params.uniq:
            body["uniq"] = params.uniq

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers=_headers(), json=[body])
            r.raise_for_status()
            data = r.json()

        calls = _embedded(data, "calls")

        if params.response_format == "json":
            return json.dumps({"created_calls": calls}, ensure_ascii=False, indent=2)

        lines = [f"## Call Added Successfully\n"]
        for c in calls:
            lines.append(f"- **ID**: {c.get('id', '')}")
            lines.append(f"- **Direction**: {params.direction}")
            lines.append(f"- **Phone**: {params.phone}")
            lines.append(f"- **Duration**: {params.duration}s")
            lines.append(f"- **Status**: {params.call_status}")
            if params.link:
                lines.append(f"- **Recording**: {params.link}")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {e.response.text}"
    except Exception as e:
        if isinstance(e, ValueError):
            return f"Config error: {e}"
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
