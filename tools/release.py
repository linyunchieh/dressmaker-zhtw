"""打包 payload 成 zip、建立 GitHub Release、更新 index.json（之後 git commit/push 由人確認後執行）。

usage: release.py <payload dir> <owner/repo>
"""
import hashlib, json, os, subprocess, sys, zipfile

PAYLOAD, REPO = sys.argv[1:3]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
man = json.load(open(os.path.join(PAYLOAD, 'manifest.json'), encoding='utf-8'))
ver, bid = man['version'], man['buildid']
name = f'dressmaker-zhtw-payload-{ver}.zip'
out = os.path.join(os.path.dirname(os.path.abspath(PAYLOAD)), name)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:   # lit.xz 已壓縮
    for f in sorted(os.listdir(PAYLOAD)):
        z.write(os.path.join(PAYLOAD, f), f)
data = open(out, 'rb').read()
h = hashlib.sha256(data).hexdigest()
print(name, len(data), 'bytes, sha256', h)
subprocess.run(['gh', 'release', 'create', f'v{ver}', out, '-R', REPO, '-t', f'補丁資料 {ver}（buildid {bid}）',
                '-n', f'線上安裝程式使用的補丁資料，適用 Steam buildid {bid}。玩家請下載 launcher release 的安裝程式。\n\n'
                      f'**SHA-256**\n`{name}`：`{h}`'],
               check=True)
ip = os.path.join(ROOT, 'index.json')
idx = json.load(open(ip, encoding='utf-8')) if os.path.exists(ip) else {'min_launcher': 1, 'versions': []}
idx['versions'] = [v for v in idx['versions'] if v['buildid'] != bid] + [{
    'version': ver, 'buildid': bid, 'size': len(data), 'sha256': h,
    'url': f'https://github.com/{REPO}/releases/download/v{ver}/{name}'}]
idx['latest'] = ver
json.dump(idx, open(ip, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('index.json updated; review and git commit/push')
