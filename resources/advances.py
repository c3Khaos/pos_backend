from decimal import Decimal
from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import CashAdvance
from extensions import db
from datetime import datetime, timezone
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


class CashAdvanceListResource(Resource):

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        department = request.args.get('department')
        status     = request.args.get('status')
        show_all   = request.args.get('all') == 'true'

        query = CashAdvance.query.filter_by(tenant_id=tenant_id)

        if department:
            query = query.filter(CashAdvance.department == department)

        if show_all:
            if status:
                query = query.filter(CashAdvance.status == status)
        elif status:
            query = query.filter(CashAdvance.status == status)
        else:
            query = query.filter(CashAdvance.status.in_(['pending', 'partial']))

        advances = query.order_by(CashAdvance.taken_at.desc()).all()
        return [a.to_dict() for a in advances], 200

    @jwt_required()
    def post(self):
        user, tenant_id = current_user_and_tenant()
        if not user or user.role != 'admin':
            return {"message": "Admin access required."}, 403

        data        = request.get_json() or {}
        person_name = data.get('person_name', '').strip()
        amount      = data.get('amount')
        reason      = data.get('reason', '').strip()
        department  = data.get('department', 'shop')

        if not person_name:
            return {"message": "Person name is required."}, 400
        if amount is None:
            return {"message": "Amount is required."}, 400

        try:
            amount = Decimal(str(amount))
        except (TypeError, ValueError):
            return {"message": "Invalid amount."}, 400

        if amount <= 0:
            return {"message": "Amount must be greater than 0."}, 400

        advance = CashAdvance(
            tenant_id   = tenant_id,
            person_name = person_name,
            amount      = amount,
            reason      = reason or None,
            department  = department,
            recorded_by = user.id,
        )
        db.session.add(advance)
        db.session.commit()
        return advance.to_dict(), 201


class CashAdvanceReturnResource(Resource):

    @jwt_required()
    def post(self, advance_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        advance = CashAdvance.query.filter_by(
            id=advance_id, tenant_id=tenant_id
        ).first()
        if not advance:
            return {"message": "Advance not found."}, 404

        data = request.get_json() or {}

        if advance.status == 'returned':
            return {"message": "This advance has already been fully returned."}, 400

        amount_returning = data.get('amount')
        if amount_returning is None:
            return {"message": "Amount is required."}, 400

        try:
            amount_returning = Decimal(str(amount_returning))
        except (TypeError, ValueError):
            return {"message": "Invalid amount."}, 400

        if amount_returning <= 0:
            return {"message": "Amount must be greater than 0."}, 400

        already_returned  = advance.amount_returned or Decimal('0')
        amount_still_owed = advance.amount - already_returned

        if amount_returning > amount_still_owed:
            return {
                "message": f"Return exceeds amount owed (KSh {amount_still_owed:.2f})."
            }, 400

        try:
            advance.amount_returned = already_returned + amount_returning

            if advance.amount_returned >= advance.amount:
                advance.status      = 'returned'
                advance.returned_at = datetime.now(timezone.utc)
            else:
                advance.status = 'partial'

            db.session.commit()

            return {
                "message":         "Return recorded successfully.",
                "advance":         advance.to_dict(),
                "amount_returned": float(advance.amount_returned),
                "amount_owed":     float(advance.amount - advance.amount_returned),
                "status":          advance.status,
            }, 200

        except Exception as e:
            db.session.rollback()
            return {"message": "An error occurred."}, 500


class CashAdvanceSummaryResource(Resource):

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        department = request.args.get('department')

        outstanding_q = CashAdvance.query.filter_by(tenant_id=tenant_id).filter(
            CashAdvance.status.in_(['pending', 'partial'])
        )
        if department:
            outstanding_q = outstanding_q.filter(CashAdvance.department == department)
        outstanding = outstanding_q.all()

        all_q = CashAdvance.query.filter_by(tenant_id=tenant_id)
        if department:
            all_q = all_q.filter(CashAdvance.department == department)
        all_advances = all_q.all()

        total_taken    = sum(a.amount for a in all_advances)
        total_returned = sum((a.amount_returned or Decimal('0')) for a in all_advances)
        total_owed     = sum(
            a.amount - (a.amount_returned or Decimal('0')) for a in outstanding
        )

        return {
            "total_taken":    float(round(total_taken,    2)),
            "total_returned": float(round(total_returned, 2)),
            "total_owed":     float(round(total_owed,     2)),
            "count":          len(outstanding),
        }, 200