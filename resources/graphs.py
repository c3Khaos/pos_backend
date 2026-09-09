from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import db, Sale
from sqlalchemy import func, cast, Date


class SalesTrend(Resource):

    @jwt_required()
    def get(self):
        results = db.session.query(
            cast(Sale.sale_date, Date).label('day'),
            func.sum(Sale.total_amount).label('total_sales'),
        ).filter(
            Sale.payment_status == 'paid'
        ).group_by(
            cast(Sale.sale_date, Date)
        ).order_by(
            cast(Sale.sale_date, Date).asc()
        ).all()

        data = [
            {"day": str(row.day), "total_sales": float(row.total_sales)}
            for row in results
        ]
        return {"sales": data}, 200