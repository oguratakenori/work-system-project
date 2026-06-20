import os
import sys
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify, session
from models import db, Work, PerformanceRecord
import crud
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-default-key-please-change')
app.config['SESSION_COOKIE_NAME'] = 'work_record_management_session'

base_dir = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(base_dir, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from auth_utils import (
    auth_context,
    authenticate_employee,
    change_own_password,
    ensure_auth_schema,
    get_employee_db_path,
    permission_required,
    require_login_for_request,
    reset_password_by_admin,
    seed_initial_admin_from_env,
    set_initial_password,
    sign_in,
    sign_out,
)

SYSTEM_KEY = 'work_record'
EMPLOYEE_DB_PATH = get_employee_db_path(base_dir)

# Database Configuration
database_url = os.getenv('DATABASE_URL')
if not database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///taskapp.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

PER_PAGE_OPTIONS = (10, 20, 50, 100)
DEFAULT_PER_PAGE = 20

def get_pagination_params():
    try:
        page = int(request.args.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    try:
        per_page = int(request.args.get('per_page', DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        per_page = DEFAULT_PER_PAGE
    if per_page not in PER_PAGE_OPTIONS:
        per_page = DEFAULT_PER_PAGE

    return page, per_page

def get_pagination_args():
    args = request.args.to_dict()
    args.pop('page', None)
    return args

def safe_next_url(next_url):
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for('index')

@app.before_request
def require_login():
    return require_login_for_request(SYSTEM_KEY, EMPLOYEE_DB_PATH, {'login', 'logout', 'forgot_password'})

@app.context_processor
def inject_auth_context():
    return auth_context(SYSTEM_KEY)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        employee_code = request.form.get('employee_code', '').strip()
        password = request.form.get('password', '')
        employee, error = authenticate_employee(EMPLOYEE_DB_PATH, employee_code, password, SYSTEM_KEY)
        if error:
            flash(error, 'error')
            return render_template('login.html', system_name='作業実績管理システム')
        sign_in(employee)
        if session.get('password_reset_required'):
            flash('初回ログインのため、新しいパスワードを設定してください。', 'warning')
            return redirect(url_for('initial_password_setup'))
        flash('ログインしました。', 'success')
        return redirect(safe_next_url(request.args.get('next')))
    return render_template('login.html', system_name='作業実績管理システム')

@app.route('/logout')
def logout():
    sign_out()
    flash('ログアウトしました。', 'success')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        success, message = reset_password_by_admin(
            EMPLOYEE_DB_PATH,
            request.form.get('target_employee_code', ''),
            request.form.get('admin_employee_code', ''),
            request.form.get('admin_password', ''),
        )
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('login'))
    return render_template('forgot_password.html', system_name='作業実績管理システム')

@app.route('/initial-password', methods=['GET', 'POST'])
def initial_password_setup():
    if not session.get('password_reset_required'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        success, message = set_initial_password(
            EMPLOYEE_DB_PATH,
            session.get('employee_id'),
            request.form.get('new_password', ''),
            request.form.get('new_password_confirm', ''),
        )
        flash(message, 'success' if success else 'error')
        if success:
            session['password_reset_required'] = False
            return redirect(url_for('index'))
    return render_template('initial_password_setup.html')

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        success, message = change_own_password(
            EMPLOYEE_DB_PATH,
            session.get('employee_id'),
            request.form.get('current_password', ''),
            request.form.get('new_password', ''),
            request.form.get('new_password_confirm', ''),
        )
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('index'))
    return render_template('change_password.html')

def seed_data():
    if crud.get_all_works() == []:
        # Seed Works
        crud.add_work('W001', '組立')
        crud.add_work('W002', '加工')

# 1. Menu Screen
@app.route('/')
def index():
    return render_template('index.html')

# 2. Work Master Management
@app.route('/masters/works', methods=['GET'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def manage_works():
    filters = {
        'work_code': request.args.get('work_code'),
        'name': request.args.get('name'),
        'department_id': request.args.get('department_id')
    }
    page, per_page = get_pagination_params()
    works = crud.get_works_page(filters, page=page, per_page=per_page)
    departments = crud.get_external_departments()
    dept_map = crud.get_department_map()
    return render_template(
        'masters/works.html',
        works=works,
        departments=departments,
        dept_map=dept_map,
        per_page_options=PER_PAGE_OPTIONS,
        pagination_args=get_pagination_args()
    )

@app.route('/masters/works/new', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def new_work():
    if request.method == 'POST':
        code = request.form.get('work_code')
        name = request.form.get('name')
        dept_id = request.form.get('department_id')
        if name:
            crud.add_work(code, name, dept_id)
            flash('作業を追加しました')
        return redirect(url_for('manage_works'))
    
    departments = crud.get_external_departments()
    return render_template('masters/works_new.html', departments=departments)

@app.route('/masters/works/edit/<int:id>', methods=['POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def edit_work(id):
    code = request.form.get('work_code')
    name = request.form.get('name')
    dept_id = request.form.get('department_id')
    crud.update_work(id, code, name, dept_id)
    flash('作業情報を更新しました')
    return redirect(url_for('manage_works'))

@app.route('/masters/works/delete/<int:id>')
@permission_required(SYSTEM_KEY, 'master_delete', EMPLOYEE_DB_PATH)
def delete_work(id):
    crud.delete_work(id)
    flash('作業を削除しました')
    return redirect(url_for('manage_works'))

# 3. Performance Input
@app.route('/performance/input', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'record_write', EMPLOYEE_DB_PATH)
def performance_input():
    if request.method == 'POST':
        data = {
            'work_date': request.form.get('work_date'),
            'employee_code': request.form.get('employee_code'),
            'work_code': request.form.get('work_code'),
            'product_code': request.form.get('product_code'),
            'work_hours': request.form.get('work_hours'),
            'quantity': request.form.get('quantity')
        }
        
        if all([data['work_date'], data['employee_code'], data['work_code'], data['product_code']]):
            crud.add_performance_record(data)
            flash('実績を登録しました')
        else:
            flash('必須項目を入力してください', 'error')
        return redirect(url_for('performance_input'))
    
    departments = crud.get_external_departments()
    return render_template('performance/input.html', departments=departments)

@app.route('/performance/edit/<int:id>', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'record_write', EMPLOYEE_DB_PATH)
def edit_performance(id):
    if request.method == 'POST':
        data = {
            'work_date': request.form.get('work_date'),
            'employee_code': request.form.get('employee_code'),
            'work_code': request.form.get('work_code'),
            'product_code': request.form.get('product_code'),
            'work_hours': request.form.get('work_hours'),
            'quantity': request.form.get('quantity')
        }
        crud.update_performance_record(id, data)
        flash('作業実績を更新しました')
        return redirect(url_for('performance_list'))

    record = crud.get_performance_record(id)
    if not record:
        flash('対象の実績が見つかりません', 'error')
        return redirect(url_for('performance_list'))
    
    departments = crud.get_external_departments()
    
    # Need current department_id to initialize cascading dropdowns in edit mode
    work = Work.query.filter_by(work_code=record.work_code).first()
    current_dept_id = work.department_id if work else None
    
    return render_template('performance/edit.html', 
                           record=record, 
                           departments=departments,
                           current_dept_id=current_dept_id)

@app.route('/performance/delete/<int:id>', methods=['POST'])
@permission_required(SYSTEM_KEY, 'record_delete', EMPLOYEE_DB_PATH)
def delete_performance(id):
    crud.delete_performance_record(id)
    flash('作業実績を削除しました')
    return redirect(url_for('performance_list'))

# API Endpoints for Dynamic UI
@app.route('/api/employees')
def api_employees():
    query = request.args.get('q', '')
    employees = crud.get_external_employees(query)
    return jsonify(employees)

@app.route('/api/products')
def api_products():
    dept_id = request.args.get('department_id')
    products = crud.get_external_products(dept_id)
    return jsonify(products)

@app.route('/api/works')
def api_works():
    dept_id = request.args.get('department_id')
    works = crud.get_works({'department_id': dept_id})
    return jsonify([{'work_code': w.work_code, 'name': w.name} for w in works])

# 4. Performance List
@app.route('/performance/list')
def performance_list():
    filters = {
        'employee_code': request.args.get('employee_code'),
        'department_id': request.args.get('department_id'),
        'work_code': request.args.get('work_code')
    }
    page, per_page = get_pagination_params()
    records = crud.get_performance_records_page(filters, page=page, per_page=per_page)
    
    departments = crud.get_external_departments()
    # Filter works for the dropdown if department is selected
    works = crud.get_works({'department_id': filters['department_id']}) if filters['department_id'] else crud.get_all_works()
    
    emp_name_map = crud.get_employee_name_map()
    all_works = crud.get_all_works()
    work_name_map = {w.work_code: w.name for w in all_works}
    dept_map = crud.get_department_map()
    # Create a map for work_code -> department_name for display
    work_dept_map = {w.work_code: dept_map.get(w.department_id, '未設定') for w in all_works}

    return render_template('performance/list.html', 
                           records=records, 
                           departments=departments, 
                           works=works,
                           emp_name_map=emp_name_map,
                           work_name_map=work_name_map,
                           work_dept_map=work_dept_map,
                           per_page_options=PER_PAGE_OPTIONS,
                           pagination_args=get_pagination_args())

# 5. Reports
@app.route('/reports', methods=['GET'])
def reports():
    filters = {
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
        'employee_code': request.args.get('employee_code'),
        'department_id': request.args.get('department_id'),
        'work_code': request.args.get('work_code'),
        'product_code': request.args.get('product_code')
    }
    records = crud.get_performance_records(filters)

    departments = crud.get_external_departments()
    dept_id = filters['department_id']
    # Dynamic options for dropdowns
    works = crud.get_works({'department_id': dept_id}) if dept_id else crud.get_all_works()
    products = crud.get_external_products(dept_id) if dept_id else crud.get_external_products()

    # Maps for display
    emp_name_map = crud.get_employee_name_map()
    all_works = crud.get_all_works()
    work_name_map = {w.work_code: w.name for w in all_works}
    prod_name_map = crud.get_product_name_map()
    dept_map = crud.get_department_map()

    # Map for Work Code -> Department ID/Full Name
    work_to_dept_id = {w.work_code: w.department_id for w in all_works}

    if request.args.get('export') == 'csv':
        output = StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['作業日', '社員コード', '氏名', '部署', '作業コード', '作業名', '製品コード', '製品名', '時間', '数量'])
        for r in records:
            d_id = work_to_dept_id.get(r.work_code)
            dept_display = dept_map.get(d_id, '未設定')
            writer.writerow([
                r.work_date, 
                r.employee_code, 
                emp_name_map.get(r.employee_code, ''),
                dept_display,
                r.work_code, 
                work_name_map.get(r.work_code, ''),
                r.product_code, 
                prod_name_map.get(r.product_code, ''),
                r.work_hours, 
                r.quantity
            ])

        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=performance_report.csv'
        return response

    return render_template('reports/index.html', 
                           records=records, 
                           departments=departments,
                           works=works,
                           products=products,
                           emp_name_map=emp_name_map,
                           work_name_map=work_name_map,
                           prod_name_map=prod_name_map,
                           dept_map=dept_map,
                           work_to_dept_id=work_to_dept_id)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_auth_schema(EMPLOYEE_DB_PATH)
        seed_initial_admin_from_env(EMPLOYEE_DB_PATH)
        seed_data()
    app.run(debug=True, port=5003)
