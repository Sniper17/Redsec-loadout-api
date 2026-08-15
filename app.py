from flask import Flask, request
import json, os, re, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

app=Flask(__name__)
DATA=os.path.join(os.path.dirname(__file__),"data","weapons.json")
HEADERS={"User-Agent":"RedSecLoadoutAPI/1.0"}
TIMEOUT=(4,10)
ALIASES={"svd":"SVDM","svdm":"SVDM","kord":"KORD 6P67","kord6p67":"KORD 6P67","pw5":"PW5A3","pw5a3":"PW5A3","m4":"M4A1","m4a1":"M4A1","sgx":"SGX","sg553":"SG-553R","sg553r":"SG-553R","m16":"M16A4","m16a4":"M16A4","b36":"B36A4","b36a4":"B36A4","nvo":"NVO-228E","nvo228e":"NVO-228E","rpk":"RPK-74M","rpk74m":"RPK-74M","m2010":"M2010 ESR","m2010esr":"M2010 ESR","psr":"PSR","l115":"L115","kts":"KTS100 MK8","kts100":"KTS100 MK8","cz":"CZ3A1","cz3a1":"CZ3A1"}
SOURCES=[("BattlefieldMeta","https://battlefieldmeta.gg/pt/melhores-configuracoes/{slug}"),("WZStats","https://wzstats.gg/battlefield-6/loadouts/{slug}-loadout")]

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "").lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))
def slug(s): return re.sub(r"[^a-z0-9]+","-",norm(s)).strip("-")
def load():
    with open(DATA,encoding="utf-8") as f:return json.load(f)
def canonical(q):
    k=re.sub(r"[^a-z0-9]+","",norm(q))
    if k in ALIASES:return ALIASES[k]
    for name,w in load().get("weapons",{}).items():
        if k in [re.sub(r"[^a-z0-9]+","",norm(x)) for x in [name]+w.get("aliases",[])]: return name
    return q.strip()
def parse(html):
    soup=BeautifulSoup(html,"html.parser")
    lines=[" ".join(x.stripped_strings) for x in soup.find_all(["h1","h2","h3","h4","li","p","div","span"])]
    lines=[x for x in lines if x]
    labels={"barrel":"Cano","underbarrel":"Acoplamento","ammunition":"Munição","muzzle":"Boca","magazine":"Carregador","scope":"Mira","optic":"Mira","right accessory":"Acessório Direito","left accessory":"Acessório Esquerdo","ergonomics":"Ergonomia"}
    start=next((i for i,x in enumerate(lines) if norm(x) in ("recommended","recomendado")),None)
    end=next((i for i in range((start or 0)+1,len(lines)) if "lowest recoil" in norm(lines[i]) or "menor recuo" in norm(lines[i])),None)
    sec=lines[start:end] if start is not None else lines
    out=[]; seen=set()
    for i,line in enumerate(sec):
        slot=labels.get(norm(line))
        if slot and i and slot not in seen:
            value=sec[i-1].strip()
            if value and len(value)<80 and norm(value) not in ("recommended","recomendado"):
                out.append({"slot":slot,"name":value}); seen.add(slot)
    return out[:8]," ".join(lines)
def fetch(source,url,weapon):
    try:
        r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
        if r.status_code!=200:return None
        a,text=parse(r.text)
        if len(a)<3:return None
        return {"weapon":weapon,"attachments":a,"tier":"META" if re.search(r"\bMETA\b",text,re.I) else "","source":source,"source_url":url}
    except Exception:return None
def live(q):
    weapon=canonical(q); s=slug(weapon)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fs=[pool.submit(fetch,n,u.format(slug=s),weapon) for n,u in SOURCES]
        results=[x for f in as_completed(fs) if (x:=f.result())]
    if results:
        results.sort(key=lambda x:0 if x["source"]=="BattlefieldMeta" else 1)
        return results[0]
    return None
def fmt(x):
    p=[f"🔫 {x['weapon']}"]
    if x["tier"]:p.append("🔥 META")
    p += [f"{a['slot']}: {a['name']}" for a in x["attachments"]]
    return " • ".join(p)
@app.get("/")
def home(): return "🔥 REDSEC Loadout API online!"
@app.get("/classe")
def classe():
    q=request.args.get("arma","").strip()
    if not q:return "⚠️ Informe a arma. Exemplo: /classe?arma=svdm"
    x=live(q)
    return fmt(x) if x else f"⚠️ Não encontrei um loadout confiável para '{q}'."
@app.get("/status")
def status(): return {"online":True,"api_version":"1.0","game":"Battlefield REDSEC","sources":["BattlefieldMeta","WZStats"],"cached_weapons":len(load().get("weapons",{}))}
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
