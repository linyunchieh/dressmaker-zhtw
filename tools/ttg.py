import os, re, UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


def unity_version(D):
    """從 globalgamemanagers 檔頭讀出 Unity 版本（遊戲更新可能升級引擎，不寫死）。"""
    head = open(os.path.join(D, 'globalgamemanagers'), 'rb').read(256)
    return re.search(rb'\d{4}\.\d+\.\d+[abfp]\d+', head).group().decode()


def load(path, D):
    env = UnityPy.load(path)
    g = TypeTreeGenerator(unity_version(D))
    for n in sorted(os.listdir(D + "/Managed")):
        if n.endswith(".dll"):
            try: g.load_dll(open(D + "/Managed/" + n, "rb").read())
            except AssertionError: pass
    env.typetree_generator = g
    return env
