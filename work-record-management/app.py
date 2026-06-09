import os
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from models import db, Department, Work, PerformanceRecord
import crud
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret_key')

# Database Configuration
database_url = os.getenv('DATABASE_URL')
if not database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///taskapp.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def seed_data():
    if crud.get_all_departments() == []:
        # Seed Departments
        crud.add_department('D001', '製造1課')
        crud.add_department('D002', '製造2課')

        # Seed Works
        crud.add_work('W001', '組立', 'D001')
        crud.add_work('W002', '加工', 'D002')

# 1. Menu Screen
@app.route('/')
def index():
    return render_template('index.html')

# 2. Master Management
@app.route('/masters')
def masters_menu():
    return render_template('masters/menu.html')

@app.route('/masters/departments', methods=['GET', 'POST'])
def manage_departments():
    if request.method == 'POST':
        code = request.form.get('department_code')
        name = request.form.get('name')
        if code and name:
            crud.add_department(code, name)
            flash('部署を追加しました')
        return redirect(url_for('manage_departments'))
    departments = crud.get_all_departments()
    return render_template('masters/departments.html', departments=departments)

@app.route('/masters/works', methods=['GET', 'POST'])
def manage_works():
    if request.method == 'POST':
        code = request.form.get('work_code')
        name = request.form.get('name')
        dept_code = request.form.get('department_code')
        if name:
            crud.add_work(code, name, dept_code)
            flash('作業を追加しました')
        return redirect(url_for('manage_works'))
    works = crud.get_all_works()
    departments = crud.get_all_departments()
    return render_template('masters/works.html', works=works, departments=departments)

# 3. Performance Input
@app.route('/performance/input', methods=['GET', 'POST'])
def performance_input():
    if request.method == 'POST':
        data = {
            'work_date': request.form.get('work_date'),
            'employee_code': request.form.get('employee_code'),
            'department_code': request.form.get('department_code'),
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
    
    departments = crud.get_all_departments()
    works = crud.get_all_works()
    return render_template('performance/input.html', departments=departments, works=works)

# 4. Performance List
@app.route('/performance/list')
def performance_list():
    filters = {
        'employee_code': request.args.get('employee_code'),
        'department_code': request.args.get('department_code')
    }
    records = crud.get_performance_records(filters)
    departments = crud.get_all_departments()
    return render_template('performance/list.html', records=records, departments=departments)

# 5. Reports
@app.route('/reports', methods=['GET'])
def reports():
    filters = {
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date')
    }
    records = crud.get_performance_records(filters)
    
    if request.args.get('export') == 'csv':
        output = StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['作業日', '社員コード', '部署コード', '作業コード', '製品コード', '作業時間', '数量'])
        for r in records:
            writer.writerow([r.work_date, r.employee_code, r.department_code, r.work_code, r.product_code, r.work_hours, r.quantity])
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=performance_report.csv'
        return response

    return render_template('reports/index.html', records=records)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True)
