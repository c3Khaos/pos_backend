from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import db, User
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


class UserListResource(Resource):

    @jwt_required()
    def get(self):
        # ── SECURITY: only admins list users, and only their OWN shop's ───
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        users = User.query.filter_by(tenant_id=tenant_id).all()
        return [u.to_dict() for u in users], 200

    @jwt_required()
    def post(self):
        # ── SECURITY: was WIDE OPEN (any logged-in user could create users).
        # Now admin-only, and the new user is bound to the admin's tenant.
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        data     = request.get_json() or {}
        username = (data.get('username') or "").strip()
        password = data.get('password')
        role     = data.get('role', 'user')
        active   = data.get('active', True)
        email    = (data.get('email') or "").strip() or None

        if not username or not password:
            return {"message": "Username and password are required"}, 400

        if len(password) < 6:
            return {"message": "Password must be at least 6 characters."}, 400

        # ── Only 'admin' or 'user' roles allowed (no privilege injection) ──
        if role not in ('admin', 'user'):
            role = 'user'

        # ── Uniqueness scoped to THIS tenant ──────────────────────────────
        existing = User.query.filter_by(
            tenant_id=tenant_id, username=username
        ).first()
        if existing:
            return {"message": "A user with that username already exists in this shop."}, 409

        new_user = User(
            tenant_id = tenant_id,
            username  = username,
            email     = email,
            role      = role,
            active    = active,
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()
        return new_user.to_dict(), 201


class UserResource(Resource):

    @jwt_required()
    def patch(self, user_id):
        # ── SECURITY: was WIDE OPEN. Now admin-only + tenant-scoped.
        current_user, tenant_id = current_user_and_tenant()
        if not current_user or current_user.role != "admin":
            return {"message": "Admin access required."}, 403

        user = User.query.filter_by(
            id=user_id, tenant_id=tenant_id
        ).first_or_404()
        data = request.get_json() or {}

        # ── Guard: an admin can't lock themselves out or self-demote ──────
        if user.id == current_user.id:
            if "active" in data and data["active"] is False:
                return {"message": "You can't deactivate your own account."}, 400
            if "role" in data and data["role"] != "admin":
                return {"message": "You can't remove your own admin role."}, 400

        if 'active' in data:
            user.active = bool(data['active'])
        if 'role' in data and data['role'] in ('admin', 'user'):
            user.role = data['role']

        db.session.commit()
        return user.to_dict(), 200

    @jwt_required()
    def delete(self, user_id):
        current_user, tenant_id = current_user_and_tenant()
        if not current_user or current_user.role != "admin":
            return {"message": "Admin access required."}, 403

        # ── Guard: can't delete yourself ──────────────────────────────────
        if user_id == current_user.id:
            return {"message": "You can't delete your own account."}, 400

        user = User.query.filter_by(
            id=user_id, tenant_id=tenant_id
        ).first_or_404()
        db.session.delete(user)
        db.session.commit()
        return {"message": "User deleted successfully"}, 200