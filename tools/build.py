"""Build the Dressmaker zh-TW patch payload (delta-only; contains no original game files).

usage: build.py <orig game dir> <prev payload dir> <TC font source resources.assets> <out payload dir>
                --version X.Y.Z --buildid N

<orig game dir> 必須是新版遊戲的「未修改」檔案（Dressmaker_Data/...，含 Managed/ 與 globalgamemanagers.assets）。
每個檔案：原檔與上一版 manifest 的 old_sha256 相同 -> 沿用上一版成品；不同 -> 從新版原檔重做：
- 字串表：translations/strings.json（{表: {m_Id: {sc_sha, tc}}}；sc_sha＝簡中原文 UTF-8 的 SHA-256 前 16 碼，
  repo 不存原文）。原文雜湊對不上或缺條目時，會寫出 <out>/../untranslated.json（含原文與新的 sc_sha）並中止；
  把 sc_sha 與譯文補進 strings.json 再跑一次。
- catalog：三個 bundle 的 CRC 歸零（位置用新版原檔大小重新找）
- Assembly-CSharp.dll：LanguageSelectorPopup.NativeName 的 brtrue.s 7 -> pop; nop（用 IL 樣式重新定位）
- resources.assets：思源 SC Font 換成 TC 字型資料（依名稱找物件）
- sharedassets2.assets：素描本需求條標籤 overflowMode 1 -> 0（依 m_text／字級找物件）
- locales、圖片 bundle：目前沒有重做程式，原檔變了就中止（屆時再補）
輸出全部是 delta：['C', 原檔位移, 長度] 從原檔照搬，['L', 長度] 從 .lit.xz 取。
"""
import argparse, hashlib, json, lzma, os, re, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ttg, unityfs

ap = argparse.ArgumentParser()
ap.add_argument('orig')
ap.add_argument('prev')
ap.add_argument('fontsrc')
ap.add_argument('out')
ap.add_argument('--version', required=True)
ap.add_argument('--buildid', required=True)
A = ap.parse_args()
NEW, PREV, OUT = A.orig, A.prev, A.out
DATA = os.path.join(NEW, 'Dressmaker_Data')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRINGS_JSON = os.path.join(REPO, 'translations', 'strings.json')
os.makedirs(OUT, exist_ok=True)

AA = 'Dressmaker_Data/StreamingAssets/aa/StandaloneWindows64/'
STR_BUNDLE = AA + 'localization-string-tables-chinese(simplified)(zh-hans)_assets_all.bundle'
LOC_BUNDLE = AA + 'localization-locales_assets_all.bundle'
IMG_BUNDLE = AA + 'localization-assets-chinese(simplified)(zh-hans)_assets_all.bundle'
CATALOG = 'Dressmaker_Data/StreamingAssets/aa/catalog.bin'
DLL = 'Dressmaker_Data/Managed/Assembly-CSharp.dll'
RES = 'Dressmaker_Data/resources.assets'
SA2 = 'Dressmaker_Data/sharedassets2.assets'
SHARED_BUNDLE = AA + 'localization-assets-shared_assets_all.bundle'
FONTS = ['SourceHanSerifSC-Regular', 'SourceHanSansSC-Regular']
# 圖片 bundle 以不壓縮存檔；其中的原版內容（舊 .resS 裡的簡中貼圖、照搬自 shared bundle 的英文 Logo）
# 安裝時從玩家電腦上這些 bundle 解壓後串接的資料取得（S op），payload 不含原版內容
AUX = {IMG_BUNDLE: [IMG_BUNDLE, SHARED_BUNDLE]}
# 安裝順序沿用 2.x：字串表最先
ORDER = [STR_BUNDLE, LOC_BUNDLE, IMG_BUNDLE, CATALOG, DLL, RES, SA2]
DELTA_NAME = {STR_BUNDLE: 'strings', LOC_BUNDLE: 'locales', IMG_BUNDLE: 'images', CATALOG: 'catalog',
              DLL: 'dll', RES: 'resources', SA2: 'sharedassets2'}


def sha(p_or_b):
    if isinstance(p_or_b, (bytes, bytearray)):
        return hashlib.sha256(p_or_b).hexdigest()
    h = hashlib.sha256()
    with open(p_or_b, 'rb') as f:
        for b in iter(lambda: f.read(1 << 23), b''):
            h.update(b)
    return h.hexdigest()


def sha16(s):
    """簡中原文的指紋：strings.json 只存這個，用來偵測遊戲更新後原文有沒有改。"""
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def load(path):
    return ttg.load(path, DATA)


def orig(rel):
    return os.path.join(NEW, rel)


PREVMAN = json.load(open(os.path.join(PREV, 'manifest.json'), encoding='utf-8'))
PREVE = {e['path']: e for e in PREVMAN['files']}


# ---------------------------------------------------------------- delta helpers
def apply_ops(src, ops, lit, dst, aux=None):
    li = 0
    with open(src, 'rb') as fi, open(dst, 'wb') as fo:
        for op in ops:
            if op[0] == 'C':
                fi.seek(op[1])
                n = op[2]
                while n:
                    d = fi.read(min(n, 8 << 20))
                    fo.write(d)
                    n -= len(d)
            elif op[0] == 'S':
                fo.write(aux[op[1]:op[1] + op[2]])
            else:
                fo.write(lit[li:li + op[1]])
                li += op[1]
    assert li == len(lit)


def binary_delta(src, new, aux=None, B=32):
    """區塊雜湊比對：src（與 aux）以 B byte 對齊建索引，掃描 new，命中就前後延伸成 C（aux 為 S），其餘為 L。"""
    idx = {}
    for kind, buf in (('C', src), ('S', aux or b'')):
        for i in range(0, len(buf) - B + 1, B):
            idx.setdefault(buf[i:i + B], (kind, i))
    ops, lit = [], bytearray()
    i = lstart = 0

    def emit_lit(end):
        if end > lstart:
            ops.append(['L', end - lstart])
            lit.extend(new[lstart:end])

    n = len(new)
    while i + B <= n:
        hit = idx.get(new[i:i + B])
        if hit is None:
            i += 1
            continue
        kind, s = hit
        buf = src if kind == 'C' else aux
        a, b = i, s                      # 向後延伸（吃掉待輸出的 literal）
        while a > lstart and b > 0 and new[a - 1] == buf[b - 1]:
            a -= 1
            b -= 1
        e, f = i + B, s + B              # 向前延伸
        while e < n and f < len(buf) and new[e] == buf[f]:
            e += 1
            f += 1
        emit_lit(a)
        if ops and ops[-1][0] == kind and ops[-1][1] + ops[-1][2] == b:
            ops[-1][2] += e - a
        else:
            ops.append([kind, b, e - a])
        i = lstart = e
    emit_lit(n)
    return ops, bytes(lit)


def object_delta(src_path, new_data, changed_ids):
    """new_data 是 UnityPy 重存的整檔；未改動的物件從原檔照搬（C），其餘為 literal（L）。"""
    import UnityPy
    sf = list(UnityPy.load(src_path).files.values())[0]
    nf = list(UnityPy.load(new_data).files.values())[0]
    src_pos = {pid: (o.byte_start, o.byte_size) for pid, o in sf.objects.items()}
    spans = sorted((o.byte_start, o.byte_size, pid) for pid, o in nf.objects.items() if pid not in changed_ids)
    ops, lit, pos = [], bytearray(), 0
    for start, size, pid in spans:
        s0, s1 = src_pos[pid]
        assert s1 == size, pid
        if start > pos:
            ops.append(['L', start - pos])
            lit += new_data[pos:start]
        if ops and ops[-1][0] == 'C' and ops[-1][1] + ops[-1][2] == s0:
            ops[-1][2] += size
        else:
            ops.append(['C', s0, size])
        pos = start + size
    if pos < len(new_data):
        ops.append(['L', len(new_data) - pos])
        lit += new_data[pos:]
    return ops, bytes(lit)


def write_delta(rel, ops, lit, new_sha, aux_rel=None):
    name = DELTA_NAME[rel]
    json.dump({'ops': ops}, open(os.path.join(OUT, name + '.json'), 'w'), separators=(',', ':'))
    open(os.path.join(OUT, name + '.lit.xz'), 'wb').write(lzma.compress(lit, preset=9 | lzma.PRESET_EXTREME))
    chk = os.path.join(OUT, '_check')
    apply_ops(orig(rel), ops, lit, chk, aux_rel and aux_data(aux_rel))
    ok = sha(chk) == new_sha
    os.remove(chk)
    assert ok, name + ' delta does not reproduce output'
    cnt = {k: sum(op[2] for op in ops if op[0] == k) for k in 'CS'}
    print('  %-14s delta: %d ops, copy %d, aux %d, literal %d bytes' % (name, len(ops), cnt['C'], cnt['S'], len(lit)))
    e = {'path': rel, 'delta': name, 'old_sha256': sha(orig(rel)), 'new_sha256': new_sha}
    if cnt['S']:
        e['aux'] = [{'path': r, 'sha256': sha(orig(r))} for r in aux_rel]
    return e


def aux_data(rels):
    """aux 來源：遊戲 bundle 解壓後的資料依序串接（安裝時在玩家電腦上解壓）。"""
    return b''.join(unityfs.data_stream(open(orig(r), 'rb').read()) for r in rels)


def delta_from_bytes(rel, new_data, aux_rel=None):
    ops, lit = binary_delta(open(orig(rel), 'rb').read(), new_data, aux_rel and aux_data(aux_rel))
    return write_delta(rel, ops, lit, sha(new_data), aux_rel)


# ---------------------------------------------------------------- 字串表
def build_strings():
    tr = json.load(open(STRINGS_JSON, encoding='utf-8'))
    env = load(orig(STR_BUNDLE))
    missing, n = [], 0
    for o in env.objects:
        if o.type.name != 'MonoBehaviour':
            continue
        d = o.read_typetree()
        if 'm_TableData' not in d:
            continue
        t = tr.get(d['m_Name'], {})
        for e in d['m_TableData']:
            x = t.get(str(e['m_Id']))
            h = sha16(e['m_Localized'])
            if x is None or x['sc_sha'] != h:
                missing.append({'table': d['m_Name'], 'id': str(e['m_Id']), 'sc': e['m_Localized'],
                                'sc_sha': h, 'old_tc': x and x['tc']})
                continue
            e['m_Localized'] = x['tc']
            n += 1
        o.save_typetree(d)
    if missing:
        p = os.path.join(os.path.dirname(os.path.abspath(OUT)), 'untranslated.json')
        json.dump(missing, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        sys.exit('%d 條字串需要翻譯／更新，清單在 %s；補進 translations/strings.json 後再跑' % (len(missing), p))
    data = env.file.save(packer='original')
    assert not any('哥特' in x['tc'] for t in tr.values() for x in t.values())
    print('  strings: %d entries' % n)
    return delta_from_bytes(STR_BUNDLE, data)


# ---------------------------------------------------------------- catalog CRC
def build_catalog():
    b = bytearray(open(orig(CATALOG), 'rb').read())
    for rel in (LOC_BUNDLE, STR_BUNDLE, IMG_BUNDLE):
        pat = struct.pack('<I', os.path.getsize(orig(rel))) + bytes.fromhex('66070000a7070000')
        i = b.find(pat)
        assert i > 0 and b.find(pat, i + 1) < 0, 'catalog record not unique: ' + rel
        b[i - 4:i] = b'\0\0\0\0'
    return delta_from_bytes(CATALOG, bytes(b))


# ---------------------------------------------------------------- Assembly-CSharp.dll
def build_dll():
    b = bytearray(open(orig(DLL), 'rb').read())
    # NativeName: ldarg.0; callvirt get_Identifier; stloc.1; ldloca.s 1; call get_CultureInfo; stloc.0; ldloc.0; brtrue.s 7
    pat = re.compile(rb'\x02\x6f...\x0a\x0b\x12\x01\x28...\x0a\x0a\x06\x2d\x07\x02\x6f...\x0a\x2a\x06\x6f...\x0a\x2a', re.S)
    ms = [m.start() for m in pat.finditer(b)]
    assert len(ms) == 1, ms
    off = ms[0] + 16
    assert b[off:off + 2] == b'\x2d\x07'
    b[off:off + 2] = b'\x26\x00'   # pop; nop -> 永遠回傳 locale.LocaleName
    print('  dll: NativeName patched at', off)
    return delta_from_bytes(DLL, bytes(b))


# ---------------------------------------------------------------- resources.assets（思源 TC 字型）
def build_resources():
    src = list(load(A.fontsrc).files.values())[0]
    tcfonts = {o.peek_name(): o for o in src.objects.values() if o.type.name == 'Font'}
    env = load(orig(RES))
    f = list(env.files.values())[0]
    changed = set()
    for name in FONTS:
        hits = [o for o in f.objects.values() if o.type.name == 'Font' and o.peek_name() == name]
        assert len(hits) == 1, (name, hits)
        o = hits[0]
        d = o.read_typetree()
        s = tcfonts[name].read_typetree()
        assert s['m_FontNames'][0].endswith(' TC'), s['m_FontNames']
        d['m_FontData'] = s['m_FontData']
        d['m_FontNames'] = s['m_FontNames']
        o.save_typetree(d)
        changed.add(o.path_id)
        print('  font', name, 'pathID', o.path_id, '->', s['m_FontNames'][0])
    data = f.save()
    nf = list(load(data).files.values())[0]
    for name in FONTS:
        o = next(o for o in nf.objects.values() if o.type.name == 'Font' and o.peek_name() == name)
        assert o.read_typetree()['m_FontData'] == tcfonts[name].read_typetree()['m_FontData']
    ops, lit = object_delta(orig(RES), data, changed)
    return write_delta(RES, ops, lit, sha(data))


# ---------------------------------------------------------------- sharedassets2（素描本需求條標籤）
def build_sharedassets2():
    src = orig(SA2)
    f = list(load(src).files.values())[0]
    hits = []
    for o in f.objects.values():
        if o.type.name != 'MonoBehaviour':
            continue
        try:
            t = o.read_typetree()
        except Exception:
            continue
        if t.get('m_text') == 'Quality' and t.get('m_fontSize') == 25.0 and t.get('m_overflowMode') == 1:
            hits.append((o, t))
    assert len(hits) == 1, [o.path_id for o, _ in hits]   # 2.x 時是 pathID 2129
    o, t = hits[0]
    t['m_overflowMode'] = 0
    old = bytes(o.get_raw_data())
    o.save_typetree(t)
    new = bytes(o.data)
    assert len(old) == len(new)
    ref = bytearray(open(src, 'rb').read())
    assert ref[o.byte_start:o.byte_start + len(old)] == old
    ref[o.byte_start:o.byte_start + len(new)] = new
    print('  sharedassets2: label pathID', o.path_id, 'overflowMode 1 -> 0')
    return delta_from_bytes(SA2, bytes(ref))


BUILDERS = {STR_BUNDLE: build_strings, CATALOG: build_catalog, DLL: build_dll,
            RES: build_resources, SA2: build_sharedassets2}


def reuse(rel):
    """原檔沒變：沿用上一版成品（delta 直接複製；舊格式 blob 轉成 delta）。"""
    e = PREVE[rel]
    if 'delta' in e:
        for ext in ('.json', '.lit.xz'):
            shutil.copyfile(os.path.join(PREV, e['delta'] + ext), os.path.join(OUT, DELTA_NAME[rel] + ext))
        print('  %-14s reused delta from previous payload' % DELTA_NAME[rel])
        return dict(e, delta=DELTA_NAME[rel])
    data = open(os.path.join(PREV, e['blob']), 'rb').read()
    if rel in AUX:   # 存成不壓縮，原版內容才會以原始 bytes 出現、能從 aux 照搬
        data = load(data).file.save(packer='none')
        print('  resaved uncompressed:', len(data), 'bytes')
        return delta_from_bytes(rel, data, AUX[rel])
    r = delta_from_bytes(rel, data)
    assert r['new_sha256'] == e['new_sha256']
    return r


def main():
    files = []
    for rel in ORDER:
        print(DELTA_NAME[rel] + ':')
        # 字串表一律重做：strings.json 改了但遊戲沒更新時，也要套進新譯文
        if rel != STR_BUNDLE and rel in PREVE and sha(orig(rel)) == PREVE[rel]['old_sha256']:
            files.append(reuse(rel))
        elif rel in BUILDERS:
            files.append(BUILDERS[rel]())
        else:
            sys.exit(rel + ' 的原檔被遊戲更新改動，且沒有重做程式；需要手動處理')
    for lic in ('OFL_SourceHanSans.txt', 'OFL_SourceHanSerif.txt'):
        shutil.copyfile(os.path.join(PREV, lic), os.path.join(OUT, lic))
    json.dump({'version': A.version, 'buildid': A.buildid, 'files': files},
              open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('manifest written:', len(files), 'files')


main()
