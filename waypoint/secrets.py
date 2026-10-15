"""Local API keys use Windows user-bound DPAPI; never content records or backups."""
import base64
import ctypes
import json
import os
import sys
import threading
from pathlib import Path


def _crypt(data, decrypt=False):
    if sys.platform != 'win32':
        raise ValueError('本机加密密钥保存仅支持 Windows；其它环境请配置服务端环境变量')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy_buffer = ctypes.create_string_buffer(b'waypoint-api-keys-v1')
    entropy = Blob(len(b'waypoint-api-keys-v1'), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(out)):
        raise ValueError('本机密钥加密或解密失败，请重新配置密钥')
    try: return ctypes.string_at(out.data, out.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]; free.restype = ctypes.c_void_p
        free(ctypes.cast(out.data, ctypes.c_void_p))


class KeyVault:
    def __init__(self, root):
        self.path = Path(root) / 'private' / 'api_keys.json'
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists(): return {}
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict): raise ValueError()
            return value
        except (OSError, ValueError): raise ValueError('本机密钥文件无法读取，请检查本地私有配置') from None

    def preserve_encrypted(self):
        """Keep a reversible encrypted copy only in the private local directory."""
        from uuid import uuid4
        with self.lock:
            if self.path.exists():
                backup=self.path.parent/('api_keys_before_rebind_'+uuid4().hex+'.json')
                backup.write_bytes(self.path.read_bytes())

    def has(self, id, binding):
        with self.lock:
            item = self._read().get(id, {})
            return bool(item.get('binding') == binding and item.get('ciphertext'))

    def get(self, id, binding):
        with self.lock:
            item = self._read().get(id, {})
            if item.get('binding') != binding or not item.get('ciphertext'): return None
            try: return _crypt(base64.b64decode(item['ciphertext'], validate=True), decrypt=True).decode('utf-8')
            except (KeyError, UnicodeError, ValueError): raise ValueError('本机保存的密钥无法解密，请重新配置') from None

    def set(self, id, key, binding):
        if not isinstance(key, str) or not 8 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError('密钥格式不正确，请直接粘贴密钥，不添加空格或换行')
        encrypted = base64.b64encode(_crypt(key.encode())).decode('ascii')
        with self.lock:
            values = self._read(); values[id] = {'binding': binding, 'ciphertext': encrypted}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            with temporary.open('w', encoding='utf-8') as f:
                json.dump(values, f); f.flush(); os.fsync(f.fileno())
            temporary.replace(self.path)
