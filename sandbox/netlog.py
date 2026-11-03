"""Reads Chromium's --log-net-log JSON: every URL the rendered page tried to load, and how it ended.

Used inside the room after a headless-Chromium preview. These are the renderer's own records, made inside the room;
we never make a network attempt ourselves.
"""
import json

# Chromium's traffic-annotation hash for "blink_resource_loader": requests the rendered page made (images, fetch, XHR).
# Everything else in the log is the browser's own housekeeping (updates, time sync), which the room disables anyway.
BLINK_LOADER = 101845102


def attempts(path, skip_schemes=("file:", "data:", "about:", "chrome:", "blob:")):
    with open(path) as f:
        d = json.load(f)
    c = d.get("constants", {})
    ev_name = {v: k for k, v in c.get("logEventTypes", {}).items()}
    src_name = {v: k for k, v in c.get("logSourceType", {}).items()}
    err_name = {v: k for k, v in c.get("netError", {}).items()}
    reqs = {}
    for e in d.get("events", []):
        if src_name.get(e["source"]["type"]) != "URL_REQUEST":
            continue
        sid, p = e["source"]["id"], e.get("params") or {}
        r = reqs.setdefault(sid, {"url": None, "error": None, "page": False})
        if p.get("traffic_annotation") == BLINK_LOADER:
            r["page"] = True      # loaded by the document itself, not the browser's own housekeeping
        if ev_name.get(e["type"]) == "REQUEST_ALIVE" and "url" in p and r["url"] is None:
            r["url"] = p["url"]
        if "net_error" in p and p["net_error"] != 0:
            r["error"] = p["net_error"]
    out, seen = [], set()
    for r in reqs.values():
        u = r["url"]
        if not u or not r["page"] or u.startswith(skip_schemes) or u in seen:
            continue
        seen.add(u)
        code = r["error"]
        out.append({"url": u, "error": err_name.get(code, str(code) if code is not None else "none")})
    return out
