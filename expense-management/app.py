import os
import csv
import io
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, flash, request, make_response
from models import db, Account, ExpenseRecord
from sqlalchemy import asc, desc

app = Flask(__name__)
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'expense_management.db').replace('\\', '/')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'expense-secret-key'

db.init_app(app)

@app.route('/')
def index():
    return render_template('index.html')

# --- Account Master ---
@app.route('/accounts')
def account_list():
    # IN accounts ordered by display_order
    in_accounts = Account.query.filter_by(is_visible=True).order_by(Account.display_order.asc()).all()
    # OUT accounts ordered by code or name (no display_order concept for OUT)
    out_accounts = Account.query.filter_by(is_visible=False).order_by(Account.code.asc()).all()
    return render_template('accounts/list.html', in_accounts=in_accounts, out_accounts=out_accounts)

@app.route('/accounts/save_all', methods=['POST'])
def account_save_all():
    try:
        data = request.get_json()
        in_ids = data.get('in_ids', [])
        out_ids = data.get('out_ids', [])

        # Update IN accounts: is_visible=True, re-index display_order from 1
        for i, acc_id in enumerate(in_ids, start=1):
            acc = Account.query.get(acc_id)
            if acc:
                acc.is_visible = True
                acc.display_order = i

        # Update OUT accounts: is_visible=False, display_order=0
        for acc_id in out_ids:
            acc = Account.query.get(acc_id)
            if acc:
                acc.is_visible = False
                acc.display_order = 0
        
        db.session.commit()
        return {"status": "success", "message": "保存しました。"}
    except Exception as e:
        db.session.rollback()
        return {"status": "error", "message": str(e)}, 500

@app.route('/accounts/new', methods=['GET', 'POST'])
def account_new():
    if request.method == 'POST':
        code = request.form.get('code')
        name = request.form.get('name')
        is_visible = request.form.get('is_visible') == '1'
        
        if Account.query.filter_by(code=code).first():
            flash(f'科目コード {code} は既に使用されています。', 'error')
            accounts = Account.query.order_by(Account.code.asc()).all()
            return render_template('accounts/edit.html', account=None, accounts=accounts)
        
        # Get max display_order
        max_order = db.session.query(db.func.max(Account.display_order)).scalar() or 0
        new_account = Account(code=code, name=name, is_visible=is_visible, display_order=max_order + 1)
        db.session.add(new_account)
        db.session.commit()
        flash('勘定科目を登録しました。', 'success')
        return redirect(url_for('account_new'))
    
    accounts = Account.query.order_by(Account.code.asc()).all()
    return render_template('accounts/edit.html', account=None, accounts=accounts)

@app.route('/accounts/<int:id>/edit', methods=['GET', 'POST'])
def account_edit(id):
    account = Account.query.get_or_404(id)
    if request.method == 'POST':
        account.code = request.form.get('code')
        account.name = request.form.get('name')
        account.is_visible = request.form.get('is_visible') == '1'
        db.session.commit()
        flash('勘定科目を更新しました。', 'success')
        return redirect(url_for('account_new'))
    return render_template('accounts/edit_exclusive.html', account=account)

@app.route('/accounts/<int:id>/delete', methods=['POST'])
def account_delete(id):
    account = Account.query.get_or_404(id)
    if account.records:
        flash('この科目は既に使用されているため削除できません。非表示にしてください。', 'error')
    else:
        db.session.delete(account)
        db.session.commit()
        flash('勘定科目を削除しました。', 'success')
    return redirect(url_for('account_new'))

@app.route('/accounts/<int:id>/move/<direction>', methods=['POST'])
def account_move(id, direction):
    account = Account.query.get_or_404(id)
    if direction == 'up':
        other = Account.query.filter(Account.display_order < account.display_order).order_by(Account.display_order.desc()).first()
    else:
        other = Account.query.filter(Account.display_order > account.display_order).order_by(Account.display_order.asc()).first()
    
    if other:
        account.display_order, other.display_order = other.display_order, account.display_order
        db.session.commit()
    return redirect(url_for('account_list'))

# --- Expense Batch Entry ---
@app.route('/entry', methods=['GET', 'POST'])
def expense_entry():
    accounts = Account.query.filter_by(is_visible=True).order_by(Account.display_order.asc()).all()
    if request.method == 'POST':
        unit = request.form.get('unit')
        target_date_str = request.form.get('target_date')
        
        if not target_date_str:
            flash('日付を入力してください。', 'error')
            return render_template('entry.html', accounts=accounts)
        
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            
        count = 0
        for acc in accounts:
            amount_str = request.form.get(f'amount_{acc.id}')
            if amount_str and amount_str.strip():
                clean_amount = int(amount_str.replace(',', ''))
                if clean_amount != 0:
                    record = ExpenseRecord(
                        target_date=target_date,
                        account_id=acc.id,
                        amount=clean_amount,
                        unit=unit
                    )
                    db.session.add(record)
                    count += 1
        
        if count > 0:
            db.session.commit()
            flash(f'{count}件の経費データを登録しました。', 'success')
            return redirect(url_for('expense_entry'))
        else:
            flash('登録するデータがありません。', 'error')
            
    return render_template('entry.html', accounts=accounts)

# --- Expense Data Correction ---
@app.route('/correction')
def correction_search():
    unit = request.args.get('unit')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    query = ExpenseRecord.query.filter_by(is_deleted=False)
    if unit:
        query = query.filter(ExpenseRecord.unit == unit)
    if from_date:
        query = query.filter(ExpenseRecord.target_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
    if to_date:
        query = query.filter(ExpenseRecord.target_date <= datetime.strptime(to_date, '%Y-%m-%d').date())
    
    records = query.order_by(ExpenseRecord.target_date.desc(), ExpenseRecord.id.desc()).all()
    return render_template('correction/list.html', records=records)

@app.route('/correction/deleted')
def correction_deleted_list():
    records = ExpenseRecord.query.filter_by(is_deleted=True).order_by(ExpenseRecord.deleted_at.desc()).all()
    return render_template('correction/deleted_list.html', records=records)

@app.route('/correction/<int:id>/edit', methods=['GET', 'POST'])
def correction_edit(id):
    record = ExpenseRecord.query.filter_by(id=id, is_deleted=False).first_or_404()
    accounts = Account.query.order_by(Account.display_order.asc()).all()
    if request.method == 'POST':
        record.unit = request.form.get('unit')
        target_date_str = request.form.get('target_date')
        record.target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        record.amount = int(request.form.get('amount').replace(',', ''))
        record.account_id = int(request.form.get('account_id'))
        db.session.commit()
        flash('経費データを更新しました。', 'success')
        return redirect(url_for('correction_search'))
    return render_template('correction/edit.html', record=record, accounts=accounts)

@app.route('/correction/<int:id>/delete', methods=['POST'])
def correction_delete(id):
    record = ExpenseRecord.query.get_or_404(id)
    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    db.session.commit()
    flash('経費データを削除しました。（削除済み一覧から復元可能です）', 'success')
    return redirect(url_for('correction_search', **request.args))

@app.route('/correction/<int:id>/restore', methods=['POST'])
def correction_restore(id):
    record = ExpenseRecord.query.get_or_404(id)
    record.is_deleted = False
    record.deleted_at = None
    db.session.commit()
    flash('経費データを復元しました。', 'success')
    return redirect(url_for('correction_deleted_list'))

@app.route('/correction/<int:id>/purge', methods=['POST'])
def correction_purge(id):
    record = ExpenseRecord.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()
    flash('経費データを完全に削除しました。', 'success')
    return redirect(url_for('correction_deleted_list'))

# --- Expense Data Search/Output ---
@app.route('/search')
def expense_search():
    unit = request.args.get('unit')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    all_search = request.args.get('all_search') == '1'
    
    monthly_records = []
    daily_records = []
    
    # Priority: 1.Specific unit 2.All units if empty
    fetch_monthly = (unit == 'monthly') or (not unit)
    fetch_daily = (unit == 'daily') or (not unit)

    if fetch_monthly:
        query = ExpenseRecord.query.join(Account).filter(ExpenseRecord.unit == 'monthly', ExpenseRecord.is_deleted == False)
        if from_date:
            query = query.filter(ExpenseRecord.target_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
        if to_date:
            query = query.filter(ExpenseRecord.target_date <= datetime.strptime(to_date, '%Y-%m-%d').date())
        monthly_records = query.order_by(ExpenseRecord.target_date.desc(), Account.display_order.asc()).all()
        
    if fetch_daily:
        query = ExpenseRecord.query.join(Account).filter(ExpenseRecord.unit == 'daily', ExpenseRecord.is_deleted == False)
        if from_date:
            query = query.filter(ExpenseRecord.target_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
        if to_date:
            query = query.filter(ExpenseRecord.target_date <= datetime.strptime(to_date, '%Y-%m-%d').date())
        daily_records = query.order_by(ExpenseRecord.target_date.desc(), Account.display_order.asc()).all()
        
    return render_template('search/list.html', monthly_records=monthly_records, daily_records=daily_records)

@app.route('/search/csv')
def expense_csv():
    unit = request.args.get('unit')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    query = ExpenseRecord.query.filter_by(is_deleted=False)
    if unit:
        query = query.filter(ExpenseRecord.unit == unit)
    if from_date:
        query = query.filter(ExpenseRecord.target_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
    if to_date:
        query = query.filter(ExpenseRecord.target_date <= datetime.strptime(to_date, '%Y-%m-%d').date())
    
    records = query.order_by(ExpenseRecord.unit, ExpenseRecord.target_date.desc()).all()
    
    si = io.StringIO()
    si.write('\ufeff')
    writer = csv.writer(si, lineterminator='\r\n')
    writer.writerow(['計上単位', '計上日/年月', '科目コード', '科目名', '金額', '登録日時', '更新日時'])
    
    for r in records:
        date_str = r.target_date.strftime('%Y/%m') if r.unit == 'monthly' else r.target_date.strftime('%Y/%m/%d')
        unit_str = '月次' if r.unit == 'monthly' else '日次'
        writer.writerow([
            unit_str,
            date_str,
            r.account.code,
            r.account.name,
            r.amount,
            r.created_at.strftime('%Y/%m/%d %H:%M:%S'),
            r.updated_at.strftime('%Y/%m/%d %H:%M:%S')
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=expenses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5004)
