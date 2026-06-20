from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    department_code = db.Column(db.String(4), unique=True, nullable=False) # D001 format
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    employees = db.relationship('Employee', backref='department', lazy=True)

class Position(db.Model):
    __tablename__ = 'positions'
    id = db.Column(db.Integer, primary_key=True)
    position_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    employees = db.relationship('Employee', backref='position', lazy=True)

class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(10), unique=True, nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    furigana_last = db.Column(db.String(50), nullable=False)
    furigana_first = db.Column(db.String(50), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'), nullable=True)
    hire_date = db.Column(db.Date)
    retirement_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='在職') # 在職, 休職, 退職
    is_active = db.Column(db.Boolean, default=True)
    password_hash = db.Column(db.String(255))
    password_reset_required = db.Column(db.Boolean, default=False)
    can_login = db.Column(db.Boolean, default=False)
    postal_code = db.Column(db.String(20))
    address1 = db.Column(db.String(255))
    address2 = db.Column(db.String(255))
    address1_furigana = db.Column(db.String(255))
    address2_furigana = db.Column(db.String(255))
    phone_number = db.Column(db.String(30))
    birth_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    is_system_user = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    hourly_rates = db.relationship('HourlyRateHistory', backref='employee', lazy=True, order_by='HourlyRateHistory.start_date.desc()')
    system_permissions = db.relationship('EmployeeSystemPermission', backref='employee', lazy=True, cascade='all, delete-orphan')

    @property
    def current_hourly_rate(self):
        # Get the history record where end_date is NULL
        latest = HourlyRateHistory.query.filter_by(employee_id=self.id, end_date=None).first()
        return latest.hourly_wage if latest else 0

class HourlyRateHistory(db.Model):
    __tablename__ = 'hourly_rate_history'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    hourly_wage = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date) # NULL means currently active
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmployeeSystemPermission(db.Model):
    __tablename__ = 'employee_system_permissions'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    system_key = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('employee_id', 'system_key', name='uq_employee_system_permission'),
    )
