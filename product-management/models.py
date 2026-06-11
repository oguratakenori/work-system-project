from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Department(db.Model):
    __bind_key__ = 'employee_db'
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    department_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, nullable=False)
    product_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, default=0)
    registered_date = db.Column(db.Date, nullable=False)
    abolished_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('department_id', 'product_code', name='uq_dept_prod_code'),
    )

    @property
    def department(self):
        return Department.query.get(self.department_id)
