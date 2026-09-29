from flask import request
from flask_restful import Resource
from models import User, Tenant, ShopSettings
from extensions import db, limiter
from flask_jwt_extended import create_access_token, create_refresh_token


class LoginResource(Resource):
    @limiter.limit("5 per minute")
    def post(self):
        data     = request.get_json() or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        # Optional: a shop slug to disambiguate when the same username
        # exists in more than one shop (e.g. every shop has an "admin").
        shop_slug = (data.get("shop") or data.get("shop_slug") or "").strip()

        if not username or not password:
            return {"error": "Username and password are required."}, 400

        # ── Resolve the user within a tenant ──────────────────────────────
        # SECURITY: usernames are unique PER TENANT, not globally. So a plain
        # filter_by(username=...) can match multiple shops' users. We must
        # scope the lookup. If a shop slug is provided, use it; otherwise we
        # match the username and, only if EXACTLY ONE user has it, log in.
        # If the same username exists in multiple shops and no slug is given,
        # we refuse rather than guess — never log into the wrong shop.
        if shop_slug:
            tenant = Tenant.query.filter_by(slug=shop_slug, is_active=True).first()
            if not tenant:
                # Generic message — don't reveal whether the shop exists
                return {"error": "Invalid credentials."}, 401
            user = User.query.filter_by(
                tenant_id=tenant.id, username=username
            ).first()
        else:
            matches = User.query.filter_by(username=username).all()
            if len(matches) > 1:
                # Ambiguous — the same username lives in multiple shops.
                return {
                    "error": "Multiple shops use this username. Please include your shop.",
                    "needs_shop": True,
                }, 409
            user = matches[0] if matches else None

        # 1. User must exist
        if not user:
            return {"error": "Invalid username or password."}, 401

        # 2. The shop itself must be active (suspended shops can't log in)
        if not user.tenant or not user.tenant.is_active:
            return {"message": "This shop is not active. Contact support."}, 403

        # 3. The user account must be active
        if not user.active:
            return {"message": "Account deactivated. Contact Admin."}, 403

        # 4. Verify password (constant-time compare inside check_password)
        if not user.check_password(password):
            return {"error": "Invalid username or password."}, 401

        # ── Issue tokens ──────────────────────────────────────────────────
        # SECURITY: tenant_id is baked into the SIGNED JWT. Every request
        # reads it from the token, never from the request body/params, so a
        # client cannot forge or switch tenants.
        additional_claims = {
            "role":      user.role,
            "tenant_id": user.tenant_id,
        }
        access_token  = create_access_token(
            identity=str(user.id),
            additional_claims=additional_claims,
        )
        # The refresh token also carries tenant_id so refreshed access tokens
        # keep the tenant binding.
        refresh_token = create_refresh_token(
            identity=str(user.id),
            additional_claims=additional_claims,
        )

        return {
            "message":       "Login successful",
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "user":          user.to_dict(),
            "shop": {
                "id":   user.tenant_id,
                "name": user.tenant.name if user.tenant else None,
                "slug": user.tenant.slug if user.tenant else None,
            },
        }, 200


class RegisterResource(Resource):
    """
    Public self-registration is DISABLED under multi-tenancy.
    Creating a user now requires a tenant context — new shops are created
    through /onboard, and new staff are created by their shop's admin through
    the tenant-scoped /users endpoint. Leaving an open /register that guesses
    a tenant would be a security hole (which shop would the user belong to?).
    """
    def post(self):
        return {
            "message": "Direct registration is disabled. "
                       "Use /onboard to create a shop, or ask your admin to add you."
        }, 405