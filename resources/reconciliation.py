from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import CashReconciliation, Sale, User
from extensions import db
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import func, cast, Date


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class ReconciliationResource(Resource):
    """GET /reconciliation — get today's expected cash + past reconciliations
       POST /reconciliation — record today's actual cash count"""

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        # Today's expected cash from system
        target_date_str = request.args.get('date')
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400
        else:
            eat_offset = timedelta(hours=3)
            target_date = (datetime.now(timezone.utc) + eat_offset).date()

        # Sum of cash sales for that date
        expected_cash = db.session.query(func.sum(Sale.amount_paid))\
            .filter(
                cast(Sale.sale_date, Date) == target_date,
                Sale.payment_method == 'cash',
                Sale.payment_status == 'paid'
            ).scalar() or 0

        # Check if already reconciled
        existing = CashReconciliation.query.filter_by(reconciled_date=target_date).first()

        # Past reconciliations
        past = CashReconciliation.query.order_by(
            CashReconciliation.reconciled_date.desc()
        ).limit(30).all()

        return {
            "date":          target_date.isoformat(),
            "expected_cash": float(expected_cash),
            "already_done":  existing.to_dict() if existing else None,
            "history":       [r.to_dict() for r in past],
        }, 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        data = request.get_json()

        actual_cash     = data.get('actual_cash')
        notes           = data.get('notes', '').strip()
        target_date_str = data.get('date')

        if actual_cash is None:
            return {"message": "Actual cash count required."}, 400

        try:
            actual_cash = float(actual_cash)
            if actual_cash < 0:
                return {"message": "Actual cash cannot be negative."}, 400
        except (TypeError, ValueError):
            return {"message": "Invalid cash amount."}, 400

        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                return {"message": "Invalid date."}, 400
        else:
            eat_offset = timedelta(hours=3)
            target_date = (datetime.now(timezone.utc) + eat_offset).date()

        # Check existing
        existing = CashReconciliation.query.filter_by(reconciled_date=target_date).first()
        if existing:
            return {"message": f"Cash already reconciled for {target_date}."}, 409

        # Expected from system
        expected_cash = db.session.query(func.sum(Sale.amount_paid))\
            .filter(
                cast(Sale.sale_date, Date) == target_date,
                Sale.payment_method == 'cash',
                Sale.payment_status == 'paid'
            ).scalar() or 0
        expected_cash = float(expected_cash)

        difference = actual_cash - expected_cash

        try:
            recon = CashReconciliation(
                reconciled_date = target_date,
                expected_cash   = expected_cash,
                actual_cash     = actual_cash,
                difference      = difference,
                notes           = notes or None,
                reconciled_by   = user_id,
            )
            db.session.add(recon)
            db.session.commit()
            return recon.to_dict(), 201
        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500