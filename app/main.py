from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
import io
import pathlib
from app.password_manager import password_manager
from app.decrypter import get_decrypter, DecryptionError

app = FastAPI(title="Multi-Format Decryption Utility")

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
    file: UploadFile = File(...),
    password: str = Form(None),
    persist: bool = Form(True)
):
    extension = pathlib.Path(file.filename).suffix.lower()
    decrypter = get_decrypter(extension)
    
    if not decrypter:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {extension}")
    
    # Process files entirely in memory
    file_bytes = await file.read()
    
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
        
    return StreamingResponse(
        io.BytesIO(decrypted_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="decrypted_{file.filename}"'}
    )
