# Auto Git - Tự động commit & push

## 🎯 Chức năng

Script tự động:
- 🔍 Check thay đổi
- ➕ `git add .`
- 💾 `git commit -m "auto: update [timestamp]"`
- 🚀 `git push origin main`

**Mỗi 60 giây** tự động lặp lại!

---

## ▶️ Cách dùng

### 1. Chạy trực tiếp (Terminal hiện tại)

```bash
cd /home/mk/Desktop/img-resize
python3 auto_git.py
```

**Dừng:** Nhấn `Ctrl+C`

### 2. Chạy background (Không block terminal)

```bash
cd /home/mk/Desktop/img-resize
nohup python3 auto_git.py > auto_git.log 2>&1 &
echo $! > auto_git.pid
```

**Xem log:**
```bash
tail -f auto_git.log
```

**Dừng:**
```bash
kill $(cat auto_git.pid)
rm auto_git.pid
```

### 3. Chạy trong tmux (Khuyên dùng)

```bash
tmux new -s auto-git
cd /home/mk/Desktop/img-resize
python3 auto_git.py

# Detach: Ctrl+B, D
# Attach lại: tmux attach -t auto-git
# Kill: tmux kill-session -t auto-git
```

---

## 📊 Output mẫu

```
============================================================
🤖 Auto Git - Starting...
============================================================
📁 Working directory: /home/mk/Desktop/img-resize
⏱️  Interval: 60 seconds
🛑 Press Ctrl+C to stop
============================================================

============================================================
⏰ 2026-01-26 10:30:00
============================================================
📝 Changes detected:
 M run.py
 M index.html

[1/3] Adding files...
✓ Git add successful

[2/3] Committing...
✓ Committed: auto: update 2026-01-26 10:30:00

[3/3] Pushing to remote...
✓ Pushed successfully

⏸️  Waiting 60 seconds...
```

---

## ⚙️ Tùy chỉnh

### Thay đổi interval (không phải 60s)

Edit file `auto_git.py`, dòng 91:
```python
interval = 120  # 120 seconds = 2 minutes
```

### Thay đổi commit message

Edit file `auto_git.py`, dòng 48:
```python
commit_msg = f"auto: update {timestamp}"
# Đổi thành:
commit_msg = f"chore: auto save {timestamp}"
```

---

## ⚠️ Lưu ý

- ✅ Script tự động skip nếu không có thay đổi
- ✅ An toàn với `.gitignore` (`.env` không bao giờ được commit)
- ⚠️ Không dùng cho production code (dùng manual commit)
- ⚠️ Git history sẽ nhiều commits (mỗi 60s một commit)

---

## 🛑 Dừng script

**Terminal hiện tại:** `Ctrl+C`

**Background process:**
```bash
ps aux | grep auto_git.py
kill <PID>
```

**Tmux:**
```bash
tmux kill-session -t auto-git
```
