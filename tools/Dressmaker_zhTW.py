"""Dressmaker 繁體中文化補丁 線上安裝程式（簡中 -> 繁中台灣用語、思源 TC 字型、語言選單顯示「繁體中文」、繁中圖片）

安裝程式本身固定不變；執行時依遊戲的 Steam buildid 從 GitHub 下載對應的補丁資料（只含差分，不含遊戲原檔）。
測試／離線：--payload <dir> 直接用本機 payload；--cli install|restore <game dir> 不開視窗。
"""
import os, sys, json, hashlib, shutil, lzma, re, subprocess, threading, tempfile, urllib.request, zipfile, winreg
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unityfs

APP_ID = '4019220'
LAUNCHER_VERSION = 1
REPO = 'linyunchieh/dressmaker-zhtw'
INDEX_URL = f'https://raw.githubusercontent.com/{REPO}/main/index.json'
PAGE_URL = f'https://github.com/{REPO}'
TITLE = 'Dressmaker 繁體中文化補丁'
BACKUP = '_zhTW_backup'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def find_game():
    roots = []
    for hive, key, val in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                           (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
        try:
            with winreg.OpenKey(hive, key) as k:
                roots.append(winreg.QueryValueEx(k, val)[0])
        except OSError:
            pass
    libs = []
    for r in roots:
        libs.append(r)
        vdf = os.path.join(r, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf):
            txt = open(vdf, encoding='utf-8', errors='ignore').read()
            libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', txt)]
    for lib in libs:
        p = os.path.join(lib, 'steamapps', 'common', 'Dressmaker')
        if os.path.exists(os.path.join(p, 'Dressmaker.exe')):
            return os.path.normpath(p)
    return ''


def game_buildid(game):
    """遊戲資料夾 <lib>/steamapps/common/Dressmaker -> <lib>/steamapps/appmanifest_4019220.acf 的 buildid。"""
    acf = os.path.join(game, '..', '..', f'appmanifest_{APP_ID}.acf')
    try:
        m = re.search(r'"buildid"\s+"(\d+)"', open(acf, encoding='utf-8', errors='ignore').read())
        return m.group(1) if m else None
    except OSError:
        return None


def game_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dressmaker.exe'], capture_output=True, text=True,
                             creationflags=0x08000000).stdout
        return 'Dressmaker.exe' in out
    except Exception:
        return False


# ---------------------------------------------------------------- 下載補丁資料
def http_get(url, log=None, label=''):
    req = urllib.request.Request(url, headers={'User-Agent': 'Dressmaker-zhTW-launcher'})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get('Content-Length') or 0)
        buf = bytearray()
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            buf += b
            if log and total:
                log('%s %d%%（%.1f / %.1f MB）' % (label, len(buf) * 100 // total, len(buf) / 1e6, total / 1e6))
    return bytes(buf)


def fetch_payload(game, log):
    """依 buildid 從 GitHub 下載並解壓補丁資料，回傳 payload 目錄。"""
    log('取得補丁版本清單…')
    try:
        idx = json.loads(http_get(INDEX_URL))
    except Exception as ex:
        raise RuntimeError('無法連線到 GitHub 取得補丁資料：\n' + str(ex))
    if idx.get('min_launcher', 1) > LAUNCHER_VERSION:
        raise RuntimeError('這個安裝程式版本太舊，請到以下網址下載新版安裝程式：\n' + PAGE_URL)
    bid = game_buildid(game)
    vers = idx['versions']
    if bid:
        hit = [v for v in vers if v['buildid'] == bid]
        if not hit:
            raise RuntimeError(f'補丁尚未支援目前的遊戲版本（Steam buildid {bid}）。\n'
                               f'遊戲更新後通常需要幾天適配，請到以下網址查看：\n{PAGE_URL}')
        v = hit[0]
    else:   # 找不到 Steam 資訊：用最新版，檔案版本由雜湊檢查把關
        v = next(v for v in vers if v['version'] == idx['latest'])
    data = http_get(v['url'], log, f'下載補丁 {v["version"]}')
    if hashlib.sha256(data).hexdigest() != v['sha256']:
        raise RuntimeError('下載的補丁資料損毀（雜湊不符），請再試一次。')
    d = tempfile.mkdtemp(prefix='dressmaker_zhtw_')
    import io
    zipfile.ZipFile(io.BytesIO(data)).extractall(d)
    return d


# ---------------------------------------------------------------- 安裝／還原
def apply_delta(payload, game, src, dst, entry, log):
    meta = json.load(open(os.path.join(payload, entry['delta'] + '.json')))
    lit = lzma.decompress(open(os.path.join(payload, entry['delta'] + '.lit.xz'), 'rb').read())
    aux = b''
    if 'aux' in entry:
        log('讀取遊戲原始資源…')
        parts = []
        for a in entry['aux']:
            p = os.path.join(game, a['path'])
            bk = os.path.join(game, BACKUP, a['path'])
            if os.path.exists(bk) and sha256(bk) == a['sha256']:   # 補丁也會改到的檔案：原檔在備份裡
                p = bk
            if sha256(p) != a['sha256']:
                raise RuntimeError('檔案版本不符：' + os.path.basename(a['path']) +
                                   '\n請先在 Steam「驗證遊戲檔案完整性」後再試。')
            parts.append(unityfs.data_stream(open(p, 'rb').read()))
        aux = b''.join(parts)
    li = 0
    with open(src, 'rb') as fi, open(dst, 'wb') as fo:
        for op in meta['ops']:
            if op[0] == 'C':
                fi.seek(op[1])
                n = op[2]
                while n:
                    b = fi.read(min(n, 8 << 20))
                    fo.write(b)
                    n -= len(b)
            elif op[0] == 'S':
                fo.write(aux[op[1]:op[1] + op[2]])
            else:
                fo.write(lit[li:li + op[1]])
                li += op[1]


def install(game, log, payload):
    if game_running():
        raise RuntimeError('請先關閉遊戲再安裝。')
    man = json.load(open(os.path.join(payload, 'manifest.json'), encoding='utf-8'))
    ver = man['version']
    plan = []
    log('檢查遊戲檔案版本…')
    for e in man['files']:
        p = os.path.join(game, e['path'])
        if not os.path.exists(p):
            raise RuntimeError('找不到檔案：' + e['path'] + '\n請確認選的是 Dressmaker 遊戲資料夾。')
        h = sha256(p)
        if h == e['new_sha256']:
            continue
        bk = os.path.join(game, BACKUP, e['path'])
        if h == e['old_sha256']:
            plan.append((e, True))
        elif os.path.exists(bk) and sha256(bk) == e['old_sha256']:
            plan.append((e, False))   # 已裝舊版補丁：原檔在備份裡
        else:
            raise RuntimeError('檔案版本不符：' + os.path.basename(e['path']) +
                               f'\n這個補丁（{ver}）適用 Steam buildid {man["buildid"]} 版遊戲。'
                               '\n（若之前裝過舊版補丁但備份遺失，請先在 Steam「驗證遊戲檔案完整性」後再試）')
    if not plan:
        return f'已經是繁體中文化 {ver} 版本，不需要重複安裝。'
    for e, is_orig in plan:
        p = os.path.join(game, e['path'])
        bk = os.path.join(game, BACKUP, e['path'])
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        if is_orig and not (os.path.exists(bk) and sha256(bk) == e['old_sha256']):
            log('備份 ' + os.path.basename(p) + '…')
            shutil.copy2(p, bk)
    for e, _ in plan:
        p = os.path.join(game, e['path'])
        tmp = p + '.zhtw_tmp'
        log('寫入 ' + os.path.basename(p) + '…')
        apply_delta(payload, game, os.path.join(game, BACKUP, e['path']), tmp, e, log)
        log('驗證 ' + os.path.basename(p) + '…')
        if sha256(tmp) != e['new_sha256']:
            os.remove(tmp)
            raise RuntimeError(os.path.basename(p) + ' 寫入後驗證失敗，已中止。')
        os.replace(tmp, p)
    for lic in ('OFL_SourceHanSans.txt', 'OFL_SourceHanSerif.txt'):
        shutil.copyfile(os.path.join(payload, lic), os.path.join(game, BACKUP, lic))
    return (f'繁體中文化 {ver} 安裝完成！\n\n進遊戲後在「選項 → 語言」選「繁體中文」。\n'
            '原始檔案已備份在遊戲資料夾的 _zhTW_backup。')


def restore(game, log, payload):
    if game_running():
        raise RuntimeError('請先關閉遊戲再還原。')
    man = json.load(open(os.path.join(payload, 'manifest.json'), encoding='utf-8'))
    done = 0
    for e in man['files']:
        p = os.path.join(game, e['path'])
        bk = os.path.join(game, BACKUP, e['path'])
        if os.path.exists(p) and sha256(p) == e['old_sha256']:
            continue
        if not os.path.exists(bk) or sha256(bk) != e['old_sha256']:
            raise RuntimeError('找不到 ' + os.path.basename(p) + ' 的有效備份。\n請改用 Steam「驗證遊戲檔案完整性」還原。')
        log('還原 ' + os.path.basename(p) + '…')
        shutil.copy2(bk, p)
        done += 1
    return '已還原為原版。' if done else '目前已經是原版檔案。'


def run_action(fn, game, log, local_payload):
    payload = local_payload or fetch_payload(game, log)
    try:
        return fn(game, log, payload)
    finally:
        if not local_payload:
            shutil.rmtree(payload, ignore_errors=True)


class App:
    def __init__(self, root, local_payload):
        self.root = root
        self.local_payload = local_payload
        root.title(TITLE)
        root.resizable(False, False)
        f = ttk.Frame(root, padding=16)
        f.grid()
        ttk.Label(f, text=TITLE, font=('Microsoft JhengHei UI', 14, 'bold')).grid(columnspan=3, sticky='w')
        ttk.Label(f, text='將官方簡體中文轉為繁體中文（台灣用語），並改用思源 TC 字型與繁中圖片。\n'
                          '會自動從 GitHub 下載符合目前遊戲版本的補丁資料（約 27 MB）。',
                  font=('Microsoft JhengHei UI', 10)).grid(columnspan=3, sticky='w', pady=(4, 12))
        ttk.Label(f, text='遊戲資料夾：').grid(row=2, column=0, sticky='w')
        self.path = tk.StringVar(value=find_game())
        ttk.Entry(f, textvariable=self.path, width=58).grid(row=2, column=1, padx=4)
        ttk.Button(f, text='瀏覽…', command=self.browse).grid(row=2, column=2)
        bf = ttk.Frame(f)
        bf.grid(row=3, columnspan=3, pady=(14, 6))
        self.b1 = ttk.Button(bf, text='安裝繁體中文', command=lambda: self.run(install))
        self.b2 = ttk.Button(bf, text='還原原版', command=lambda: self.run(restore))
        self.b1.grid(row=0, column=0, padx=6, ipadx=10, ipady=4)
        self.b2.grid(row=0, column=1, padx=6, ipadx=10, ipady=4)
        self.status = tk.StringVar(value='就緒' if self.path.get() else '找不到遊戲，請按「瀏覽…」選擇 Dressmaker 資料夾')
        ttk.Label(f, textvariable=self.status, foreground='#555').grid(row=4, columnspan=3, sticky='w')

    def browse(self):
        d = filedialog.askdirectory(title='選擇 Dressmaker 遊戲資料夾（含 Dressmaker.exe）')
        if d:
            self.path.set(os.path.normpath(d))

    def run(self, fn):
        game = self.path.get().strip()
        if not os.path.exists(os.path.join(game, 'Dressmaker.exe')):
            messagebox.showerror(TITLE, '這個資料夾裡沒有 Dressmaker.exe，請重新選擇。')
            return
        self.b1.state(['disabled'])
        self.b2.state(['disabled'])

        def log(s):
            self.root.after(0, self.status.set, s)

        def work():
            try:
                msg = run_action(fn, game, log, self.local_payload)
                self.root.after(0, lambda: (self.status.set('完成'), messagebox.showinfo(TITLE, msg)))
            except Exception as ex:
                err = str(ex)
                self.root.after(0, lambda: (self.status.set('失敗'), messagebox.showerror(TITLE, err)))
            finally:
                self.root.after(0, lambda: (self.b1.state(['!disabled']), self.b2.state(['!disabled'])))

        threading.Thread(target=work, daemon=True).start()


if __name__ == '__main__':
    args = sys.argv[1:]
    local = None
    if '--payload' in args:
        i = args.index('--payload')
        local = args[i + 1]
        del args[i:i + 2]
    if args and args[0] == '--cli':   # 測試用：--cli install|restore <game dir>
        _, act, g = args
        try:
            msg, code = run_action({'install': install, 'restore': restore}[act], g, lambda s: None, local), 0
        except Exception as ex:
            msg, code = 'ERROR: ' + str(ex), 1
        with open(os.path.join(g, BACKUP + '_cli.log'), 'w', encoding='utf-8') as fh:
            fh.write(msg)
        sys.exit(code)
    root = tk.Tk()
    App(root, local)
    root.mainloop()
