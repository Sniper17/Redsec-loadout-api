from flask import Flask, request
import json, os, re, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

app=Flask(__name__)
DATA=os.path.join(os.path.dirname(__file__),"data","weapons.json")
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; RedSecLoadoutAPI/2.0)"}
TIMEOUT=(5,15)

ALIASES={
"svd":"SVDM","svdm":"SVDM","kord":"KORD 6P67","kord6p67":"KORD 6P67",
"pw5":"PW5A3","pw5a3":"PW5A3","m4":"M4A1","m4a1":"M4A1","sgx":"SGX",
"sg553":"SG-553R","sg553r":"SG-553R","m16":"M16A4","m16a4":"M16A4",
"b36":"B36A4","b36a4":"B36A4","nvo":"NVO-228E","nvo228e":"NVO-228E",
"rpk":"RPK-74M","rpk74m":"RPK-74M","m2010":"M2010 ESR","m2010esr":"M2010 ESR",
"psr":"PSR","l115":"L115","kts":"KTS100 MK8","kts100":"KTS100 MK8",
"cz":"CZ3A1","cz3a1":"CZ3A1","pp19":"PP-19","drsiar":"DRS-IAR",
"qbz":"QBZ-192","qbz192":"QBZ-192"
}
SOURCES=[
("BattlefieldMeta","https://battlefieldmeta.gg/pt/melhores-configuracoes/{slug}"),
("Battlefinity","https://battlefinity.gg/pt/weapon/BF6/{slug}"),
("Battlefield6.gg","https://www.battlefield6.gg/weapon/{slug}/")
]
SLOT_MAP={
"barrel":"Cano","underbarrel":"Acoplamento","under barrel":"Acoplamento",
"acoplamento inferior":"Acoplamento","ammunition":"Munição","munição":"Munição",
"muzzle":"Boca","boca":"Boca","magazine":"Carregador","carregador":"Carregador",
"scope":"Mira","optic":"Mira","mira":"Mira","right accessory":"Acessório",
"top accessory":"Acessório","left accessory":"Acessório","ergonomics":"Ergonomia",
"ergonomia":"Ergonomia"
}

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "").lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))
def slug(s): return re.sub(r"[^a-z0-9]+","-",norm(s)).strip("-")
def load():
    with open(DATA,encoding="utf-8") as f:return json.load(f)
def canonical(q):
    k=compact(q)
    if k in ALIASES:return ALIASES[k]
    for name,w in load().get("weapons",{}).items():
        if k==compact(name) or k in [compact(x) for x in w.get("aliases",[])]: return name
    return q.strip()
def tokens(html):
    soup=BeautifulSoup(html,"html.parser")
    return [" ".join(str(x).split()).strip() for x in soup.stripped_strings if str(x).strip() and len(str(x).strip())<=120]
def noise(t):
    n=norm(t)
    if re.fullmatch(r"[\d\s/+-]+",t): return True
    return n in {"level","nivel","nível","premium","recommended","recomendado","lowest recoil","menor recuo","fastest ads","hip fire","100/100","95/100","90/100"} or re.match(r"^(level|nível)\s*\d+",n)
def extract(ts):
    start=next((i+1 for i,t in enumerate(ts) if norm(t) in {"recommended","recomendado"}),None)
    if start is None:return []
    end=next((i for i in range(start,len(ts)) if norm(ts[i]) in {"lowest recoil","menor recuo","fastest ads","hip fire"}),len(ts))
    sec=ts[start:end]; out=[]; seen=set()
    for i,t in enumerate(sec):
        slot=SLOT_MAP.get(norm(t))
        if slot and slot not in seen:
            j=i-1
            while j>=0 and noise(sec[j]):j-=1
            if j>=0 and not SLOT_MAP.get(norm(sec[j])):
                out.append({"slot":slot,"name":sec[j]});seen.add(slot)
    return out[:8]
def fetch(src,url,weapon):
    try:
        r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
        if r.status_code!=200:return None
        a=extract(tokens(r.text))
        return {"weapon":weapon,"attachments":a,"source":src,"source_url":url} if len(a)>=4 else None
    except Exception:return None
def live(q):
    w=canonical(q);s=slug(w)
    with ThreadPoolExecutor(max_workers=3) as p:
        fs=[p.submit(fetch,n,u.format(slug=s),w) for n,u in SOURCES]
        rs=[x for f in as_completed(fs) if (x:=f.result())]
    order={"BattlefieldMeta":0,"Battlefinity":1,"Battlefield6.gg":2}
    rs.sort(key=lambda x:order.get(x["source"],99))
    return rs[0] if rs else None
def fmt(x):
    return " • ".join([f"🔫 {x['weapon']}"]+[f"{a['slot']}: {a['name']}" for a in x["attachments"]]+[f"📚 {x['source']}"])
@app.get("/")
def home():return "🔥 REDSEC Loadout API v2 online!"
@app.get("/status")
def status():return {"online":True,"api_version":"2.0","game":"Battlefield REDSEC","sources":[x[0] for x in SOURCES],"cached_weapons":len(load().get("weapons",{}))}
@app.get("/classe")
def classe():
    q=request.args.get("arma","").strip()
    if not q:return "⚠️ Informe a arma. Exemplo: /classe?arma=svdm"
    x=live(q)
    return fmt(x) if x else f"⚠️ Não encontrei um loadout confiável para '{q}'."
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
