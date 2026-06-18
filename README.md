# Work System Project

4つの業務管理システムを統合したプロジェクトです。

## システム一覧
1. **社員管理システム (employee-management)**: 社員、部署、役職の管理。
2. **経費管理システム (expense-management)**: 経費精算、勘定科目管理。
3. **製品管理システム (product-management)**: 製品情報の管理とCSV出力。
4. **作業実績管理システム (work-record-management)**: 日次の作業実績登録。

## セットアップ手順
1. Python 3.x のインストール
2. 依存パッケージのインストール: `pip install -r requirements.txt`
3. 環境変数の設定: `.env.example` を参考に `.env` を作成してください。
   ※ 開発時は `.env` がなくてもデフォルト値で動作しますが、本番利用時は必ず設定してください。

## 起動方法
各システムのディレクトリに移動して `python app.py` を実行してください。

## 注意事項
- データベースファイル（*.db）や環境設定（.env）は Git 管理対象外です。
- 各システムは独立した Flask アプリケーションとして動作します。
