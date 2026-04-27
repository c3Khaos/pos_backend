from flask_restful import Resource
from models import db, SaleItem, Product
from sqlalchemy import text

HARDWARE_CATEGORY = 'Hardware & Utilities'

class SalesTrend(Resource):
    def get(self):
        # Get hardware sale IDs to exclude
        hw_sale_ids = db.session.query(SaleItem.sale_id).join(
            Product, SaleItem.product_id == Product.id
        ).filter(
            Product.category == HARDWARE_CATEGORY
        ).distinct().all()

        hw_ids = [row[0] for row in hw_sale_ids]

        if hw_ids:
            # Exclude hardware sales from trend
            placeholders = ','.join(str(i) for i in hw_ids)
            query = text(f"""
                SELECT DATE(sale_date) as day, SUM(total_amount) as total_sales
                FROM sales
                WHERE id NOT IN ({placeholders})
                GROUP BY DATE(sale_date)
                ORDER BY day ASC
            """)
        else:
            # No hardware sales exist yet — return all
            query = text("""
                SELECT DATE(sale_date) as day, SUM(total_amount) as total_sales
                FROM sales
                GROUP BY DATE(sale_date)
                ORDER BY day ASC
            """)

        result = db.session.execute(query).fetchall()
        data   = [{"day": str(row[0]), "total_sales": float(row[1])} for row in result]

        return {"sales": data}, 200