import os,UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
def load(path,D):
    env=UnityPy.load(path)
    g=TypeTreeGenerator("6000.3.4f1")
    for n in sorted(os.listdir(D+"/Managed")):
        if n.endswith(".dll"):
            try: g.load_dll(open(D+"/Managed/"+n,"rb").read())
            except AssertionError: pass
    env.typetree_generator=g
    return env
