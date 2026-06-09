from datetime import datetime
from models import db, Department, Work, PerformanceRecord

def get_all_departments():
    return Department.query.all()

def add_department(code, name):
    new_dept = Department(department_code=code, name=name)
    db.session.add(new_dept)
    db.session.commit()
    return new_dept

def get_all_works():
    return Work.query.all()

def add_work(code, name, dept_code):
    new_work = Work(work_code=code, name=name, department_code=dept_code)
    db.session.add(new_work)
    db.session.commit()
    return new_work

def add_performance_record(data):
    new_record = PerformanceRecord(
        work_date=datetime.strptime(data['work_date'], '%Y-%m-%d').date(),
        employee_code=data['employee_code'],
        department_code=data['department_code'],
        work_code=data['work_code'],
        product_code=data['product_code'],
        work_hours=float(data['work_hours'] or 0),
        quantity=int(data['quantity'] or 0)
    )
    db.session.add(new_record)
    db.session.commit()
    return new_record

def get_performance_records(filters=None):
    query = PerformanceRecord.query
    if filters:
        if filters.get('employee_code'):
            query = query.filter(PerformanceRecord.employee_code == filters['employee_code'])
        if filters.get('department_code'):
            query = query.filter(PerformanceRecord.department_code == filters['department_code'])
        if filters.get('start_date'):
            query = query.filter(PerformanceRecord.work_date >= datetime.strptime(filters['start_date'], '%Y-%m-%d').date())
        if filters.get('end_date'):
            query = query.filter(PerformanceRecord.work_date <= datetime.strptime(filters['end_date'], '%Y-%m-%d').date())
    
    return query.order_by(PerformanceRecord.work_date.desc()).all()
