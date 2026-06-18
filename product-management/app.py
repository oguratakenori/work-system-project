import os
from dotenv import load_dotenv
import csv
import io
import json
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, make_response
from models import db, Department, Product
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

load_dotenv()

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
employee_db_path = os.path.join(base_dir, '..', 'employee-management', 'instance', 'employee_management.db')
employee_db_path = os.path.abspath(employee_db_path).replace('\\', '/')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///product_management.db'
app.config['SQLALCHEMY_BINDS'] = {
    'employee_db': f'sqlite:///{employee_db_path}'
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-default-key-please-change')

db.init_app(app)

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

    products = query.all()
    departments = get_departments_from_employee_db()
    all_product_codes = [p.product_code for p in Product.query.with_entities(Product.product_code).filter_by(is_active=True).distinct().all()]
    return render_template('products/list.html', products=products, departments=departments, all_product_codes=all_product_codes)

@app.route('/products/new', methods=['GET', 'POST'])
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
    # employee_db は触らず、デフォルトの product_management.db だけを作成する
    db.create_all(bind_key=None)
    print("Database initialized.")

if __name__ == '__main__':
    with app.app_context(): db.create_all(bind_key=None)
    app.run(debug=True, port=5001)
