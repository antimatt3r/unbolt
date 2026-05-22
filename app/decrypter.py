import io
import pikepdf
from typing import Callable, Dict, Optional

class DecryptionError(Exception):
    """Raised when decryption fails due to reasons other than incorrect password."""
    pass

DecrypterFunc = Callable[[bytes, str], Optional[bytes]]

# The handler registry
_registry: Dict[str, DecrypterFunc] = {}

def register_decrypter(extension: str):
    """Decorator to register a decryption handler for a specific file extension."""
    def decorator(func: DecrypterFunc):
        _registry[extension.lower()] = func
        return func
    return decorator

def get_decrypter(extension: str) -> Optional[DecrypterFunc]:
    """Retrieve the appropriate decryption handler for an extension."""
    return _registry.get(extension.lower())

@register_decrypter(".pdf")
def decrypt_pdf(file_bytes: bytes, password: str) -> Optional[bytes]:
    try:
        with pikepdf.open(io.BytesIO(file_bytes), password=password) as pdf:
            out_io = io.BytesIO()
            pdf.save(out_io)
            return out_io.getvalue()
    except pikepdf.PasswordError:
        return None
    except Exception as e:
        raise DecryptionError(f"PDF processing error: {str(e)}")

@register_decrypter(".zip")
def decrypt_zip(file_bytes: bytes, password: str) -> Optional[bytes]:
    # Placeholder for .zip file logic
    raise NotImplementedError("ZIP decryption is not yet implemented.")

@register_decrypter(".xlsx")
def decrypt_xlsx(file_bytes: bytes, password: str) -> Optional[bytes]:
    # Placeholder for .xlsx file logic
    raise NotImplementedError("XLSX decryption is not yet implemented.")
