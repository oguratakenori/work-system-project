from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_visible = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    
    records = db.relationship('ExpenseRecord', backref='account', lazy=True)

class ExpenseRecord(db.Model):
    __tablename__ = 'expense_records'
    id = db.Column(db.Integer, primary_key=True)
    target_date = db.Column(db.Date, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(10), nullable=False) # 'monthly' or 'daily'
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
