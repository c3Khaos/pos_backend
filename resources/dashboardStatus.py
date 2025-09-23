from flask_restful import Resource
from models import User,SaleItem,Product,db
from sqlalchemy import func


class DashboardInfo(Resource):
    def get(self):
        try:
            total_users = db.session.query(User).count()
            total_products = db.session.query(Product).count()
            total_profit = db.session.query(func.sum(SaleItem.profit)).scalar()
            total_sales = db.session.query(func.sum(SaleItem.price * SaleItem.quantity)).scalar()

            return {
                "total_users":total_users,
                "total_products":total_products,
                "total_profit":total_profit,
                "total_sales":total_sales
            },200
        except Exception as e:
            return {"message":f"Error fetching stats: {e}"},500
        


