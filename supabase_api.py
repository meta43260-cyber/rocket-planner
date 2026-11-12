"""Supabase REST integration for Rocket Planner.

Uses the public anon key plus the caller's Supabase access token.
Never place a service-role key in the browser or this application.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rocket-database"])


class SupabaseConfigError(RuntimeError):
    pass


class SupabaseREST:
    def __init__(self, access_token: str | None = None):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        if not self.url or not self.anon_key:
            raise HTTPException(
                status_code=503,
                detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY."
            )
        self.access_token = access_token or self.anon_key

    def call(self, path: str, *, method: str = "GET", body=None, prefer=None):
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if prefer:
            headers["Prefer"] = prefer
        try:
            # Keep request construction inside the guarded block so malformed
            # configuration is reported as a diagnostic response, not a 500.
            req = Request(f"{self.url}{path}", data=data, headers=headers, method=method)
            with urlopen(req, timeout=15) as response:
                raw = response.read()
                if not raw:
                    return None
                try:
                    return json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    logger.error("Supabase returned a non-JSON response for %s %s (content-type=%s, bytes=%d)",
                                 method, path, response.headers.get("Content-Type", "unknown"), len(raw))
                    raise HTTPException(status_code=502, detail="Supabase returned an invalid response.") from exc
        except HTTPError as exc:
            # Do not relay provider internals or tokens to the public client.
            if exc.code in (401, 403):
                raise HTTPException(status_code=403, detail="Supabase denied this operation.") from exc
            if exc.code == 404:
                raise HTTPException(status_code=404, detail="Rocket record not found.") from exc
            raise HTTPException(status_code=502, detail=f"Supabase request failed ({exc.code}).") from exc
        except (URLError, TimeoutError) as exc:
            logger.warning("Supabase connection failed for %s %s: %s", method, path, type(exc).__name__)
            raise HTTPException(status_code=503, detail="Supabase is temporarily unreachable.") from exc
        except HTTPException:
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            logger.exception("Unexpected Supabase REST failure for %s %s (%s)", method, path, error_type)
            # The exception class is safe to show; never expose exception text,
            # request headers, URLs with credentials, or Supabase response bodies.
            raise HTTPException(
                status_code=502,
                detail=f"Supabase request could not be processed (diagnostic: {error_type})."
            ) from exc


def _rows(client: SupabaseREST, table: str, query: dict[str, str] | None = None):
    suffix = "?" + urlencode(query or {}, safe="*,().=<>") if query else ""
    result = client.call(f"/rest/v1/{table}{suffix}")
    if not isinstance(result, list):
        raise HTTPException(status_code=502, detail=f"Unexpected response from {table}.")
    return result


def _published_catalog(client: SupabaseREST):
    rockets = _rows(client, "rockets")
    versions = _rows(client, "rocket_versions", {
        "status": "eq.published", "is_current": "eq.true"
    })
    version_by_rocket = {str(v.get("rocket_id")): v for v in versions}
    current = [r for r in rockets if str(r.get("id")) in version_by_rocket]
    version_ids = [str(version_by_rocket[str(r.get("id"))].get("id")) for r in current]
    if not version_ids:
        return []
    in_filter = "in.(" + ",".join(version_ids) + ")"
    stages = _rows(client, "rocket_stages", {"version_id": in_filter})
    boosters = _rows(client, "rocket_boosters", {"version_id": in_filter})
    sources = _rows(client, "rocket_sources", {"version_id": in_filter})
    result = []
    for rocket in current:
        version = version_by_rocket[str(rocket.get("id"))]
        vid = str(version.get("id"))
        result.append({
            **rocket,
            "current_version": {
                **version,
                "stages": [x for x in stages if str(x.get("version_id")) == vid],
                "boosters": [x for x in boosters if str(x.get("version_id")) == vid],
                "sources": [x for x in sources if str(x.get("version_id")) == vid],
            },
        })
    return result


def _require_admin(client: SupabaseREST):
    user = client.call("/auth/v1/user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Please sign in with your admin account.")
    admins = _rows(client, "admin_users", {
        "user_id": f"eq.{user_id}", "is_active": "eq.true", "select": "user_id"
    })
    if not admins:
        raise HTTPException(status_code=403, detail="This account is not an active Rocket Planner admin.")
    return user


def _client(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization bearer token required.")
    return SupabaseREST(authorization.split(" ", 1)[1].strip())


@router.get("/public/rockets")
def public_rockets():
    return _published_catalog(SupabaseREST())


@router.get("/public/rockets/export.json")
def export_rockets_json():
    payload = json.dumps(_published_catalog(SupabaseREST()), ensure_ascii=False, indent=2)
    return Response(payload, media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="rockets.json"'})


@router.get("/public/rockets/export.csv")
def export_rockets_csv():
    rows = _published_catalog(SupabaseREST())
    output = io.StringIO()
    fields = ["name", "slug", "manufacturer", "country", "rocket_family", "version"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in rows:
        version = item.get("current_version") or {}
        writer.writerow({**item, "version": version.get("version") or version.get("version_number")})
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="rockets.csv"'})


@router.get("/public/rockets/{slug}")
def public_rocket_detail(slug: str):
    for rocket in _published_catalog(SupabaseREST()):
        if rocket.get("slug") == slug:
            return rocket
    raise HTTPException(status_code=404, detail="Published rocket not found.")


@router.get("/admin/me")
def admin_me(authorization: str | None = Header(default=None)):
    client = _client(authorization)
    user = _require_admin(client)
    return {"authenticated": True, "is_admin": True, "user": {
        "id": user.get("id"), "email": user.get("email")
    }}


@router.get("/admin/rockets")
def admin_rockets(authorization: str | None = Header(default=None)):
    client = _client(authorization)
    _require_admin(client)
    return {
        "rockets": _rows(client, "rockets"),
        "versions": _rows(client, "rocket_versions"),
    }


from fastapi import Body


def _admin_client(authorization: str | None):
    client = _client(authorization)
    _require_admin(client)
    return client


def _insert(client: SupabaseREST, table: str, payload: dict):
    result = client.call(f"/rest/v1/{table}", method="POST", body=payload,
                         prefer="return=representation")
    return result[0] if isinstance(result, list) and result else result


def _update(client: SupabaseREST, table: str, row_id: str, payload: dict):
    query = urlencode({"id": f"eq.{row_id}"})
    result = client.call(f"/rest/v1/{table}?{query}", method="PATCH",
                         body=payload, prefer="return=representation")
    if not result:
        raise HTTPException(status_code=404, detail="Record not found or not editable.")
    return result[0] if isinstance(result, list) else result


@router.post("/admin/rockets")
def create_rocket(payload: dict = Body(...), authorization: str | None = Header(default=None)):
    client = _admin_client(authorization)
    return _insert(client, "rockets", payload)


@router.patch("/admin/rockets/{rocket_id}")
def update_rocket(rocket_id: str, payload: dict = Body(...),
                  authorization: str | None = Header(default=None)):
    client = _admin_client(authorization)
    return _update(client, "rockets", rocket_id, payload)


@router.post("/admin/rockets/{rocket_id}/versions")
def create_draft_version(rocket_id: str, payload: dict = Body(...),
                         authorization: str | None = Header(default=None)):
    client = _admin_client(authorization)
    draft = {**payload, "rocket_id": rocket_id, "status": "draft", "is_current": False}
    return _insert(client, "rocket_versions", draft)


@router.patch("/admin/versions/{version_id}")
def update_draft_version(version_id: str, payload: dict = Body(...),
                          authorization: str | None = Header(default=None)):
    client = _admin_client(authorization)
    if "status" in payload or "is_current" in payload:
        raise HTTPException(status_code=400, detail="Use the Publish action to change revision status.")
    return _update(client, "rocket_versions", version_id, payload)


@router.post("/admin/versions/{version_id}/publish")
def publish_version(version_id: str, authorization: str | None = Header(default=None)):
    client = _admin_client(authorization)
    return client.call("/rest/v1/rpc/publish_rocket_version", method="POST",
                       body={"p_version_id": version_id})


@router.post("/admin/versions/{version_id}/{child_table}")
def add_version_child(version_id: str, child_table: str, payload: dict = Body(...),
                      authorization: str | None = Header(default=None)):
    client = _admin_client(authorization)
    if child_table not in {"rocket_stages", "rocket_boosters", "rocket_sources"}:
        raise HTTPException(status_code=404, detail="Unsupported revision data type.")
    return _insert(client, child_table, {**payload, "version_id": version_id})


@router.post("/admin/login")
def admin_login(credentials: dict = Body(...)):
    email = str(credentials.get("email", "")).strip()
    password = credentials.get("password")
    if not email or not isinstance(password, str) or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
    client = SupabaseREST()
    try:
        session = client.call("/auth/v1/token?grant_type=password", method="POST",
                              body={"email": email, "password": password})
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            raise HTTPException(status_code=401, detail="Email or password is incorrect.") from exc
        raise
    if not isinstance(session, dict) or not session.get("access_token"):
        raise HTTPException(status_code=401, detail="Supabase did not return a valid session.")
    verified = SupabaseREST(session["access_token"])
    user = _require_admin(verified)
    return {"access_token": session["access_token"],
            "refresh_token": session.get("refresh_token"),
            "expires_in": session.get("expires_in"),
            "user": {"id": user.get("id"), "email": user.get("email")}}
