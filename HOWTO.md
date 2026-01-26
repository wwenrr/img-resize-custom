# Cách dùng với Product IDs từ Console

## Bước 1: Extract Product IDs

Paste console output vào file hoặc pipe trực tiếp:

```bash
# Cách 1: Copy console output vào clipboard, paste vào terminal
cd /home/mk/Desktop/img-resize
python3 extract_ids.py
# Paste console output, nhấn Ctrl+D

# Cách 2: Từ file
python3 extract_ids.py < your_console_output.txt
```

**Output sẽ hiện:**
```
PRODUCT_IDS = [
    "8358417924254",
    "8358425460894",
    ...
]

MODE = "product_ids"
```

## Bước 2: Copy vào run.py

Mở `run.py`, tìm dòng (khoảng line 915):

```python
# Product IDs mode - paste extracted IDs here
PRODUCT_IDS = [
    # Example: "8358417924254",
]

# MODE: "barcodes" or "product_ids"
MODE = "barcodes"
```

**Paste list và đổi MODE:**

```python
PRODUCT_IDS = [
    "8358417924254",
    "8358425460894",
    "8363751178398",
    ...  # paste tất cả IDs
]

MODE = "product_ids"  # ← Đổi thành "product_ids"
```

## Bước 3: Chạy

```bash
cd /home/mk/Desktop/img-resize
source venv/bin/activate
python3 run.py
```

Chọn store (1=JWL, 2=JF), script sẽ chạy!

---

## Output:

```
[1/50] Processing Product ID: 8358417924254
[2/50] Processing Product ID: 8358425460894
[3/50] Processing Product ID: 8363751178398
...
```

Sạch sẽ, không có noise!

---

## Tips:

- File `product_ids.txt` chứa output
- Có thể edit trực tiếp list trong `run.py`
- Không duplicate IDs tự động
- Không cache - luôn xử lý lại
