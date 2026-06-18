import os
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify
from models import db, Work, PerformanceRecord
import crud
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-default-key-please-change')

# Database Configuration
database_url = os.getenv('DATABASE_URL')
if not database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///taskapp.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

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
def manage_works():
    filters = {
        'work_code': request.args.get('work_code'),
        'name': request.args.get('name'),
        'department_id': request.args.get('department_id')
    }
    works = crud.get_works(filters)
    departments = crud.get_external_departments()
    dept_map = crud.get_department_map()
    return render_template('masters/works.html', works=works, departments=departments, dept_map=dept_map)

@app.route('/masters/works/new', methods=['GET', 'POST'])
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
def edit_work(id):
    code = request.form.get('work_code')
    name = request.form.get('name')
    dept_id = request.form.get('department_id')
    crud.update_work(id, code, name, dept_id)
    flash('作業情報を更新しました')
    return redirect(url_for('manage_works'))

@app.route('/masters/works/delete/<int:id>')
def delete_work(id):
    crud.delete_work(id)
    flash('作業を削除しました')
    return redirect(url_for('manage_works'))

# 3. Performance Input
@app.route('/performance/input', methods=['GET', 'POST'])
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
    records = crud.get_performance_records(filters)
    
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
                           work_dept_map=work_dept_map)

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
        seed_data()
    app.run(debug=True, port=5003)
