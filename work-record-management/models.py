from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    department_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

class Work(db.Model):
    __tablename__ = 'works'
    id = db.Column(db.Integer, primary_key=True)
    work_code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100), nullable=False)
    department_code = db.Column(db.String(20)) # Associated department code

class PerformanceRecord(db.Model):
    __tablename__ = 'performance_records'
    id = db.Column(db.Integer, primary_key=True)
    work_date = db.Column(db.Date, nullable=False)
    employee_code = db.Column(db.String(20), nullable=False)
    department_code = db.Column(db.String(20))
    work_code = db.Column(db.String(20), nullable=False)
    product_code = db.Column(db.String(50), nullable=False)
    work_hours = db.Column(db.Float, nullable=False, default=0.0)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
