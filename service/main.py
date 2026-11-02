"""The REST layer (interface IF-8) and the dashboard page, on http://localhost:8000.

    GET  /               the dashboard (dashboard/index.html)
    GET  /register       the sign-up page for phone alerts (dashboard/register.html)
    GET  /api/latest     what to show and sound now: state, CO2, link, last acknowledgement
    GET  /api/readings   ?seconds=600: [[time, ppm, display], ...] for the trend
    GET  /api/alarms     ?limit=20: the alarm log, newest first, with acknowledgements and messages
    POST /api/ack        {"who": "AM"}: acknowledge from the dashboard
    GET  /api/users      the people signed up for phone alerts (never their keys, only the end of
                         their number)
    POST /api/users      sign up: {"name", "role", "channel", "phone", "apikey" | "telegram",
                         "level", "consent": true}; sends a test message
    POST /api/users/<id>/test, /stop, /start
    GET  /api/notifications  ?limit=20: the latest messages and how they went
    GET  /api/health     {"ok": true} while the service runs

Flask (one of the two web frameworks the project card lists) with its built-in server: one laptop,
one browser, localhost only unless started with --lan.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, request, send_from_directory

from .core import ROOT

DASHBOARD = os.path.join(ROOT, "dashboard")


def create_app(service) -> Flask:
    app = Flask(__name__, static_folder=None)

    @app.after_request
    def no_cache(resp):
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/")
    def dashboard():
        return send_from_directory(DASHBOARD, "index.html")

    @app.get("/register")
    def register_page():
        return send_from_directory(DASHBOARD, "register.html")

    @app.get("/dashboard/<path:name>")
    def dashboard_files(name):
        return send_from_directory(DASHBOARD, name)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/latest")
    def latest():
        return jsonify(service.latest())

    @app.get("/api/readings")
    def readings():
        try:
            seconds = float(request.args.get("seconds", 600))
        except ValueError:
            seconds = 600.0
        seconds = min(max(seconds, 10.0), 3600.0)
        return jsonify({"seconds": seconds, "points": service.readings(seconds)})

    @app.get("/api/alarms")
    def alarms():
        try:
            limit = int(request.args.get("limit", 20))
        except ValueError:
            limit = 20
        return jsonify({"alarms": service.alarms(min(max(limit, 1), 200)), "phones": service.phones()})

    @app.post("/api/ack")
    def ack():
        body = request.get_json(silent=True) or {}
        r = service.ack(str(body.get("who", "")))
        return jsonify(r), (200 if r["ok"] else 409)

    @app.get("/api/users")
    def users():
        return jsonify(service.people())

    @app.post("/api/users")
    def signup():
        body = request.get_json(silent=True)
        code, r = service.signup(body if isinstance(body, dict) else {})
        return jsonify(r), code

    @app.post("/api/users/<int:user_id>/test")
    def user_test(user_id):
        code, r = service.send_test(user_id)
        return jsonify(r), code

    @app.post("/api/users/<int:user_id>/stop")
    def user_stop(user_id):
        code, r = service.set_active(user_id, False)
        return jsonify(r), code

    @app.post("/api/users/<int:user_id>/start")
    def user_start(user_id):
        code, r = service.set_active(user_id, True)
        return jsonify(r), code

    @app.get("/api/notifications")
    def notifications():
        try:
            limit = int(request.args.get("limit", 20))
        except ValueError:
            limit = 20
        return jsonify({"notifications": service.store.notifications(min(max(limit, 1), 200))})

    return app
