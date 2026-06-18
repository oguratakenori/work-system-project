import os
import csv
import io
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, make_response
from models import db, Department, Position, Employee, HourlyRateHistory
from sqlalchemy import or_

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__)); db_path = os.path.join(base_dir, 'instance', 'employee_management.db').replace('\\\\ ', '/'); app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key'

db.init_app(app)

@app.route('/')
def index():
    employee_count = Employee.query.filter_by(is_active=True).count()
    dept_count = Department.query.filter_by(is_active=True).count()
    return render_template('index.html', employee_count=employee_count, dept_count=dept_count)

# --- CSV Export ---
@app.route('/csv/export')
def csv_export():
    employees = Employee.query.filter_by(is_active=True).all()
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
    departments = query.all()
    return render_template('departments/list.html', departments=departments)

@app.route('/departments/new', methods=['GET', 'POST'])
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
def department_edit(id):
    dept = Department.query.get_or_404(id)
    if request.method == 'POST':
        dept.department_code, dept.name = request.form.get('department_code'), request.form.get('name')
        db.session.commit()
        flash('部署情報を更新しました。', 'success')
        return redirect(url_for('department_list'))
    return render_template('departments/edit.html', department=dept)

@app.route('/departments/<int:id>/delete', methods=['POST'])
def department_delete(id):
    dept = Department.query.get_or_404(id)
    dept.is_active = False
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
    positions = query.all()
    return render_template('positions/list.html', positions=positions)

@app.route('/positions/new', methods=['GET', 'POST'])
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
def position_edit(id):
    pos = Position.query.get_or_404(id)
    if request.method == 'POST':
        pos.position_code, pos.name = request.form.get('position_code'), request.form.get('name')
        db.session.commit()
        flash('役職情報を更新しました。', 'success')
        return redirect(url_for('position_list'))
    return render_template('positions/edit.html', position=pos)

@app.route('/positions/<int:id>/delete', methods=['POST'])
def position_delete(id):
    pos = Position.query.get_or_404(id)
    pos.is_active = False
    db.session.commit()
    flash('役職を削除しました。', 'success')
    return redirect(url_for('position_list'))

@app.route('/employees')
def employee_list():
    query = Employee.query.filter_by(is_active=True)
    
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

    employees = query.all()

    # 候補表示用：必要なカラムのみを事前に取得（非同期通信の遅延による不具合を回避）
    all_emp_data = db.session.query(
        Employee.employee_code,
        Employee.last_name,
        Employee.first_name,
        Employee.furigana_last,
        Employee.furigana_first
    ).filter(Employee.is_active == True).all()

    departments = Department.query.filter_by(is_active=True).all()
    positions = Position.query.filter_by(is_active=True).all()

    return render_template('employees/list.html', 
                         employees=employees, 
                         all_emp_data=all_emp_data, 
                         departments=departments, 
                         positions=positions)
@app.route('/employees/new', methods=['GET', 'POST'])
def employee_new():
    departments, positions = Department.query.filter_by(is_active=True).all(), Position.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        code = request.form.get('employee_code')
        if Employee.query.filter_by(employee_code=code).first():
            flash(f'社員コード {code} は使用中。', 'error')
            return render_template('employees/edit.html', employee=None, departments=departments, positions=positions)
        
        def to_date(s): return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        
        new_emp = Employee(
            employee_code=code, last_name=request.form.get('last_name'), first_name=request.form.get('first_name'),
            furigana_last=request.form.get('furigana_last'), furigana_first=request.form.get('furigana_first'),
            department_id=request.form.get('department_id') or None, position_id=request.form.get('position_id') or None,
            hire_date=to_date(request.form.get('hire_date')), retirement_date=to_date(request.form.get('retirement_date')),
            status=request.form.get('status')
        )
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
    employee = Employee.query.get_or_404(id)
    return render_template('employees/detail.html', employee=employee)

@app.route('/employees/<int:id>/edit', methods=['GET', 'POST'])
def employee_edit(id):
    employee = Employee.query.get_or_404(id)
    departments, positions = Department.query.filter_by(is_active=True).all(), Position.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        def to_date(s): return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        
        status = request.form.get('status')
        retirement_date = to_date(request.form.get('retirement_date'))
        
        # Validation: status vs retirement_date
        if status != '退職' and retirement_date:
            flash('状態が「退職」以外の場合、退職日は入力できません。', 'error')
            return render_template('employees/edit.html', employee=employee, departments=departments, positions=positions)
        if status == '退職' and not retirement_date:
            flash('状態が「退職」の場合は、退職日を入力してください。', 'error')
            return render_template('employees/edit.html', employee=employee, departments=departments, positions=positions)

        employee.employee_code, employee.last_name, employee.first_name = request.form.get('employee_code'), request.form.get('last_name'), request.form.get('first_name')
        employee.furigana_last, employee.furigana_first = request.form.get('furigana_last'), request.form.get('furigana_first')
        employee.department_id = request.form.get('department_id') or None
        employee.position_id = request.form.get('position_id') or None
        employee.hire_date = to_date(request.form.get('hire_date'))
        employee.retirement_date = retirement_date
        employee.status = status
        
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
def employee_delete(id):
    emp = Employee.query.get_or_404(id)
    emp.is_active, emp.status = False, '退職'
    db.session.commit()
    flash('社員を削除しました。', 'success')
    return redirect(url_for('employee_list'))

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, port=5000)
