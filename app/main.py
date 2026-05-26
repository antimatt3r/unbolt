from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
import io
import os
import re
import time
import pathlib
import threading
from collections import defaultdict
from urllib.parse import quote
from app.password_manager import password_manager
from app.decrypter import get_decrypter, DecryptionError

app = FastAPI(title="Multi-Format Decryption Utility")

# Configuration via environment variables
MAX_FILE_SIZE = int(os.environ.get("UNBOLT_MAX_FILE_SIZE", 100 * 1024 * 1024)) # default 100MB
RATE_LIMIT_REQUESTS = int(os.environ.get("UNBOLT_RATE_LIMIT_REQUESTS", 60))    # requests
RATE_LIMIT_WINDOW = int(os.environ.get("UNBOLT_RATE_LIMIT_WINDOW", 60))        # seconds (1 minute)

# Thread-safe in-memory rate limiter
class IPWindowsLimiter:
    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self.history = defaultdict(list)
        self.lock = threading.Lock()

    def check_rate_limit(self, client_ip: str):
        now = time.time()
        with self.lock:
            # Keep only hits in the current window
            self.history[client_ip] = [t for t in self.history[client_ip] if now - t < self.window]
            if len(self.history[client_ip]) >= self.limit:
                raise HTTPException(
                    status_code=429, 
                    detail="Too many requests. Please try again later."
                )
            self.history[client_ip].append(now)

limiter = IPWindowsLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

def sanitize_filename(filename: str) -> str:
    # Extract basename only to prevent directory traversal
    name = pathlib.Path(filename).name
    # Strip carriage returns, newlines, and tabs
    name = re.sub(r'[\r\n\t]', '', name)
    # Remove double quotes and backslashes
    name = name.replace('"', '').replace('\\', '')
    # Cap length at 255 to prevent filesystem errors
    return name[:255]

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = pathlib.Path(__file__).parent / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/banner.png")
async def serve_banner():
    banner_path = pathlib.Path(__file__).parent / "banner.png"
    if banner_path.exists():
        return FileResponse(banner_path)
    raise HTTPException(status_code=404, detail="Banner not found")

@app.post("/decrypt")
async def decrypt_file(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(None),
    persist: bool = Form(True)
):
    # 1. Rate Limiting Check
    client_ip = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    limiter.check_rate_limit(client_ip)

    # 2. File Size Checks
    # Pre-check Content-Length header (avoids reading body if too large)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")
        except ValueError:
            pass

    extension = pathlib.Path(file.filename).suffix.lower()
    decrypter = get_decrypter(extension)
    
    if not decrypter:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {extension}")
    
    # Process files entirely in memory (with fallback check after reading)
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 100MB.")
    
    passwords_to_try = []
    if password:
        passwords_to_try.append(password)
    passwords_to_try.extend(password_manager.get_all_passwords())
    
    decrypted_bytes = None
    successful_password = None
    
    for pwd in passwords_to_try:
        try:
            result = decrypter(file_bytes, pwd)
            if result is not None:
                decrypted_bytes = result
                successful_password = pwd
                break
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except DecryptionError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception:
            continue
            
    if decrypted_bytes is None:
        raise HTTPException(status_code=422, detail="Failed to decrypt file with available passwords.")
        
    if password and successful_password == password and persist:
        password_manager.add_user_password(password)
        
    # 3. Filename Sanitization
    sanitized_name = sanitize_filename(file.filename)
    encoded_name = quote(sanitized_name)
    
    return StreamingResponse(
        io.BytesIO(decrypted_bytes),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="decrypted_{sanitized_name}"; filename*=UTF-8\'\'decrypted_{encoded_name}'
        }
    )
