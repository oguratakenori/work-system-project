import os
import sys
from dotenv import load_dotenv
import csv
import io
import json
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, make_response, session
from models import db, Department, Product
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

load_dotenv()

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
employee_db_path = os.path.join(base_dir, '..', 'employee-management', 'instance', 'employee_management.db')
employee_db_path = os.path.abspath(employee_db_path).replace('\\', '/')
PROJECT_ROOT = os.path.abspath(os.path.join(base_dir, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from auth_utils import (
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

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///product_management.db'
app.config['SQLALCHEMY_BINDS'] = {
    'employee_db': f'sqlite:///{employee_db_path}'
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-default-key-please-change')
app.config['SESSION_COOKIE_NAME'] = 'product_management_session'

db.init_app(app)

SYSTEM_KEY = 'product'
EMPLOYEE_DB_PATH = employee_db_path

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
            return render_template('login.html', system_name='製品管理システム')
        sign_in(employee)
        if session.get('password_reset_required'):
            flash('初回ログインのため、新しいパスワードを設定してください。', 'warning')
            return redirect(url_for('initial_password_setup'))
        flash('ログインしました。', 'success')
        return redirect(safe_next_url(request.args.get('next')))
    return render_template('login.html', system_name='製品管理システム')

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
    return render_template('forgot_password.html', system_name='製品管理システム')

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

def to_date(s): return datetime.strptime(s, '%Y-%m-%d').date() if s else None

def get_departments_from_employee_db():
    return Department.query.filter_by(is_active=True).all()

@app.route('/')
def index():
    product_count = Product.query.filter_by(is_active=True).count()
    return render_template('index.html', product_count=product_count)

# --- Product ---
@app.route('/products')
def product_list():
    query = Product.query.filter_by(is_active=True)
    code = request.args.get('product_code')
    name = request.args.get('name')
    dept_id = request.args.get('department_id')
    
    if code: query = query.filter(Product.product_code.like(f"%{code}%"))
    if name: query = query.filter(Product.name.like(f"%{name}%"))
    if dept_id: query = query.filter(Product.department_id == dept_id)

    page, per_page = get_pagination_params()
    products = query.order_by(Product.product_code).paginate(page=page, per_page=per_page, error_out=False)
    departments = get_departments_from_employee_db()
    all_product_codes = [p.product_code for p in Product.query.with_entities(Product.product_code).filter_by(is_active=True).distinct().all()]
    return render_template(
        'products/list.html',
        products=products,
        departments=departments,
        all_product_codes=all_product_codes,
        per_page_options=PER_PAGE_OPTIONS,
        pagination_args=get_pagination_args()
    )

@app.route('/products/new', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def product_new():
    departments = get_departments_from_employee_db()
    if request.method == 'POST':
        dept_id = int(request.form.get('department_id'))
        code = request.form.get('product_code')
        
        # 有効なデータとの重複チェック
        if Product.query.filter_by(department_id=dept_id, product_code=code, is_active=True).first():
            flash('すでにその製品コードは使用されています。', 'error')
            return render_template('products/edit.html', product=None, departments=departments)
        
        # 削除済みデータの確認（再活性化）
        inactive_prod = Product.query.filter_by(department_id=dept_id, product_code=code, is_active=False).first()
        if inactive_prod:
            inactive_prod.name = request.form.get('name')
            inactive_prod.price = int(request.form.get('price', '0').replace(',', '') or 0)
            inactive_prod.registered_date = to_date(request.form.get('registered_date')) or datetime.now().date()
            inactive_prod.abolished_date = to_date(request.form.get('abolished_date'))
            inactive_prod.notes = request.form.get('notes')
            inactive_prod.is_active = True
            try:
                db.session.commit()
                flash('製品を登録しました。', 'success')
                return redirect(url_for('product_list'))
            except IntegrityError:
                db.session.rollback()
                flash('データベース制約エラー: 部署内で製品コードが重複しています。', 'error')
                return render_template('products/edit.html', product=None, departments=departments)

        # 新規作成
        new_prod = Product(
            department_id=dept_id,
            product_code=code,
            name=request.form.get('name'),
            price=int(request.form.get('price', '0').replace(',', '') or 0),
            registered_date=to_date(request.form.get('registered_date')) or datetime.now().date(),
            abolished_date=to_date(request.form.get('abolished_date')),
            notes=request.form.get('notes')
        )
        try:
            db.session.add(new_prod)
            db.session.commit()
            flash('製品を登録しました。', 'success')
            return redirect(url_for('product_list'))
        except IntegrityError:
            db.session.rollback()
            flash('データベース制約エラー: 部署内で製品コードが重複しています。', 'error')
            
    return render_template('products/edit.html', product=None, departments=departments)

@app.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@permission_required(SYSTEM_KEY, 'master_write', EMPLOYEE_DB_PATH)
def product_edit(id):
    product = Product.query.get_or_404(id)
    departments = get_departments_from_employee_db()
    if request.method == 'POST':
        dept_id = int(request.form.get('department_id'))
        code = request.form.get('product_code')
        
        # 自分以外の重複チェック（有効・無効問わずDB制約に抵触するため）
        existing = Product.query.filter_by(department_id=dept_id, product_code=code).first()
        if existing and existing.id != product.id:
            if existing.is_active:
                flash('すでにその製品コードは使用されています。', 'error')
            else:
                flash('この製品コードは削除済みデータとして存在するため使用できません。新規登録画面から再登録してください。', 'error')
            return render_template('products/edit.html', product=product, departments=departments)

        product.department_id = dept_id
        product.product_code = code
        product.name = request.form.get('name')
        product.price = int(request.form.get('price', '0').replace(',', '') or 0)
        product.registered_date = to_date(request.form.get('registered_date')) or product.registered_date
        product.abolished_date = to_date(request.form.get('abolished_date'))
        product.notes = request.form.get('notes')
        
        try:
            db.session.commit()
            flash('製品情報を更新しました。', 'success')
            return redirect(url_for('product_list'))
        except IntegrityError:
            db.session.rollback()
            flash('データベース制約エラー: 部署内で製品コードが重複しています。', 'error')

    return render_template('products/edit.html', product=product, departments=departments)

@app.route('/products/<int:id>/delete', methods=['POST'])
@permission_required(SYSTEM_KEY, 'delete', EMPLOYEE_DB_PATH)
def product_delete(id):
    prod = Product.query.get_or_404(id)
    prod.is_active = False
    db.session.commit()
    flash('製品を削除しました。', 'success')
    return redirect(url_for('product_list'))

# --- CSV ---
@app.route('/csv/export')
def csv_export():
    products = Product.query.filter_by(is_active=True).all()
    si = io.StringIO()
    si.write('\ufeff')
    writer = csv.writer(si, lineterminator='\r\n')
    writer.writerow(['department_code', 'product_code', 'name', 'price', 'registered_date', 'abolished_date', 'notes'])
    for p in products:
        writer.writerow([
            p.department.department_code if p.department else '',
            p.product_code, p.name, p.price,
            p.registered_date.strftime('%Y-%m-%d') if p.registered_date else '',
            p.abolished_date.strftime('%Y-%m-%d') if p.abolished_date else '',
            p.notes or ''
        ])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
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
            csv_input = list(csv.DictReader(stream))
            
            preview_data = {'new': [], 'update': [], 'error': []}
            
            for i, row in enumerate(csv_input, start=2):
                try:
                    dept_code = row.get('department_code')
                    p_code = row.get('product_code')
                    name = row.get('name', '')
                    price_str = row.get('price', '0')
                    reg_date_str = row.get('registered_date', '')
                    abolish_date_str = row.get('abolished_date', '')
                    notes = row.get('notes', '')

                    if not dept_code or not p_code:
                        preview_data['error'].append({'line': i, 'reason': '部署コードまたは製品コードが空です。', 'data': row})
                        continue
                    
                    dept = Department.query.filter_by(department_code=dept_code).first()
                    if not dept:
                        preview_data['error'].append({'line': i, 'reason': f'部署コード {dept_code} が見つかりません。', 'data': row})
                        continue

                    price = int(price_str) if price_str else 0
                    reg_date = reg_date_str if reg_date_str else datetime.now().strftime('%Y-%m-%d')
                    
                    prod = Product.query.filter_by(department_id=dept.id, product_code=p_code).first()

                    row_info = {
                        'line': i, 'department_code': dept_code, 'department_name': dept.name, 'department_id': dept.id,
                        'product_code': p_code, 'name': name, 'price': price, 
                        'registered_date': reg_date, 'abolished_date': abolish_date_str, 'notes': notes
                    }

                    if not prod:
                        preview_data['new'].append(row_info)
                    else:
                        changes = []
                        if prod.name != name: changes.append('製品名')
                        if prod.price != price: changes.append('単価')
                        if (prod.registered_date.strftime('%Y-%m-%d') if prod.registered_date else '') != reg_date: changes.append('登録日')
                        if (prod.abolished_date.strftime('%Y-%m-%d') if prod.abolished_date else '') != abolish_date_str: changes.append('廃止日')
                        if (prod.notes or '') != notes: changes.append('備考')
                        
                        if prod.is_active == False: changes.append('有効化(復元)')
                        
                        row_info['changes'] = changes
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
        # Process New
        for r in new_rows:
            prod = Product(
                department_id=r['department_id'], product_code=r['product_code'], name=r['name'],
                price=r['price'], registered_date=to_date(r['registered_date']),
                abolished_date=to_date(r['abolished_date']), notes=r['notes'], is_active=True
            )
            db.session.add(prod)

        # Process Update
        for r in update_rows:
            prod = Product.query.filter_by(department_id=r['department_id'], product_code=r['product_code']).first()
            if prod:
                prod.name = r['name']
                prod.price = r['price']
                prod.registered_date = to_date(r['registered_date'])
                prod.abolished_date = to_date(r['abolished_date'])
                prod.notes = r['notes']
                prod.is_active = True
                
        db.session.commit()
        flash(f'インポート完了（新規: {len(new_rows)}, 更新: {len(update_rows)}）', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'エラー: {str(e)}', 'error')
    return redirect(url_for('index'))

@app.cli.command("init-db")
def init_db():
    db.create_all(bind_key=None)
    ensure_auth_schema(EMPLOYEE_DB_PATH)
    seed_initial_admin_from_env(EMPLOYEE_DB_PATH)
    print("Database initialized.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all(bind_key=None)
        ensure_auth_schema(EMPLOYEE_DB_PATH)
        seed_initial_admin_from_env(EMPLOYEE_DB_PATH)
    app.run(debug=True, port=5001)
