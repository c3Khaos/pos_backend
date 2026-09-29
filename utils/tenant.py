# utils/tenant.py
# ═════════════════════════════════════════════════════════════════════════════
# The single source of truth for "which tenant is this request for?"
#
# SECURITY — the whole isolation model rests on this file:
#   tenant_id is read ONLY from the signed JWT claims, never from the URL,
#   query string, or request body. A client cannot forge or switch tenants
#   because they cannot mint a validly-signed token with a different tenant_id.
# ═════════════════════════════════════════════════════════════════════════════
from flask_jwt_extended import get_jwt, get_jwt_identity
from models import User


def get_tenant_id():
    """
    Return the tenant_id for the current request, taken from the JWT claims.
    Returns None if there is no valid tenant claim (caller should treat that
    as unauthorized).
    """
    claims = get_jwt()
    return claims.get("tenant_id")


def get_role():
    """Return the role claim from the JWT ('admin' | 'user')."""
    claims = get_jwt()
    return claims.get("role")


def current_user_and_tenant():
    """
    Resolve the User for the current JWT AND verify they still belong to the
    tenant in the token. This is a defense-in-depth check: even if a token's
    tenant_id claim were somehow stale, we confirm the user row agrees.

    Returns (user, tenant_id) or (None, tenant_id) if the user can't be
    validated for that tenant.
    """
    tenant_id = get_tenant_id()
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None, tenant_id

    if tenant_id is None:
        return None, None

    user = User.query.filter_by(id=user_id, tenant_id=tenant_id).first()
    return user, tenant_id


def is_admin():
    """
    True only if the current user is an active admin of the tenant in the JWT.
    Verifies against the DB row, not just the token claim, so a demoted or
    deactivated admin loses access immediately.
    """
    user, _ = current_user_and_tenant()
    return bool(user and user.active and user.role == "admin")