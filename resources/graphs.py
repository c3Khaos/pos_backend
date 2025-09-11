from  flask_restful import Resource
from models import db

class SalesTrend(Resource):
    def get(self):
        query = """
        SELECT DATE(sale_date) as day, SUM(amount) as total_sales
        FROM sales
        GROUP BY DATE(sale_date)
        ORDER BY day ASC
        """

        result = db.session.execute(query).fetchall()

        data = [{"day":str(row[0]),"total_sales":float(row[1])} for row in result]

        return {"sales":data},200
