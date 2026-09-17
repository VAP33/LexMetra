import httpx, json

pairs = [
    ('admin', 'password123'),
    ('inspector1', 'password123'),
    ('inspector', 'password123'),
    ('admin', 'admin'),
    ('admin', 'admin123'),
]

for user, pwd in pairs:
    body = f'username={user}&password={pwd}'
    r = httpx.post(
        'http://127.0.0.1:8000/auth/login',
        content=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=5
    )
    data = r.json()
    tok = data.get('access_token', '')
    role = data.get('role', '')
    detail = data.get('detail', '')
    print(f'{user}/{pwd}: status={r.status_code} token={bool(tok)} role={role} detail={detail}')
    if tok:
        print(f'  -> SUCCESS with token prefix: {tok[:20]}...')
        # Test extract-preview with a small dummy image
        import numpy as np, cv2, io
        img = np.ones((100, 100, 3), dtype=np.uint8) * 200
        ok, enc = cv2.imencode('.jpg', img)
        img_bytes = enc.tobytes()
        ep = httpx.post(
            'http://127.0.0.1:8000/extract-preview',
            headers={'Authorization': f'Bearer {tok}'},
            files={'file': ('test.jpg', img_bytes, 'image/jpeg')},
            timeout=60
        )
        print(f'  extract-preview: status={ep.status_code}')
        if ep.status_code == 200:
            epd = ep.json()
            print(f'  fields: {list(epd.get("raw_ocr_fields", {}).keys())}')
        else:
            print(f'  error: {ep.text[:200]}')
        break
