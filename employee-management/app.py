import os
import sys
from dotenv import load_dotenv
import csv
import io
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, make_response, session
from models import db, Department, Position, Employee, HourlyRateHistory, EmployeeSystemPermission
from sqlalchemy import or_

load_dotenv()

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'employee_management.db').replace('\\', '/')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-default-key-please-change')
app.config['SESSION_COOKIE_NAME'] = 'employee_management_session'

PROJECT_ROOT = os.path.abspath(os.path.join(base_dir, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from auth_utils import (
    ROLE_LABELS,
    SYSTEMS,
    SYSTEM_ADMIN_CODE,
    auth_context,
    authenticate_employee,
    change_own_password,
    ensure_auth_schema,
    permission_required,
    require_login_for_request,
    reset_password_by_admin,
    seed_initial_admin_from_env,
    set_initial_password,
    sign_in,
    sign_out,
)

db.init_app(app)

SYSTEM_KEY = 'employee'
EMPLOYEE_DB_PATH = db_path

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

def to_date(s):
    return datetime.strptime(s, '%Y-%m-%d').date() if s else None

def safe_next_url(next_url):
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for('index')

def apply_employee_form(employee, allow_code_change=False):
    if allow_code_change:
        employee.employee_code = request.form.get('employee_code')
    employee.last_name = request.form.get('last_name')
    employee.first_name = request.form.get('first_name')
    employee.furigana_last = request.form.get('furigana_last')
    employee.furigana_first = request.form.get('furigana_first')
    employee.department_id = request.form.get('department_id') or None
    employee.position_id = request.form.get('position_id') or None
    employee.hire_date = to_date(request.form.get('hire_date'))
    employee.retirement_date = to_date(request.form.get('retirement_date'))
    employee.status = request.form.get('status')
    employee.postal_code = request.form.get('postal_code') or None
    employee.address1 = request.form.get('address1') or None
    employee.address2 = request.form.get('address2') or None
    employee.address1_furigana = request.form.get('address1_furigana') or None
    employee.address2_furigana = request.form.get('address2_furigana') or None
    employee.phone_number = request.form.get('phone_number') or None
    employee.birth_date = to_date(request.form.get('birth_date'))
    employee.notes = request.form.get('notes') or None

def normal_employee_conditions():
    return (
        Employee.is_active == True,
        Employee.employee_code != SYSTEM_ADMIN_CODE,
        or_(Employee.is_system_user == False, Employee.is_system_user.is_(None)),
    )

def get_normal_employee_or_404(id):
    return Employee.query.filter(Employee.id == id, *normal_employee_conditions()).first_or_404()

def render_login_template():
    return render_template('login.html', system_name='社員管理システム')

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
            return render_login_template()
        sign_in(employee)
        if session.get('password_reset_required'):
            flash('初回ログインのため、新しいパスワードを設定してください。', 'warning')
            return redirect(url_for('initial_password_setup'))
        flash('ログインしました。', 'success')
        return redirect(safe_next_url(request.args.get('next')))
    return render_login_template()

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
    return render_template('forgot_password.html', system_name='社員管理システム')

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

@app.route('/')
def index():
    employee_count = Employee.query.filter(*normal_employee_conditions()).count()
    dept_count = Department.query.filter_by(is_active=True).count()
    return render_template('index.html', employee_count=employee_count, dept_count=dept_count)

# --- CSV Export ---
@app.route('/csv/export')
def csv_export():
    employees = Employee.query.filter(*normal_employee_conditions()).all()
    si = io.StringIO()
    si.write('\ufeff')
    writer = csv.writer(si, lineterminator='\r\n')
    writer.writerow(['employee_code', 'name', 'furigana', 'department_code', 'position', 'hourly_wage'])
    for emp in employees:
        writer.writerow([
            emp.employee_code,
            f"{emp.last_name} {emp.first_name}",
            f"{emp.furigana_last} {emp.furigana_first}",
            emp.department.department_code if emp.department else '',
            emp.position.name if emp.position else '',
            emp.current_hourly_rate
        ])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=employees_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@app.route('/csv/import', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def csv_import():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('ファイルがありません。', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('ファイルが選択されていません。', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            csv_input = csv.DictReader(stream)
            
            preview_data = {
                'new': [], 'update': [], 'error': [],
                'auto_create_depts': set(), 'auto_create_positions': set()
            }
            
            for i, row in enumerate(csv_input, start=2):
                try:
                    emp_code = row.get('employee_code')
                    name = row.get('name', '')
                    furigana = row.get('furigana', '')
                    dept_code = row.get('department_code', '')
                    pos_name = row.get('position', '')
                    wage_str = row.get('hourly_wage', '0')

                    if not emp_code:
                        preview_data['error'].append({'line': i, 'reason': '社員コードが空です。', 'data': row})
                        continue
                    if emp_code == SYSTEM_ADMIN_CODE:
                        preview_data['error'].append({'line': i, 'reason': 'ADMIN001 はシステム管理用アカウントのため通常社員として取り込めません。', 'data': row})
                        continue
                    
                    try:
                        wage = int(wage_str) if wage_str else 0
                    except ValueError:
                        wage = 0 # Default to 0 if invalid as per new policy

                    name_parts = name.split(None, 1)
                    last_name = name_parts[0] if len(name_parts) > 0 else ''
                    first_name = name_parts[1] if len(name_parts) > 1 else ''
                    
                    f_parts = furigana.split(None, 1)
                    f_last = f_parts[0] if len(f_parts) > 0 else ''
                    f_first = f_parts[1] if len(f_parts) > 1 else ''

                    emp = Employee.query.filter_by(employee_code=emp_code).first()
                    
                    if dept_code and not Department.query.filter_by(department_code=dept_code).first():
                        preview_data['auto_create_depts'].add(dept_code)
                    if pos_name and not Position.query.filter_by(name=pos_name).first():
                        preview_data['auto_create_positions'].add(pos_name)

                    row_info = {
                        'line': i, 'employee_code': emp_code,
                        'last_name': last_name, 'first_name': first_name,
                        'furigana_last': f_last, 'furigana_first': f_first,
                        'department_code': dept_code, 'position_name': pos_name,
                        'hourly_wage': wage
                    }

                    if not emp:
                        preview_data['new'].append(row_info)
                    else:
                        changes = []
                        if emp.last_name != last_name or emp.first_name != first_name: changes.append('氏名')
                        if (emp.department.department_code if emp.department else '') != dept_code: changes.append('部署')
                        if (emp.position.name if emp.position else '') != pos_name: changes.append('役職')
                        if emp.current_hourly_rate != wage: changes.append('時給')
                        
                        row_info['changes'] = changes
                        row_info['old_wage'] = emp.current_hourly_rate
                        preview_data['update'].append(row_info)
                except Exception as e:
                    preview_data['error'].append({'line': i, 'reason': str(e), 'data': row})
            return render_template('csv/preview.html', preview=preview_data)
    return render_template('csv/import.html')

@app.route('/csv/import/execute', methods=['POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def csv_import_execute():
    new_rows = json.loads(request.form.get('new_rows', '[]'))
    update_rows = json.loads(request.form.get('update_rows', '[]'))
    try:
        # Auto-create
        for r in new_rows + update_rows:
            if r['department_code'] and not Department.query.filter_by(department_code=r['department_code']).first():
                db.session.add(Department(department_code=r['department_code'], name=f"ー_{r['department_code']}"))
            if r['position_name'] and not Position.query.filter_by(name=r['position_name']).first():
                db.session.add(Position(position_code=f"P_{r['position_name']}", name=r['position_name']))
        db.session.flush()

        # Process New
        for r in new_rows:
            if r['employee_code'] == SYSTEM_ADMIN_CODE:
                continue
            dept = Department.query.filter_by(department_code=r['department_code']).first() if r['department_code'] else None
            pos = Position.query.filter_by(name=r['position_name']).first() if r['position_name'] else None
            emp = Employee(
                employee_code=r['employee_code'], last_name=r['last_name'], first_name=r['first_name'],
                furigana_last=r['furigana_last'], furigana_first=r['furigana_first'],
                department_id=dept.id if dept else None, position_id=pos.id if pos else None, status='在職'
            )
            db.session.add(emp)
            db.session.flush()
            db.session.add(HourlyRateHistory(employee_id=emp.id, hourly_wage=r['hourly_wage'], start_date=datetime.now().date()))

        # Process Update
        for r in update_rows:
            if r['employee_code'] == SYSTEM_ADMIN_CODE:
                continue
            emp = Employee.query.filter_by(employee_code=r['employee_code']).first()
            dept = Department.query.filter_by(department_code=r['department_code']).first() if r['department_code'] else None
            pos = Position.query.filter_by(name=r['position_name']).first() if r['position_name'] else None
            emp.last_name, emp.first_name = r['last_name'], r['first_name']
            emp.furigana_last, emp.furigana_first = r['furigana_last'], r['furigana_first']
            emp.department_id = dept.id if dept else None
            emp.position_id = pos.id if pos else None
            if emp.current_hourly_rate != r['hourly_wage']:
                old_h = HourlyRateHistory.query.filter_by(employee_id=emp.id, end_date=None).first()
                if old_h: old_h.end_date = datetime.now().date() - timedelta(days=1)
                db.session.add(HourlyRateHistory(employee_id=emp.id, hourly_wage=r['hourly_wage'], start_date=datetime.now().date()))
        db.session.commit()
        flash(f'インポート完了（新規: {len(new_rows)}, 更新: {len(update_rows)}）', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'エラー: {str(e)}', 'error')
    return redirect(url_for('index'))

@app.route('/departments')
def department_list():
    query = Department.query.filter_by(is_active=True)
    code = request.args.get('code')
    name = request.args.get('name')
    if code: query = query.filter(Department.department_code.like(f"%{code}%"))
    if name: query = query.filter(Department.name.like(f"%{name}%"))
    page, per_page = get_pagination_params()
    departments = query.order_by(Department.department_code).paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        'departments/list.html',
        departments=departments,
        per_page_options=PER_PAGE_OPTIONS,
        pagination_args=get_pagination_args()
    )

@app.route('/departments/new', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def department_new():
    if request.method == 'POST':
        code, name = request.form.get('department_code'), request.form.get('name')
        if Department.query.filter_by(department_code=code).first():
            flash(f'部署コード {code} は使用中。', 'error')
            return render_template('departments/edit.html', department=None)
        db.session.add(Department(department_code=code, name=name))
        db.session.commit()
        flash('部署を登録しました。', 'success')
        return redirect(url_for('department_list'))
    return render_template('departments/edit.html', department=None)

@app.route('/departments/<int:id>/edit', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def department_edit(id):
    dept = Department.query.get_or_404(id)
    if request.method == 'POST':
        dept.department_code, dept.name = request.form.get('department_code'), request.form.get('name')
        db.session.commit()
        flash('部署情報を更新しました。', 'success')
        return redirect(url_for('department_list'))
    return render_template('departments/edit.html', department=dept)

@app.route('/departments/<int:id>/delete', methods=['POST'])
@permission_required(SYSTEM_KEY, 'delete', EMPLOYEE_DB_PATH)
def department_delete(id):
    dept = Department.query.get_or_404(id)
    if Employee.query.filter_by(department_id=dept.id).first():
        flash('この部署を使用している社員がいるため削除できません。先に社員の所属部署を変更してください。', 'error')
        return redirect(url_for('department_list'))
    db.session.delete(dept)
    db.session.commit()
    flash('部署を削除しました。', 'success')
    return redirect(url_for('department_list'))

@app.route('/positions')
def position_list():
    query = Position.query.filter_by(is_active=True)
    code = request.args.get('code')
    name = request.args.get('name')
    if code: query = query.filter(Position.position_code.like(f"%{code}%"))
    if name: query = query.filter(Position.name.like(f"%{name}%"))
    page, per_page = get_pagination_params()
    positions = query.order_by(Position.position_code).paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        'positions/list.html',
        positions=positions,
        per_page_options=PER_PAGE_OPTIONS,
        pagination_args=get_pagination_args()
    )

@app.route('/positions/new', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def position_new():
    if request.method == 'POST':
        code, name = request.form.get('position_code'), request.form.get('name')
        if Position.query.filter_by(position_code=code).first():
            flash(f'役職コード {code} は使用中。', 'error')
            return render_template('positions/edit.html', position=None)
        db.session.add(Position(position_code=code, name=name))
        db.session.commit()
        flash('役職を登録しました。', 'success')
        return redirect(url_for('position_list'))
    return render_template('positions/edit.html', position=None)

@app.route('/positions/<int:id>/edit', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def position_edit(id):
    pos = Position.query.get_or_404(id)
    if request.method == 'POST':
        pos.position_code, pos.name = request.form.get('position_code'), request.form.get('name')
        db.session.commit()
        flash('役職情報を更新しました。', 'success')
        return redirect(url_for('position_list'))
    return render_template('positions/edit.html', position=pos)

@app.route('/positions/<int:id>/delete', methods=['POST'])
@permission_required(SYSTEM_KEY, 'delete', EMPLOYEE_DB_PATH)
def position_delete(id):
    pos = Position.query.get_or_404(id)
    if Employee.query.filter_by(position_id=pos.id).first():
        flash('この役職を使用している社員がいるため削除できません。先に社員の役職を変更してください。', 'error')
        return redirect(url_for('position_list'))
    db.session.delete(pos)
    db.session.commit()
    flash('役職を削除しました。', 'success')
    return redirect(url_for('position_list'))

@app.route('/employees')
def employee_list():
    query = Employee.query.filter(*normal_employee_conditions())
    
    emp_code = request.args.get('emp_code')
    name = request.args.get('name')
    dept_id = request.args.get('dept_id')
    pos_id = request.args.get('pos_id')
    status = request.args.get('status')
    
    if emp_code:
        query = query.filter(Employee.employee_code.like(f"%{emp_code}%"))
    if name:
        search_name = f"%{name}%"
        query = query.filter(
            or_(
                Employee.last_name.like(search_name),
                Employee.first_name.like(search_name),
                Employee.furigana_last.like(search_name),
                Employee.furigana_first.like(search_name),
                db.func.concat(Employee.last_name, Employee.first_name).like(search_name),
                db.func.concat(Employee.last_name, ' ', Employee.first_name).like(search_name),
                db.func.concat(Employee.furigana_last, Employee.furigana_first).like(search_name),
                db.func.concat(Employee.furigana_last, ' ', Employee.furigana_first).like(search_name)
            )
        )
    if dept_id:
        query = query.filter(Employee.department_id == dept_id)
    if pos_id:
        query = query.filter(Employee.position_id == pos_id)
    if status:
        query = query.filter(Employee.status == status)

    page, per_page = get_pagination_params()
    employees = query.order_by(Employee.employee_code).paginate(page=page, per_page=per_page, error_out=False)

    # 候補表示用：必要なカラムのみを事前に取得（非同期通信の遅延による不具合を回避）
    all_emp_data = db.session.query(
        Employee.employee_code,
        Employee.last_name,
        Employee.first_name,
        Employee.furigana_last,
        Employee.furigana_first
    ).filter(*normal_employee_conditions()).all()

    departments = Department.query.filter_by(is_active=True).all()
    positions = Position.query.filter_by(is_active=True).all()

    return render_template('employees/list.html', 
                         employees=employees, 
                         all_emp_data=all_emp_data, 
                         departments=departments, 
                         positions=positions,
                         per_page_options=PER_PAGE_OPTIONS,
                         pagination_args=get_pagination_args())
@app.route('/employees/new', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def employee_new():
    departments, positions = Department.query.filter_by(is_active=True).all(), Position.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        code = request.form.get('employee_code')
        if code == SYSTEM_ADMIN_CODE:
            flash('ADMIN001 はシステム管理用アカウントのため通常社員として登録できません。', 'error')
            return render_template('employees/edit.html', employee=None, departments=departments, positions=positions)
        if Employee.query.filter_by(employee_code=code).first():
            flash(f'社員コード {code} は使用中。', 'error')
            return render_template('employees/edit.html', employee=None, departments=departments, positions=positions)

        new_emp = Employee(employee_code=code)
        apply_employee_form(new_emp, allow_code_change=False)
        db.session.add(new_emp)
        db.session.flush()
        
        hourly_wage = int(request.form.get('hourly_wage') or 0)
        db.session.add(HourlyRateHistory(employee_id=new_emp.id, hourly_wage=hourly_wage, start_date=datetime.now().date()))
        
        db.session.commit()
        flash('社員を登録しました。', 'success')
        return redirect(url_for('employee_list'))
    return render_template('employees/edit.html', employee=None, departments=departments, positions=positions)

@app.route('/employees/<int:id>')
def employee_detail(id):
    employee = get_normal_employee_or_404(id)
    return render_template('employees/detail.html', employee=employee)

@app.route('/employees/<int:id>/permissions', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'admin', EMPLOYEE_DB_PATH)
def employee_permissions(id):
    employee = get_normal_employee_or_404(id)
    current_permissions = {perm.system_key: perm for perm in employee.system_permissions}

    if request.method == 'POST':
        target_can_login = request.form.get('can_login') == '1'
        selected_roles = {}
        for system_key in SYSTEMS:
            use_system = request.form.get(f'use_{system_key}') == '1'
            role = request.form.get(f'role_{system_key}')
            if use_system and role in ROLE_LABELS.get(system_key, {}):
                selected_roles[system_key] = role

        if session.get('employee_id') == employee.id:
            if not target_can_login or selected_roles.get('employee') != 'admin':
                flash('自分自身のログイン許可と社員管理システム管理者権限は解除できません。', 'error')
                return render_template(
                    'employees/permissions.html',
                    employee=employee,
                    current_permissions=current_permissions,
                    role_labels=ROLE_LABELS,
                    systems=SYSTEMS
                )

        employee.can_login = target_can_login

        for system_key, existing in current_permissions.items():
            if system_key not in selected_roles:
                db.session.delete(existing)

        for system_key, role in selected_roles.items():
            perm = current_permissions.get(system_key)
            if perm:
                perm.role = role
            else:
                db.session.add(EmployeeSystemPermission(employee_id=employee.id, system_key=system_key, role=role))

        db.session.commit()
        flash('権限設定を更新しました。', 'success')
        return redirect(url_for('employee_list'))

    return render_template(
        'employees/permissions.html',
        employee=employee,
        current_permissions=current_permissions,
        role_labels=ROLE_LABELS,
        systems=SYSTEMS
    )

@app.route('/employees/<int:id>/edit', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def employee_edit(id):
    employee = get_normal_employee_or_404(id)
    departments, positions = Department.query.filter_by(is_active=True).all(), Position.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        status = request.form.get('status')
        retirement_date = to_date(request.form.get('retirement_date'))
        
        # Validation: status vs retirement_date
        if status != '退職' and retirement_date:
            flash('状態が「退職」以外の場合、退職日は入力できません。', 'error')
            return render_template('employees/edit.html', employee=employee, departments=departments, positions=positions)
        if status == '退職' and not retirement_date:
            flash('状態が「退職」の場合は、退職日を入力してください。', 'error')
            return render_template('employees/edit.html', employee=employee, departments=departments, positions=positions)

        apply_employee_form(employee, allow_code_change=False)
        employee.retirement_date = retirement_date
        
        new_hourly_wage = int(request.form.get('hourly_wage') or 0)
        if employee.current_hourly_rate != new_hourly_wage:
            old_h = HourlyRateHistory.query.filter_by(employee_id=employee.id, end_date=None).first()
            if old_h: 
                old_h.end_date = datetime.now().date() - timedelta(days=1)
            db.session.add(HourlyRateHistory(employee_id=employee.id, hourly_wage=new_hourly_wage, start_date=datetime.now().date()))

        db.session.commit()
        flash('社員情報を更新しました。', 'success')
        return redirect(url_for('employee_list'))
    return render_template('employees/edit.html', employee=employee, departments=departments, positions=positions)

@app.route('/employees/<int:id>/delete', methods=['POST'])
@permission_required(SYSTEM_KEY, 'delete', EMPLOYEE_DB_PATH)
def employee_delete(id):
    emp = get_normal_employee_or_404(id)
    HourlyRateHistory.query.filter_by(employee_id=emp.id).delete(synchronize_session=False)
    EmployeeSystemPermission.query.filter_by(employee_id=emp.id).delete(synchronize_session=False)
    db.session.delete(emp)
    db.session.commit()
    flash('社員を削除しました。', 'success')
    return redirect(url_for('employee_list'))

@app.cli.command("init-db")
def init_db():
    db.create_all()
    ensure_auth_schema(EMPLOYEE_DB_PATH)
    seed_initial_admin_from_env(EMPLOYEE_DB_PATH)
    print("Database initialized.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_auth_schema(EMPLOYEE_DB_PATH)
        seed_initial_admin_from_env(EMPLOYEE_DB_PATH)
    app.run(debug=True, port=5000)
