import sqlite3
import os
from datetime import datetime
from models import db, Work, PerformanceRecord

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
EXTERNAL_EMPLOYEE_DB = os.path.join(PROJECT_ROOT, 'employee-management', 'instance', 'employee_management.db')
EXTERNAL_PRODUCT_DB = os.path.join(PROJECT_ROOT, 'product-management', 'instance', 'product_management.db')

def get_external_departments():
    if not os.path.exists(EXTERNAL_EMPLOYEE_DB):
        return []
    try:
        conn = sqlite3.connect(EXTERNAL_EMPLOYEE_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, department_code, name FROM departments WHERE is_active = 1 OR is_active IS NULL")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching external departments: {e}")
        return []

def get_external_employees(query=None):
    if not os.path.exists(EXTERNAL_EMPLOYEE_DB):
        return []
    try:
        conn = sqlite3.connect(EXTERNAL_EMPLOYEE_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        sql = """
            SELECT employee_code, last_name, first_name
            FROM employees
            WHERE (is_active = 1 OR is_active IS NULL)
              AND employee_code != 'ADMIN001'
              AND (is_system_user = 0 OR is_system_user IS NULL)
        """
        params = []
        if query:
            sql += " AND (employee_code LIKE ? OR last_name LIKE ? OR first_name LIKE ?)"
            q = f"%{query}%"
            params = [q, q, q]
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching external employees: {e}")
        return []

def get_employee_name_map():
    employees = get_external_employees()
    return {emp['employee_code']: f"{emp['last_name']} {emp['first_name']}" for emp in employees}

def get_external_products(department_id=None):
    if not os.path.exists(EXTERNAL_PRODUCT_DB):
        return []
    try:
        conn = sqlite3.connect(EXTERNAL_PRODUCT_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        sql = "SELECT product_code, name FROM products WHERE is_active = 1 OR is_active IS NULL"
        params = []
        if department_id:
            sql += " AND department_id = ?"
            params = [department_id]
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching external products: {e}")
        return []

def get_product_name_map():
    products = get_external_products()
    return {p['product_code']: p['name'] for p in products}

def get_department_map():
    depts = get_external_departments()
    return {d['id']: f"{d['department_code']}：{d['name']}" for d in depts}

def get_department_full_map():
    # id -> {code, name}
    depts = get_external_departments()
    return {d['id']: d for d in depts}

def get_all_works():
    return Work.query.all()

def build_works_query(filters=None):
    query = Work.query
    if filters:
        if filters.get('work_code'):
            query = query.filter(Work.work_code.like(f"%{filters['work_code']}%"))
        if filters.get('name'):
            query = query.filter(Work.name.like(f"%{filters['name']}%"))
        if filters.get('department_id'):
            query = query.filter(Work.department_id == filters['department_id'])
    return query.order_by(Work.work_code.asc())

def get_works(filters=None):
    return build_works_query(filters).all()

def get_works_page(filters=None, page=1, per_page=20):
    return build_works_query(filters).paginate(page=page, per_page=per_page, error_out=False)

def add_work(code, name, department_id=None):
    new_work = Work(work_code=code, name=name, department_id=department_id)
    db.session.add(new_work)
    db.session.commit()
    return new_work

def update_work(work_id, code, name, department_id):
    work = Work.query.get(work_id)
    if work:
        work.work_code = code
        work.name = name
        work.department_id = department_id
        db.session.commit()
    return work

def delete_work(work_id):
    work = Work.query.get(work_id)
    if work:
        db.session.delete(work)
        db.session.commit()
    return work

def time_str_to_float(time_str):
    """Converts HH:MM or HHMM string to float hours."""
    if not time_str:
        return 0.0
    time_str = time_str.replace(':', '')
    try:
        if len(time_str) <= 2:
            return float(time_str)
        elif len(time_str) == 3:
            h = int(time_str[0])
            m = int(time_str[1:])
        else:
            h = int(time_str[:-2])
            m = int(time_str[-2:])
        return h + (m / 60.0)
    except ValueError:
        return 0.0

def add_performance_record(data):
    # Convert time format if needed
    work_hours = data['work_hours']
    if isinstance(work_hours, str) and (':' in work_hours or len(work_hours) >= 3):
        work_hours = time_str_to_float(work_hours)
    else:
        work_hours = float(work_hours or 0)

    new_record = PerformanceRecord(
        work_date=datetime.strptime(data['work_date'], '%Y-%m-%d').date(),
        employee_code=data['employee_code'],
        work_code=data['work_code'],
        product_code=data['product_code'],
        work_hours=work_hours,
        quantity=int(data['quantity'] or 0)
    )
    db.session.add(new_record)
    db.session.commit()
    return new_record

def build_performance_records_query(filters=None):
    query = PerformanceRecord.query
    if filters:
        if filters.get('employee_code'):
            query = query.filter(PerformanceRecord.employee_code == filters['employee_code'])
        if filters.get('work_code'):
            query = query.filter(PerformanceRecord.work_code == filters['work_code'])
        if filters.get('product_code'):
            query = query.filter(PerformanceRecord.product_code == filters['product_code'])
        
        # Filter by department via join with Work
        if filters.get('department_id'):
            query = query.join(Work, PerformanceRecord.work_code == Work.work_code)\
                         .filter(Work.department_id == filters['department_id'])
            
        if filters.get('start_date'):
            query = query.filter(PerformanceRecord.work_date >= datetime.strptime(filters['start_date'], '%Y-%m-%d').date())
        if filters.get('end_date'):
            query = query.filter(PerformanceRecord.work_date <= datetime.strptime(filters['end_date'], '%Y-%m-%d').date())
    
    return query.order_by(PerformanceRecord.work_date.desc(), PerformanceRecord.id.desc())

def get_performance_records(filters=None):
    return build_performance_records_query(filters).all()

def get_performance_records_page(filters=None, page=1, per_page=20):
    return build_performance_records_query(filters).paginate(page=page, per_page=per_page, error_out=False)

def get_performance_record(record_id):
    return PerformanceRecord.query.get(record_id)

def update_performance_record(record_id, data):
    record = PerformanceRecord.query.get(record_id)
    if record:
        work_hours = data['work_hours']
        if isinstance(work_hours, str) and (':' in work_hours or len(work_hours) >= 3):
            work_hours = time_str_to_float(work_hours)
        else:
            work_hours = float(work_hours or 0)

        record.work_date = datetime.strptime(data['work_date'], '%Y-%m-%d').date()
        record.employee_code = data['employee_code']
        record.work_code = data['work_code']
        record.product_code = data['product_code']
        record.work_hours = work_hours
        record.quantity = int(data['quantity'] or 0)
        db.session.commit()
    return record

def delete_performance_record(record_id):
    record = PerformanceRecord.query.get(record_id)
    if record:
        db.session.delete(record)
        db.session.commit()
    return True
