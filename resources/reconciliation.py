from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import CashReconciliation, Sale, User
from extensions import db
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, cast, Date


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


def _calculate_expected_for_date(target_date):
    """
    CASH DRAWER (physical notes in till):
      - Pure cash sales       → total_amount
      - Split sales           → cash_amount only

    TILL / M-PESA (Kopo Kopo balance):
      - Pure mpesa sales      → total_amount
      - Split sales           → mpesa_amount only
    """

    # ── Cash drawer ───────────────────────────────────────────────────────
    cash_sales = db.session.query(func.sum(Sale.total_amount))\
        .filter(
            cast(Sale.sale_date, Date) == target_date,
            Sale.payment_method == 'cash',
            Sale.payment_status == 'paid',
        ).scalar() or 0

    split_cash = db.session.query(func.sum(Sale.cash_amount))\
        .filter(
            cast(Sale.sale_date, Date) == target_date,
            Sale.payment_method == 'split',
            Sale.payment_status == 'paid',
            Sale.cash_amount.isnot(None),
        ).scalar() or 0

    expected_cash = float(cash_sales) + float(split_cash)

    # ── Till / M-Pesa ─────────────────────────────────────────────────────
    mpesa_sales = db.session.query(func.sum(Sale.total_amount))\
        .filter(
            cast(Sale.sale_date, Date) == target_date,
            Sale.payment_method == 'mpesa',
            Sale.payment_status == 'paid',
        ).scalar() or 0

    split_mpesa = db.session.query(func.sum(Sale.mpesa_amount))\
        .filter(
            cast(Sale.sale_date, Date) == target_date,
            Sale.payment_method == 'split',
            Sale.payment_status == 'paid',
            Sale.mpesa_amount.isnot(None),
        ).scalar() or 0

    expected_till = float(mpesa_sales) + float(split_mpesa)

    # ── Total revenue all methods ─────────────────────────────────────────
    total_sales = db.session.query(func.sum(Sale.total_amount))\
        .filter(
            cast(Sale.sale_date, Date) == target_date,
            Sale.payment_status == 'paid',
        ).scalar() or 0

    # ── Credit sales (not yet collected) ─────────────────────────────────
    credit_sales = db.session.query(func.sum(Sale.total_amount))\
        .filter(
            cast(Sale.sale_date, Date) == target_date,
            Sale.payment_method == 'credit',
        ).scalar() or 0

    return {
        "expected_cash":  expected_cash,
        "expected_till":  expected_till,
        "total_sales":    float(total_sales),
        "credit_sales":   float(credit_sales),
    }


class ReconciliationResource(Resource):
    """
    GET  /reconciliation  — fetch expected amounts + 30-day history
    POST /reconciliation  — lock actual cash count for the day
    """

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        target_date_str = request.args.get('date')
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400
        else:
            eat_offset  = timedelta(hours=3)
            target_date = (datetime.now(timezone.utc) + eat_offset).date()

        expected = _calculate_expected_for_date(target_date)

        existing = CashReconciliation.query.filter_by(
            reconciled_date=target_date
        ).first()

        past = CashReconciliation.query\
            .order_by(CashReconciliation.reconciled_date.desc())\
            .limit(30).all()

        return {
            "date":          target_date.isoformat(),
            "expected_cash": expected["expected_cash"],
            "expected_till": expected["expected_till"],
            "total_sales":   expected["total_sales"],
            "credit_sales":  expected["credit_sales"],
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
        actual_till     = data.get('actual_till', 0)
        notes           = data.get('notes', '').strip()
        target_date_str = data.get('date')

        if actual_cash is None:
            return {"message": "Actual cash count is required."}, 400

        try:
            actual_cash = float(actual_cash)
            actual_till = float(actual_till)
            if actual_cash < 0 or actual_till < 0:
                return {"message": "Amounts cannot be negative."}, 400
        except (TypeError, ValueError):
            return {"message": "Invalid amount."}, 400

        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                return {"message": "Invalid date."}, 400
        else:
            eat_offset  = timedelta(hours=3)
            target_date = (datetime.now(timezone.utc) + eat_offset).date()

        existing = CashReconciliation.query.filter_by(
            reconciled_date=target_date
        ).first()
        if existing:
            return {
                "message":  f"Already reconciled for {target_date}.",
                "existing": existing.to_dict(),
            }, 409

        expected = _calculate_expected_for_date(target_date)

        cash_difference = actual_cash - expected["expected_cash"]
        till_difference = actual_till - expected["expected_till"]

        # ── Pack till figures into notes since we have no extra columns ───
        # Format: "TILL:expected=X,actual=Y,diff=Z | <admin notes>"
        till_summary = (
            f"TILL: expected={expected['expected_till']:.2f}, "
            f"actual={actual_till:.2f}, "
            f"diff={till_difference:.2f}"
        )
        full_notes = f"{till_summary} | {notes}" if notes else till_summary

        try:
            recon = CashReconciliation(
                reconciled_date = target_date,
                expected_cash   = expected["expected_cash"],
                actual_cash     = actual_cash,
                difference      = cash_difference,
                notes           = full_notes,
                reconciled_by   = user_id,
            )
            db.session.add(recon)
            db.session.commit()

            # Return everything the frontend needs
            return {
                **recon.to_dict(),
                "expected_till":  expected["expected_till"],
                "actual_till":    actual_till,
                "till_difference": till_difference,
                "total_sales":    expected["total_sales"],
                "credit_sales":   expected["credit_sales"],
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500