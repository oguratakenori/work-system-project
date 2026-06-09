-- Drop tables if they exist
DROP TABLE IF EXISTS performance_records;
DROP TABLE IF EXISTS works;
DROP TABLE IF EXISTS departments;

-- Departments
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    department_code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL
);

-- Works
CREATE TABLE works (
    id SERIAL PRIMARY KEY,
    work_code VARCHAR(20) UNIQUE,
    name VARCHAR(100) NOT NULL,
    department_code VARCHAR(20)
);

-- Performance Records
CREATE TABLE performance_records (
    id SERIAL PRIMARY KEY,
    work_date DATE NOT NULL,
    employee_code VARCHAR(20) NOT NULL,
    department_code VARCHAR(20),
    work_code VARCHAR(20) NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    work_hours FLOAT NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
