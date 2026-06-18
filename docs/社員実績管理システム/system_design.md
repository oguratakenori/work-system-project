# システム設計書 - 作業実績管理システム

## 1. システム概要
本システムは、工場や製造現場における日々の作業実績（誰が、いつ、どの製品を、どの作業で、何個作ったか）を効率的に記録・管理・分析するためのWebアプリケーションです。
直感的なUIと詳細なレポート機能により、現場の生産性向上を支援します。

## 2. 使用技術
- **バックエンド**: Python 3.x / Flask
- **データベース**: PostgreSQL (推奨) / SQLite (フォールバック)
- **フロントエンド**: HTML5, CSS3, JavaScript (Vanilla JS)
- **フレームワーク/ライブラリ**:
    - Bootstrap 5 (UIフレームワーク)
    - Bootstrap Icons (アイコン)
    - Flask-SQLAlchemy (ORM)
    - Python-dotenv (環境変数管理)
- **その他**: CSV形式でのデータエクスポート機能（標準ライブラリ使用）

## 3. 画面一覧
1. **メインメニュー**: 全機能への入り口（カード型UI）
2. **マスタ管理メニュー**: 各種マスタ管理画面への遷移
    - 部署マスタ管理
    - 社員マスタ管理
    - 作業マスタ管理
    - 製品マスタ管理
3. **作業実績入力**: 実績データの登録フォーム
4. **実績一覧・修正**: 登録データの検索および編集（モーダルUI）
5. **集計・レポート**: 詳細なフィルタリングとCSVダウンロード

## 4. DB設計
### テーブル構成
- **departments (部署マスタ)**
    - `id` (SERIAL/PK)
    - `name` (VARCHAR)
- **employees (社員マスタ)**
    - `id` (SERIAL/PK)
    - `employee_no` (VARCHAR/Unique)
    - `name` (VARCHAR)
    - `department_id` (FK -> departments)
- **works (作業マスタ)**
    - `id` (SERIAL/PK)
    - `name` (VARCHAR)
- **products (製品マスタ)**
    - `id` (SERIAL/PK)
    - `product_no` (VARCHAR/Unique)
    - `name` (VARCHAR)
- **performance_records (実績データ)**
    - `id` (SERIAL/PK)
    - `employee_id` (FK -> employees)
    - `work_id` (FK -> works)
    - `product_id` (FK -> products)
    - `quantity` (INTEGER)
    - `start_time` (TIMESTAMP)
    - `end_time` (TIMESTAMP)

## 5. 機能一覧
- **マスタCRUD機能**: 各種マスターデータの登録・表示・更新・削除
- **実績登録機能**: バリデーション付きのデータ入力
- **検索機能**: 社員番号、部署、作業、日付範囲等による多角的な検索
- **データ修正機能**: 登録済みの実績データをモーダル画面で直接編集
- **CSVエクスポート**: 日本語Excel対応（BOM付きUTF-8）のレポート出力
- **DB自動初期化**: 初回起動時にテーブル作成および初期シードデータの投入

## 6. 現在の実装状況
- [x] 基本的なCRUD機能の実装完了
- [x] 業務システム向けのレスポンシブなUI/UXデザイン
- [x] SQLite/PostgreSQLのデュアルデータベース対応
- [x] 外部ライブラリ（Pandas等）に依存しない軽量なCSV出力の実装
- [x] 日本語環境に最適化されたUIおよびデータ処理

## 7. 今後の改善候補
- **認証・認可機能**: ログイン画面および管理者/一般ユーザーの権限分け
- **ダッシュボード**: グラフライブラリ（Chart.js等）を使用した生産性の視覚化
- **バーコード/QR対応**: 社員証や製品伝票の読み取りによる入力簡略化
- **一括登録機能**: CSVファイルからの実績データ一括インポート
- **履歴管理**: データの修正履歴（ログ）の保持機能
