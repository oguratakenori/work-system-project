-- Seed Departments
INSERT INTO departments (name) VALUES ('製造1課'), ('製造2課'), ('品質管理課'), ('物流課');

-- Seed Employees
INSERT INTO employees (employee_no, name, department_id) VALUES 
('E001', '山田 太郎', 1),
('E002', '佐藤 花子', 1),
('E003', '鈴木 一郎', 2),
('E004', '高橋 健二', 3);

-- Seed Works
INSERT INTO works (name) VALUES ('組立'), ('加工'), ('検査'), ('梱包');

-- Seed Products
INSERT INTO products (product_no, name) VALUES 
('P001', '製品A'),
('P002', '製品B'),
('P003', '製品C');

-- Seed Performance Records (Optional, but good for testing)
INSERT INTO performance_records (employee_id, work_id, product_id, quantity, start_time, end_time) VALUES 
(1, 1, 1, 100, '2026-06-08 09:00:00', '2026-06-08 12:00:00'),
(2, 2, 2, 50, '2026-06-08 13:00:00', '2026-06-08 17:00:00');
