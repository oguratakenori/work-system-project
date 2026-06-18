from app import app, db
import json

with app.app_context():
    with app.test_client() as client:
        print("--- API Verification ---")
        
        # 1. Query 'S'
        resp_s = client.get('/api/employees?q=S')
        data_s = json.loads(resp_s.data.decode('utf-8'))
        print(f"Query 'S': Status {resp_s.status_code}, Count: {len(data_s)}")
        if len(data_s) > 0:
            print(f"Sample data for 'S': {data_s[0]}")
            
        # 2. Query 'S0'
        resp_s0 = client.get('/api/employees?q=S0')
        data_s0 = json.loads(resp_s0.data.decode('utf-8'))
        print(f"Query 'S0': Status {resp_s0.status_code}, Count: {len(data_s0)}")
        if len(data_s0) > 0:
            print(f"Sample data for 'S0': {data_s0[0]}")
        
        print("--- API Verification End ---")
