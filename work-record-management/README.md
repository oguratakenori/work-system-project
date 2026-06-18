# 作業実績管理システム (Task Performance Manager)

工場や製造現場での実績記録・集計を効率化する、軽量かつ多機能なWebアプリケーションです。

## ✨ 特徴
- **入力支援**: 社員番号のオートコンプリート機能により、現場での入力をスピードアップ。
- **マルチDB**: SQLiteで即座に開発、PostgreSQLで堅牢な運用が可能。
- **Excel連携**: 生成されるCSVはBOM付きUTF-8のため、文字化けなしでExcelで開けます。
- **レスポンシブ**: PC、タブレットのどちらからでも快適に操作可能。

## 🚀 クイックスタート

### 1. インストール
```bash
git clone <repository-url>
cd taskapp
pip install -r requirements.txt
```

### 2. 環境設定
`.env` ファイルを作成し、必要に応じて設定を変更してください。
```ini
SECRET_KEY=your_secret_key_here
# PostgreSQLを使用する場合のみ設定
# DATABASE_URL=postgresql://user:password@localhost:5432/taskdb
```

### 3. アプリケーションの起動
```bash
python app.py
```
起動後、ブラウザで [http://127.0.0.1:5003](http://127.0.0.1:5003) にアクセスしてください。

## 📂 プロジェクト構成
- `app.py`: メインアプリケーション・ルーティング
- `models.py`: データベースモデル（SQLAlchemy）
- `templates/`: HTMLテンプレート（Bootstrap 5採用）
- `docs/system_design.md`: 詳細なシステム設計仕様

## 🛠 動作確認のポイント
1. **マスタ登録**: 「マスタ管理」から部署や製品を追加してください。
2. **実績入力**: 社員番号欄に「E」と入力すると、候補がリスト表示されます。
3. **データ修正**: 一覧画面の「修正」ボタンから、数量や時間を即座に変更できます。
4. **集計出力**: 条件を絞り込んで「CSV出力」を行い、Excelでの見え方を確認してください。

## 📝 開発者向け
- 本システムは外部のグラフライブラリや重いフレームワークに依存せず、ブラウザ標準のJavaScript (Vanilla JS) で動作します。
- データベースの初期化は `app.py` 起動時に自動で行われるため、手動の `CREATE TABLE` は不要です。
