"""UnityFS bundle 解壓（純 Python，安裝程式與 build 共用）：回傳所有資料區塊解壓後串接的內容。"""
import struct


def lz4_block(src, size):
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        ln = tok >> 4
        if ln == 15:
            while True:
                b = src[i]
                i += 1
                ln += b
                if b != 255:
                    break
        dst += src[i:i + ln]
        i += ln
        if i >= n:
            break
        off = src[i] | src[i + 1] << 8
        i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = len(dst) - off
        if off >= ml:
            dst += dst[start:start + ml]
        else:                       # 重疊複製
            for k in range(ml):
                dst.append(dst[start + k])
    assert len(dst) == size, (len(dst), size)
    return bytes(dst)


def _decomp(data, kind, size):
    if kind == 0:
        return bytes(data)
    if kind in (2, 3):
        return lz4_block(data, size)
    raise ValueError('unsupported compression %d' % kind)


def data_stream(raw):
    assert raw[:8] == b'UnityFS\0', 'not a UnityFS bundle'
    i = 8
    ver = struct.unpack('>I', raw[i:i + 4])[0]
    i += 4
    for _ in range(2):              # unityVersion, unityRevision
        i = raw.index(b'\0', i) + 1
    _size, csz, usz, flags = struct.unpack('>qIII', raw[i:i + 20])
    i += 20
    if ver >= 7:
        i = (i + 15) & ~15
    if flags & 0x80:                # blocks info 在檔尾
        bi = raw[len(raw) - csz:]
    else:
        bi = raw[i:i + csz]
        i += csz
    info = _decomp(bi, flags & 0x3F, usz)
    count = struct.unpack('>i', info[16:20])[0]
    if flags & 0x200:
        i = (i + 15) & ~15
    out = bytearray()
    p = 20
    for _ in range(count):
        u, c, f = struct.unpack('>IIH', info[p:p + 10])
        p += 10
        out += _decomp(raw[i:i + c], f & 0x3F, u)
        i += c
    return bytes(out)
