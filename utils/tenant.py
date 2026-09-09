# utils/tenant.py
from flask_jwt_extended import get_jwt


def get_tenant_id():
    """Extract tenant_id from JWT — used in every resource."""
    claims = get_jwt()
    return claims.get("tenant_id")


def get_role():
    """Extract role from JWT."""
    claims = get_jwt()
    return claims.get("role")


def is_admin_role():
    return get_role() == "admin"