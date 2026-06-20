import os
import sqlite3
from functools import wraps

from flask import flash, g, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


SYSTEMS = {
    "employee": "社員管理システム",
    "product": "製品管理システム",
    "work_record": "作業実績管理システム",
    "expense": "経費管理システム",
}

SYSTEM_ADMIN_CODE = "ADMIN001"

ROLE_LABELS = {
    "employee": {
        "admin": "管理者",
        "staff": "担当者",
    },
    "product": {
        "admin": "管理者",
        "staff": "担当者",
    },
    "work_record": {
        "admin": "管理者",
        "editor": "編集担当",
        "input": "入力担当",
    },
    "expense": {
        "admin": "管理者",
        "editor": "編集担当",
        "input": "入力担当",
    },
}

ROLE_CAPABILITIES = {
    "employee": {
        "admin": {"system_access", "master_write", "delete", "admin"},
        "staff": {"system_access", "master_write"},
    },
    "product": {
        "admin": {"system_access", "master_write", "delete"},
        "staff": {"system_access", "master_write"},
    },
    "work_record": {
        "admin": {"system_access", "master_write", "master_delete", "record_write", "record_delete"},
        "editor": {"system_access", "master_write", "record_write", "record_delete"},
        "input": {"system_access", "record_write"},
    },
    "expense": {
        "admin": {"system_access", "master_write", "master_delete", "record_write", "record_delete"},
        "editor": {"system_access", "master_write", "record_write", "record_delete"},
        "input": {"system_access", "record_write"},
    },
}

EMPLOYEE_EXTRA_COLUMNS = {
    "password_hash": "TEXT",
    "password_reset_required": "INTEGER DEFAULT 0",
    "can_login": "INTEGER DEFAULT 0",
    "postal_code": "TEXT",
    "address1": "TEXT",
    "address2": "TEXT",
    "address1_furigana": "TEXT",
    "address2_furigana": "TEXT",
    "phone_number": "TEXT",
    "birth_date": "DATE",
    "notes": "TEXT",
    "is_system_user": "INTEGER DEFAULT 0",
}


def get_employee_db_path(app_base_dir):
    project_root = os.path.abspath(os.path.join(app_base_dir, ".."))
    return os.path.join(project_root, "employee-management", "instance", "employee_management.db")


def connect_employee_db(employee_db_path):
    conn = sqlite3.connect(employee_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_auth_schema(employee_db_path):
    os.makedirs(os.path.dirname(employee_db_path), exist_ok=True)
    conn = connect_employee_db(employee_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(employees)")
        columns = {row["name"] for row in cursor.fetchall()}
        if columns:
            for name, ddl in EMPLOYEE_EXTRA_COLUMNS.items():
                if name not in columns:
                    cursor.execute(f"ALTER TABLE employees ADD COLUMN {name} {ddl}")
            cursor.execute(
                "UPDATE employees SET is_system_user = 1 WHERE employee_code = ?",
                (SYSTEM_ADMIN_CODE,),
            )
            cursor.execute(
                "UPDATE employees SET password_reset_required = 0 WHERE employee_code = ?",
                (SYSTEM_ADMIN_CODE,),
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS employee_system_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                system_key TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(employee_id, system_key),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_initial_admin_from_env(employee_db_path):
    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not password:
        return None

    ensure_auth_schema(employee_db_path)
    conn = connect_employee_db(employee_db_path)
    try:
        cursor = conn.cursor()
        employees_table = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'employees'"
        ).fetchone()
        if not employees_table:
            return None
        row = cursor.execute(
            "SELECT id, password_hash FROM employees WHERE employee_code = ?",
            ("ADMIN001",),
        ).fetchone()
        password_hash = generate_password_hash(password)
        if row:
            employee_id = row["id"]
            if not row["password_hash"] or os.getenv("RESET_INITIAL_ADMIN_PASSWORD") == "1":
                cursor.execute(
                    """
                    UPDATE employees
                    SET password_hash = ?, can_login = 1, is_system_user = 1, password_reset_required = 0
                    WHERE id = ?
                    """,
                    (password_hash, employee_id),
                )
            else:
                cursor.execute(
                    "UPDATE employees SET can_login = 1, is_system_user = 1, password_reset_required = 0 WHERE id = ?",
                    (employee_id,),
                )
        else:
            cursor.execute(
                """
                INSERT INTO employees (
                    employee_code, last_name, first_name, furigana_last, furigana_first,
                    status, is_active, can_login, password_hash, is_system_user, password_reset_required, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, 1, 0, CURRENT_TIMESTAMP)
                """,
                (SYSTEM_ADMIN_CODE, "初期", "管理者", "ショキ", "カンリシャ", "在職", password_hash),
            )
            employee_id = cursor.lastrowid

        for system_key in SYSTEMS:
            cursor.execute(
                """
                INSERT INTO employee_system_permissions (employee_id, system_key, role, updated_at)
                VALUES (?, ?, 'admin', CURRENT_TIMESTAMP)
                ON CONFLICT(employee_id, system_key)
                DO UPDATE SET role = excluded.role, updated_at = CURRENT_TIMESTAMP
                """,
                (employee_id, system_key),
            )
        conn.commit()
        return "ADMIN001"
    finally:
        conn.close()


def load_employee_by_code(employee_db_path, employee_code):
    ensure_auth_schema(employee_db_path)
    conn = connect_employee_db(employee_db_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'employees'"
        ).fetchone()
        if not table:
            return None
        row = conn.execute(
            """
            SELECT id, employee_code, last_name, first_name, password_hash, can_login, is_active
                 , COALESCE(is_system_user, 0) AS is_system_user
                 , COALESCE(password_reset_required, 0) AS password_reset_required
            FROM employees
            WHERE employee_code = ?
            """,
            (employee_code,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_permissions(employee_db_path, employee_id):
    ensure_auth_schema(employee_db_path)
    conn = connect_employee_db(employee_db_path)
    try:
        employee = conn.execute(
            "SELECT employee_code, COALESCE(is_system_user, 0) AS is_system_user FROM employees WHERE id = ?",
            (employee_id,),
        ).fetchone()
        if employee and (employee["employee_code"] == SYSTEM_ADMIN_CODE or employee["is_system_user"]):
            return {system_key: "admin" for system_key in SYSTEMS}

        rows = conn.execute(
            "SELECT system_key, role FROM employee_system_permissions WHERE employee_id = ?",
            (employee_id,),
        ).fetchall()
        return {row["system_key"]: row["role"] for row in rows}
    finally:
        conn.close()


def authenticate_employee(employee_db_path, employee_code, password, system_key):
    employee = load_employee_by_code(employee_db_path, employee_code)
    if not employee or not employee.get("is_active"):
        return None, "社員コードまたはパスワードが正しくありません。"
    if not employee.get("can_login"):
        return None, "ログインが許可されていません。"

    is_system_user = employee["employee_code"] == SYSTEM_ADMIN_CODE or employee.get("is_system_user")
    password_reset_required = bool(employee.get("password_reset_required")) and not is_system_user
    if is_system_user:
        if not employee.get("password_hash"):
            return None, "パスワードが設定されていません。"
        if not check_password_hash(employee["password_hash"], password):
            return None, "社員コードまたはパスワードが正しくありません。"
        password_reset_required = False
    elif not employee.get("password_hash") or password_reset_required:
        if password != employee["employee_code"]:
            return None, "社員コードまたはパスワードが正しくありません。"
        password_reset_required = True
    elif not check_password_hash(employee["password_hash"], password):
        return None, "社員コードまたはパスワードが正しくありません。"

    permissions = get_permissions(employee_db_path, employee["id"])
    role = permissions.get(system_key)
    if role not in ROLE_CAPABILITIES.get(system_key, {}):
        return None, "このシステムを利用する権限がありません。"

    employee["name"] = f"{employee['last_name']} {employee['first_name']}"
    employee["permissions"] = permissions
    employee["password_reset_required"] = password_reset_required
    return employee, None


def set_initial_password(employee_db_path, employee_id, new_password, confirm_password):
    if not employee_id:
        return False, "ログイン情報を確認できません。もう一度ログインしてください。"
    if not new_password or not confirm_password:
        return False, "すべての項目を入力してください。"
    if new_password != confirm_password:
        return False, "新しいパスワードと確認用パスワードが一致しません。"

    ensure_auth_schema(employee_db_path)
    conn = connect_employee_db(employee_db_path)
    try:
        employee = conn.execute(
            """
            SELECT id, employee_code, password_hash, is_active, can_login
                 , COALESCE(is_system_user, 0) AS is_system_user
                 , COALESCE(password_reset_required, 0) AS password_reset_required
            FROM employees
            WHERE id = ?
            """,
            (employee_id,),
        ).fetchone()
        if not employee or not employee["is_active"]:
            return False, "ログイン情報を確認できません。もう一度ログインしてください。"
        if employee["employee_code"] == SYSTEM_ADMIN_CODE or employee["is_system_user"]:
            return False, "このユーザーは初回パスワード設定の対象外です。"
        if not employee["can_login"]:
            return False, "ログインが許可されていません。"
        if employee["password_hash"] and not employee["password_reset_required"]:
            return False, "初回パスワード設定は完了しています。"
        if new_password == employee["employee_code"]:
            return False, "新しいパスワードには社員コード以外を設定してください。"

        conn.execute(
            """
            UPDATE employees
            SET password_hash = ?, password_reset_required = 0
            WHERE id = ?
            """,
            (generate_password_hash(new_password), employee_id),
        )
        conn.commit()
        return True, "初回パスワードを設定しました。"
    finally:
        conn.close()


def reset_password_by_admin(employee_db_path, target_employee_code, admin_employee_code, admin_password):
    target_employee_code = (target_employee_code or "").strip()
    admin_employee_code = (admin_employee_code or "").strip()
    if not target_employee_code or not admin_employee_code or not admin_password:
        return False, "すべての項目を入力してください。"

    ensure_auth_schema(employee_db_path)
    conn = connect_employee_db(employee_db_path)
    try:
        target = conn.execute(
            """
            SELECT id, employee_code, is_active, can_login
                 , COALESCE(is_system_user, 0) AS is_system_user
            FROM employees
            WHERE employee_code = ?
            """,
            (target_employee_code,),
        ).fetchone()
        if not target or not target["is_active"]:
            return False, "対象社員コードが存在しません。"
        if target["employee_code"] == SYSTEM_ADMIN_CODE or target["is_system_user"]:
            return False, "システム管理用ユーザーはこの画面では初期化できません。"
        if not target["can_login"]:
            return False, "対象社員はログインが許可されていません。"

        admin = conn.execute(
            """
            SELECT id, employee_code, password_hash, is_active, can_login
                 , COALESCE(is_system_user, 0) AS is_system_user
                 , COALESCE(password_reset_required, 0) AS password_reset_required
            FROM employees
            WHERE employee_code = ?
            """,
            (admin_employee_code,),
        ).fetchone()
        if not admin or not admin["is_active"]:
            return False, "管理者社員コードまたはパスワードが正しくありません。"
        if not admin["can_login"]:
            return False, "管理者はログインが許可されていません。"

        admin_is_system_user = admin["employee_code"] == SYSTEM_ADMIN_CODE or admin["is_system_user"]
        if not admin_is_system_user and admin["password_reset_required"]:
            return False, "管理者の初回パスワード設定が完了していません。"
        if not admin["password_hash"] or not check_password_hash(admin["password_hash"], admin_password):
            return False, "管理者社員コードまたはパスワードが正しくありません。"

        permissions = get_permissions(employee_db_path, admin["id"])
        if not admin_is_system_user and permissions.get("employee") != "admin":
            return False, "管理者に社員管理システム管理者権限がありません。"

        conn.execute(
            "UPDATE employees SET password_reset_required = 1 WHERE id = ?",
            (target["id"],),
        )
        conn.commit()
        return True, (
            "パスワードを初期化しました。"
            "対象社員は、社員コードと同じ初期パスワードでログインしてください。"
            "ログイン後、新しいパスワード設定画面が表示されます。"
        )
    finally:
        conn.close()


def change_own_password(employee_db_path, employee_id, current_password, new_password, confirm_password):
    if not employee_id:
        return False, "ログイン情報を確認できません。もう一度ログインしてください。"
    if not current_password or not new_password or not confirm_password:
        return False, "すべての項目を入力してください。"
    if new_password != confirm_password:
        return False, "新しいパスワードと確認用パスワードが一致しません。"

    ensure_auth_schema(employee_db_path)
    conn = connect_employee_db(employee_db_path)
    try:
        employee = conn.execute(
            """
            SELECT id, employee_code, password_hash, is_active, can_login
            FROM employees
            WHERE id = ?
            """,
            (employee_id,),
        ).fetchone()
        if not employee or not employee["is_active"]:
            return False, "ログイン情報を確認できません。もう一度ログインしてください。"
        if not employee["can_login"]:
            return False, "ログインが許可されていません。"
        if not employee["password_hash"]:
            return False, "パスワードが設定されていません。"
        if not check_password_hash(employee["password_hash"], current_password):
            return False, "現在のパスワードが正しくありません。"

        conn.execute(
            "UPDATE employees SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), employee_id),
        )
        conn.commit()
        return True, "パスワードを変更しました。"
    finally:
        conn.close()


def sign_in(employee):
    session.clear()
    session["employee_id"] = employee["id"]
    session["employee_code"] = employee["employee_code"]
    session["employee_name"] = employee["name"]
    session["permissions"] = employee["permissions"]
    session["password_reset_required"] = bool(employee.get("password_reset_required"))


def sign_out():
    session.clear()


def current_user():
    if not session.get("employee_code"):
        return None
    return {
        "id": session.get("employee_id"),
        "employee_code": session.get("employee_code"),
        "name": session.get("employee_name"),
        "password_reset_required": session.get("password_reset_required"),
    }


def current_role(system_key):
    return (session.get("permissions") or {}).get(system_key)


def current_role_label(system_key):
    role = current_role(system_key)
    return ROLE_LABELS.get(system_key, {}).get(role, "")


def has_capability(system_key, capability):
    role = current_role(system_key)
    return capability in ROLE_CAPABILITIES.get(system_key, {}).get(role, set())


def has_system_access(system_key):
    return has_capability(system_key, "system_access")


def forbidden_response(message="権限がありません。"):
    html = """
    <!doctype html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>権限エラー</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-5">
            <div class="card border-0 shadow-sm mx-auto" style="max-width: 560px;">
                <div class="card-body p-4 text-center">
                    <h1 class="h4 mb-3">権限エラー</h1>
                    <p class="text-muted mb-4">{{ message }}</p>
                    <a class="btn btn-secondary" href="{{ url_for('logout') }}">ログイン画面へ戻る</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, message=message), 403


def require_login_for_request(system_key, employee_db_path, exempt_endpoints=None):
    exempt_endpoints = set(exempt_endpoints or ())
    if request.endpoint in exempt_endpoints or request.endpoint == "static":
        return None
    if not session.get("employee_code"):
        return redirect(url_for("login", next=request.full_path))

    ensure_auth_schema(employee_db_path)
    permissions = get_permissions(employee_db_path, session["employee_id"])
    session["permissions"] = permissions
    if not has_system_access(system_key):
        return forbidden_response("このシステムを利用する権限がありません。")
    if session.get("password_reset_required") and request.endpoint != "initial_password_setup":
        return redirect(url_for("initial_password_setup"))
    g.current_user = current_user()
    return None


def permission_required(system_key, capability, employee_db_path):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            guard = require_login_for_request(system_key, employee_db_path, {"login", "logout"})
            if guard:
                return guard
            if not has_capability(system_key, capability):
                return forbidden_response("この操作を実行する権限がありません。")
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def auth_context(system_key):
    return {
        "current_user": current_user(),
        "current_role_label": current_role_label(system_key),
        "has_permission": lambda capability: has_capability(system_key, capability),
        "system_name": SYSTEMS.get(system_key, ""),
        "system_role_labels": ROLE_LABELS,
        "systems": SYSTEMS,
    }
