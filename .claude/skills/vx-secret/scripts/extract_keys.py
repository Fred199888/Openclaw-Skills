#!/usr/bin/env python3
"""
Extract SQLCipher encryption keys from WeChat process memory on macOS.
Requires: sudo, WeChat ad-hoc re-signed (hardened runtime removed).
Output: /tmp/vx_secret_keys.json
"""
import ctypes
import ctypes.util
import hashlib
import hmac as hmac_mod
import json
import os
import re
import struct
import subprocess
import sys
import time

PAGE_SZ = 4096
KEY_SZ = 32
SALT_SZ = 16
KEYS_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keys.json")

libc = ctypes.CDLL(ctypes.util.find_library('c'))
libc.task_for_pid.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint32)]
libc.task_for_pid.restype = ctypes.c_int32
libc.mach_task_self.argtypes = []
libc.mach_task_self.restype = ctypes.c_uint32
libc.mach_vm_read.argtypes = [
    ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint32)
]
libc.mach_vm_read.restype = ctypes.c_int32
libc.mach_vm_deallocate.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64]
libc.mach_vm_deallocate.restype = ctypes.c_int32


def verify_enc_key(enc_key_bytes, db_page1):
    """Verify key using HMAC-SHA512 (SQLCipher 4)."""
    salt = db_page1[:SALT_SZ]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key_bytes, mac_salt, 2, dklen=KEY_SZ)
    hmac_data = db_page1[SALT_SZ: PAGE_SZ - 80 + 16]
    stored_hmac = db_page1[PAGE_SZ - 64: PAGE_SZ]
    hm = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
    hm.update(struct.pack("<I", 1))
    return hm.digest() == stored_hmac


def collect_dbs(base_dir):
    """Collect all encrypted .db files with page1 data."""
    dbs = []
    for root, _, files in os.walk(base_dir):
        for name in files:
            if not name.endswith('.db'):
                continue
            path = os.path.join(root, name)
            try:
                if os.path.getsize(path) < PAGE_SZ:
                    continue
                with open(path, 'rb') as f:
                    page1 = f.read(PAGE_SZ)
                if page1[:15] == b'SQLite format 3':
                    continue
                rel = os.path.relpath(path, base_dir)
                dbs.append((rel, path, page1[:SALT_SZ], page1))
            except Exception:
                pass
    return dbs


def read_mem(task, addr, size):
    data_ptr = ctypes.c_uint64()
    data_cnt = ctypes.c_uint32()
    ret = libc.mach_vm_read(task, addr, size, ctypes.byref(data_ptr), ctypes.byref(data_cnt))
    if ret != 0:
        return None
    buf = ctypes.string_at(data_ptr.value, data_cnt.value)
    libc.mach_vm_deallocate(libc.mach_task_self(), data_ptr.value, data_cnt.value)
    return buf


def get_regions(pid):
    regions = []
    output = subprocess.check_output(['vmmap', '-w', str(pid)], stderr=subprocess.DEVNULL, text=True)
    for line in output.split('\n'):
        m = re.match(r'\s*\S+\s+([\da-f]+)-([\da-f]+)\s+\[\s*(\S+)', line)
        if m:
            start, end = int(m.group(1), 16), int(m.group(2), 16)
            size = end - start
            if 0 < size < 500 * 1024 * 1024:
                regions.append((start, size))
    return regions


def main():
    # Find WeChat PID
    try:
        pid = int(subprocess.check_output(['pgrep', '-x', 'WeChat']).strip().split()[0])
    except Exception:
        print("ERROR: WeChat is not running")
        sys.exit(1)
    print(f"WeChat PID: {pid}")

    # Get task port
    task = ctypes.c_uint32()
    ret = libc.task_for_pid(libc.mach_task_self(), pid, ctypes.byref(task))
    if ret != 0:
        print(f"ERROR: task_for_pid failed ({ret}). Need sudo + WeChat ad-hoc re-signed.")
        sys.exit(1)
    print(f"Task port: {task.value}")

    # Check if DBs are open (WeChat logged in)
    try:
        lsof = subprocess.check_output(['lsof', '-p', str(pid)], text=True, stderr=subprocess.DEVNULL)
        if '.db' not in lsof:
            print("WARNING: No .db files open - WeChat may not be logged in yet")
    except Exception:
        pass

    # Collect DB files
    home = os.path.expanduser("~")
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd
        try:
            home = pwd.getpwnam(sudo_user).pw_dir
        except Exception:
            pass

    xwechat_dir = os.path.join(home, "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files")
    all_dbs = []
    if os.path.isdir(xwechat_dir):
        all_dbs = collect_dbs(xwechat_dir)
    print(f"Found {len(all_dbs)} encrypted DBs")

    if not all_dbs:
        print("ERROR: No encrypted databases found")
        sys.exit(1)

    verify_dbs = all_dbs[:10]
    hex_re = re.compile(rb"x'([0-9a-fA-F]{64,192})'")

    # Scan memory
    regions = get_regions(pid)
    total_size = sum(s for _, s in regions)
    print(f"{len(regions)} memory regions, {total_size/1024/1024:.0f}MB")
    print("Scanning...")

    t0 = time.time()
    found_keys = {}
    scanned = 0
    chunk_size = 4 * 1024 * 1024

    for reg_idx, (base, size) in enumerate(regions):
        offset = 0
        while offset < size:
            read_size = min(chunk_size, size - offset)
            data = read_mem(task.value, base + offset, read_size)
            if data is None:
                offset += read_size
                continue
            scanned += len(data)

            # Pattern 1: x'hex' strings
            for m in hex_re.finditer(data):
                hex_str = m.group(1).decode()
                enc_key = bytes.fromhex(hex_str[:64])
                for rel, path, salt, page1 in all_dbs:
                    if rel not in found_keys and verify_enc_key(enc_key, page1):
                        found_keys[rel] = hex_str[:64]
                        print(f"  [FOUND] {rel}: {hex_str[:64]}")

            # Pattern 2: Raw salt+key bytes
            for rel, path, salt, page1 in verify_dbs:
                if rel in found_keys:
                    continue
                idx = 0
                while True:
                    idx = data.find(salt, idx)
                    if idx < 0:
                        break
                    for candidate_start in [idx - KEY_SZ, idx + SALT_SZ]:
                        if 0 <= candidate_start <= len(data) - KEY_SZ:
                            candidate = data[candidate_start:candidate_start + KEY_SZ]
                            if verify_enc_key(candidate, page1):
                                found_keys[rel] = candidate.hex()
                                print(f"  [FOUND-RAW] {rel}: {candidate.hex()}")
                    idx += 1

            offset += read_size

        if (reg_idx + 1) % 20 == 0:
            pct = scanned / total_size * 100
            print(f"  [{pct:.0f}%] {scanned/1024/1024:.0f}MB, {len(found_keys)} keys")

    # Cross-verify all DBs
    if found_keys:
        print("\nCross-verifying...")
        all_found = dict(found_keys)
        for rel, path, salt, page1 in all_dbs:
            if rel in all_found:
                continue
            for known_rel, known_key_hex in found_keys.items():
                if verify_enc_key(bytes.fromhex(known_key_hex), page1):
                    all_found[rel] = known_key_hex
                    break
        found_keys = all_found

    elapsed = time.time() - t0
    print(f"\nDone: {scanned/1024/1024:.0f}MB in {elapsed:.1f}s, {len(found_keys)}/{len(all_dbs)} DBs matched")

    # Save results
    result = {}
    for rel, key_hex in found_keys.items():
        full_path = os.path.join(xwechat_dir, rel)
        result[rel] = {"enc_key": key_hex, "path": full_path}
    with open(KEYS_OUTPUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Keys saved to {KEYS_OUTPUT}")

    unique_keys = set(found_keys.values())
    print(f"\nUnique keys ({len(unique_keys)}):")
    for k in unique_keys:
        print(f"  {k}")


if __name__ == '__main__':
    main()
