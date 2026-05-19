"""
Elliott Wave Analyzer - Basado en metodología de Enrique Santos
"""
import os, json, requests, pandas as pd, ta
from datetime import datetime, timezone
from typing import Optional

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "TU_API_KEY_AQUI")

ASSETS = [
    ("BTCUSDT","crypto"),("ETHUSDT","crypto"),
    ("AAPL","stock"),("NVDA","stock"),("MSFT","stock"),
    ("AMZN","stock"),("GOOGL","stock"),("META","stock"),("TSLA","stock"),
]
RESULTS_FILE = "results.json"
HISTORY_FILE = "history.json"

def fetch_crypto_ohlcv(symbol, interval="1h", limit=200):
    coin_map={"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","SOLUSDT":"solana","BNBUSDT":"binancecoin"}
    coin_id=coin_map.get(symbol,symbol.lower().replace("usdt",""))
    r=requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",params={"vs_currency":"usd","days":"7"},timeout=10)
    r.raise_for_status()
    df=pd.DataFrame(r.json(),columns=["timestamp","open","high","low","close"])
    df["timestamp"]=pd.to_datetime(df["timestamp"],unit="ms")
    df["volume"]=0.0
    return df.set_index("timestamp")

def fetch_stock_ohlcv(symbol,period="60d",interval="1h"):
    import yfinance as yf
    df=yf.Ticker(symbol).history(period=period,interval=interval)
    df.index=pd.to_datetime(df.index)
    df.columns=[c.lower() for c in df.columns]
    return df[["open","high","low","close","volume"]]

def get_current_price(symbol,asset_type):
    try:
        if asset_type=="crypto":
            coin_map={"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","SOLUSDT":"solana","BNBUSDT":"binancecoin"}
            coin_id=coin_map.get(symbol,symbol.lower().replace("usdt",""))
            r=requests.get("https://api.coingecko.com/api/v3/simple/price",params={"ids":coin_id,"vs_currencies":"usd"},timeout=10)
            return r.json()[coin_id]["usd"]
        else:
            import yfinance as yf
            return float(yf.Ticker(symbol).history(period="1d",interval="1m")["Close"].iloc[-1])
    except: return None

def calculate_indicators(df):
    df=df.copy()
    df["rsi"]=ta.momentum.RSIIndicator(df["close"],window=14).rsi()
    macd=ta.trend.MACD(df["close"],window_slow=26,window_fast=12,window_sign=9)
    df["macd"]=macd.macd(); df["macd_signal"]=macd.macd_signal(); df["macd_hist"]=macd.macd_diff()
    adx=ta.trend.ADXIndicator(df["high"],df["low"],df["close"],window=14)
    df["adx"]=adx.adx(); df["di_pos"]=adx.adx_pos(); df["di_neg"]=adx.adx_neg()
    w=min(100,len(df)); df["swing_high"]=df["high"].rolling(w).max(); df["swing_low"]=df["low"].rolling(w).min()
    return df

def build_analysis_prompt(symbol,df):
    last=df.iloc[-1]; prev20=df.iloc[-20:]
    price_data=[f"  {i+1}. {ts.strftime('%m/%d %H:%M')} | O:{row['open']:.4f} H:{row['high']:.4f} L:{row['low']:.4f} C:{row['close']:.4f}"
                for i,(ts,row) in enumerate(df.iloc[-50:].iterrows())]
    ch1=((last["close"]-df.iloc[-2]["close"])/df.iloc[-2]["close"]*100) if len(df)>=2 else 0
    ch24=((last["close"]-df.iloc[-25]["close"])/df.iloc[-25]["close"]*100) if len(df)>=25 else 0
    return f"""Eres experto en Ondas de Elliott según metodología de Enrique Santos.

## ACTIVO: {symbol}
- Precio: {last['close']:.4f} | 1h: {ch1:+.2f}% | 24h: {ch24:+.2f}%
- Swing High: {last['swing_high']:.4f} | Swing Low: {last['swing_low']:.4f}
- RSI: {last['rsi']:.1f} | MACD: {last['macd']:.6f} | ADX: {last['adx']:.1f} DI+: {last['di_pos']:.1f} DI-: {last['di_neg']:.1f}

## ÚLTIMAS 50 VELAS:
{chr(10).join(price_data)}

## INDICADORES 20 VELAS:
{prev20[['rsi','macd','macd_signal','adx','di_pos','di_neg']].round(2).to_string()}

Responde SOLO este JSON:
{{"simbolo":"{symbol}","precio_actual":{last['close']:.4f},"timestamp":"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
"onda_grado_mayor":{{"estructura":"...","onda_actual":"...","descripcion":"...","fibonacci_nivel":"..."}},"onda_grado_menor":{{"estructura":"...","onda_actual":"...","descripcion":"...","fibonacci_nivel":"..."}},
"señal":{{"tipo":"COMPRA|VENTA|ESPERAR|SIN_SEÑAL","fuerza":"FUERTE|MODERADA|DÉBIL","descripcion":"..."}},"niveles":{{"entrada":null,"stop_loss":null,"objetivo_1":null,"objetivo_2":null,"objetivo_3":null}},
"indicadores":{{"rsi_interpretacion":"...","macd_interpretacion":"...","adx_interpretacion":"...","confluencia":"..."}},"ratio_riesgo_beneficio":null,"resumen":"...","confianza":"ALTA|MEDIA|BAJA","razon_confianza":"..."}}

REGLAS: niveles solo si COMPRA/VENTA, señal FUERTE solo con confluencia de 3 indicadores + Elliott."""

def call_claude(prompt):
    r=requests.post("https://api.anthropic.com/v1/messages",
        headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
        json={"model":"claude-sonnet-4-5","max_tokens":1500,"messages":[{"role":"user","content":prompt}]},timeout=30)
    r.raise_for_status()
    text=r.json()["content"][0]["text"].strip().replace("```json","").replace("```","").strip()
    return json.loads(text)

def format_telegram_message(a):
    s=a.get("señal",{}); tipo=s.get("tipo","SIN_SEÑAL"); fuerza=s.get("fuerza","")
    es={"COMPRA":"🟢","VENTA":"🔴","ESPERAR":"🟡","SIN_SEÑAL":"⚪"}.get(tipo,"⚪")
    ec={"ALTA":"🔥","MEDIA":"⚡","BAJA":"❄️"}.get(a.get("confianza",""),"")
    nv=a.get("niveles",{}); gm=a.get("onda_grado_mayor",{}); gn=a.get("onda_grado_menor",{}); ind=a.get("indicadores",{})
    msg=f"""╔══════════════════════════╗\n║ 📊 {a.get('simbolo','?'):^22} ║\n╚══════════════════════════╝\n💰 Precio: *{a.get('precio_actual','?')}*\n🕐 {a.get('timestamp','')}\n\n{es} *SEÑAL: {tipo} {fuerza}* {es}\n_{s.get('descripcion','')}_\n\n━━━━ 🌊 ONDAS ━━━━\n📐 *Grado Mayor:* {gm.get('onda_actual','')} — {gm.get('estructura','')}\n_{gm.get('descripcion','')}_\nFib: {gm.get('fibonacci_nivel','')}\n\n🔍 *Grado Menor:* {gn.get('onda_actual','')} — {gn.get('estructura','')}\n_{gn.get('descripcion','')}_\nFib: {gn.get('fibonacci_nivel','')}"""
    if tipo in ("COMPRA","VENTA") and nv.get("entrada"):
        rr=a.get("ratio_riesgo_beneficio"); rrs=f"{rr:.1f}x" if rr else "N/A"
        msg+=f"\n\n━━━━ 💹 NIVELES ━━━━\n🎯 Entrada: *{nv.get('entrada','—')}*\n🛑 Stop: *{nv.get('stop_loss','—')}*\n🏁 O1: *{nv.get('objetivo_1','—')}* | O2: *{nv.get('objetivo_2','—')}* | O3: *{nv.get('objetivo_3','—')}*\n⚖️ R/B: *{rrs}*"
    msg+=f"\n\n━━━━ 📈 INDICADORES ━━━━\n• RSI: {ind.get('rsi_interpretacion','')}\n• MACD: {ind.get('macd_interpretacion','')}\n• ADX: {ind.get('adx_interpretacion','')}\n\n{a.get('resumen','')}\n\n{ec} Confianza: *{a.get('confianza','')}*"
    return msg

def send_telegram(message):
    r=requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id":TELEGRAM_CHAT_ID,"text":message,"parse_mode":"Markdown"},timeout=10)
    return r.ok

def load_history():
    try:
        with open(HISTORY_FILE) as f: return json.load(f)
    except: return {"signals":[],"stats":{}}

def save_history(history):
    with open(HISTORY_FILE,"w") as f: json.dump(history,f,indent=2,ensure_ascii=False)

def calculate_signal_return(s):
    entry=s.get("entrada"); sl=s.get("stop_loss"); o1=s.get("objetivo_1"); o2=s.get("objetivo_2"); o3=s.get("objetivo_3")
    tipo=s.get("tipo"); sl_a=s.get("sl_actual",sl)
    if not all([entry,sl,o1]): return 0.0
    if tipo=="COMPRA":
        if s.get("hit_o3") and o2 and o3: return ((o1-entry)/entry*.5+(o2-entry)/entry*.25+(o3-entry)/entry*.25)*100
        elif s.get("hit_o2") and o2: return ((o1-entry)/entry*.5+(o2-entry)/entry*.25+(o1-entry)/entry*.25)*100
        elif s.get("hit_o1"): return ((o1-entry)/entry*.5)*100
        elif s.get("hit_sl"): return ((sl_a-entry)/entry)*100
    elif tipo=="VENTA":
        if s.get("hit_o3") and o2 and o3: return ((entry-o1)/entry*.5+(entry-o2)/entry*.25+(entry-o3)/entry*.25)*100
        elif s.get("hit_o2") and o2: return ((entry-o1)/entry*.5+(entry-o2)/entry*.25+(entry-o1)/entry*.25)*100
        elif s.get("hit_o1"): return ((entry-o1)/entry*.5)*100
        elif s.get("hit_sl"): return ((entry-sl_a)/entry)*100
    return 0.0

def update_signal_tracking(signal,price):
    if signal.get("status")!="ACTIVA": return signal
    s=signal.copy(); entry=s.get("entrada"); o1=s.get("objetivo_1"); o2=s.get("objetivo_2"); o3=s.get("objetivo_3"); tipo=s.get("tipo")
    if not all([entry,o1,price]): return s
    now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if tipo=="COMPRA":
        if not s.get("hit_o1") and price>=o1: s.update({"hit_o1":True,"hit_o1_time":now,"hit_o1_price":price,"sl_actual":entry})
        if s.get("hit_o1") and not s.get("hit_o2") and o2 and price>=o2: s.update({"hit_o2":True,"hit_o2_time":now,"hit_o2_price":price,"sl_actual":o1})
        if s.get("hit_o2") and not s.get("hit_o3") and o3 and price>=o3: s.update({"hit_o3":True,"hit_o3_time":now,"hit_o3_price":price,"status":"CERRADA","resultado":calculate_signal_return(s)})
        if not s.get("hit_sl") and price<=s.get("sl_actual",s.get("stop_loss")): s.update({"hit_sl":True,"hit_sl_time":now,"hit_sl_price":price,"status":"CERRADA","resultado":calculate_signal_return(s)})
    elif tipo=="VENTA":
        if not s.get("hit_o1") and price<=o1: s.update({"hit_o1":True,"hit_o1_time":now,"hit_o1_price":price,"sl_actual":entry})
        if s.get("hit_o1") and not s.get("hit_o2") and o2 and price<=o2: s.update({"hit_o2":True,"hit_o2_time":now,"hit_o2_price":price,"sl_actual":o1})
        if s.get("hit_o2") and not s.get("hit_o3") and o3 and price<=o3: s.update({"hit_o3":True,"hit_o3_time":now,"hit_o3_price":price,"status":"CERRADA","resultado":calculate_signal_return(s)})
        if not s.get("hit_sl") and price>=s.get("sl_actual",s.get("stop_loss")): s.update({"hit_sl":True,"hit_sl_time":now,"hit_sl_price":price,"status":"CERRADA","resultado":calculate_signal_return(s)})
    return s

def calculate_stats(signals):
    closed=[s for s in signals if s.get("status")=="CERRADA"]
    activas=len([s for s in signals if s.get("status")=="ACTIVA"])
    if not closed: return {"activas":activas}
    total=len(closed); res=[s.get("resultado",0) for s in closed]; win=[r for r in res if r>0]
    by_asset={}
    for s in closed:
        sym=s.get("simbolo","?")
        if sym not in by_asset: by_asset[sym]={"total":0,"ganadoras":0,"retorno_total":0.0}
        by_asset[sym]["total"]+=1
        if s.get("resultado",0)>0: by_asset[sym]["ganadoras"]+=1
        by_asset[sym]["retorno_total"]+=s.get("resultado",0)
    for sym in by_asset:
        t=by_asset[sym]["total"]
        by_asset[sym]["tasa_exito"]=round(by_asset[sym]["ganadoras"]/t*100,1)
        by_asset[sym]["retorno_promedio"]=round(by_asset[sym]["retorno_total"]/t,2)
    return {"total_señales":total,"ganadoras":len(win),"perdedoras":total-len(win),
            "tasa_exito":round(len(win)/total*100,1),"retorno_promedio":round(sum(res)/total,2),
            "retorno_total":round(sum(res),2),"mejor_retorno":round(max(res),2),"peor_retorno":round(min(res),2),
            "by_asset":by_asset,"activas":activas}

def register_new_signal(analysis,history):
    s=analysis.get("señal",{}); tipo=s.get("tipo"); nv=analysis.get("niveles",{})
    if tipo not in ("COMPRA","VENTA") or not nv.get("entrada"): return history
    if any(x.get("simbolo")==analysis.get("simbolo") and x.get("status")=="ACTIVA" for x in history["signals"]): return history
    now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sig={"id":f"{analysis.get('simbolo')}_{now.replace(' ','_').replace(':','')}","simbolo":analysis.get("simbolo"),
         "tipo":tipo,"fuerza":s.get("fuerza"),"confianza":analysis.get("confianza"),"timestamp":analysis.get("timestamp"),
         "asset_type":"crypto" if "USDT" in analysis.get("simbolo","") else "stock",
         "entrada":nv.get("entrada"),"stop_loss":nv.get("stop_loss"),"sl_actual":nv.get("stop_loss"),
         "objetivo_1":nv.get("objetivo_1"),"objetivo_2":nv.get("objetivo_2"),"objetivo_3":nv.get("objetivo_3"),
         "rr":analysis.get("ratio_riesgo_beneficio"),"onda_mayor":analysis.get("onda_grado_mayor",{}).get("onda_actual"),
         "onda_menor":analysis.get("onda_grado_menor",{}).get("onda_actual"),"resumen":analysis.get("resumen"),
         "status":"ACTIVA","hit_o1":False,"hit_o2":False,"hit_o3":False,"hit_sl":False,"resultado":None}
    history["signals"].append(sig)
    print(f"   📝 Nueva señal: {sig['id']}")
    return history

def save_results(results):
    with open(RESULTS_FILE,"w") as f:
        json.dump({"last_update":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),"analyses":results},f,indent=2,ensure_ascii=False)

def analyze_asset(symbol,asset_type):
    print(f"\n{'─'*50}\n⏳ Analizando {symbol}...")
    try:
        df=fetch_crypto_ohlcv(symbol) if asset_type=="crypto" else fetch_stock_ohlcv(symbol)
        print(f"   ✅ {len(df)} velas")
        df=calculate_indicators(df).dropna()
        analysis=call_claude(build_analysis_prompt(symbol,df))
        tipo=analysis.get("señal",{}).get("tipo","?"); conf=analysis.get("confianza","?")
        print(f"   ✅ {tipo} ({conf})")
        if tipo in ("COMPRA","VENTA") or conf=="ALTA":
            sent=send_telegram(format_telegram_message(analysis))
            print(f"   {'✅' if sent else '❌'} Telegram")
        return analysis
    except Exception as e:
        print(f"   ❌ Error: {e}"); return None

def main():
    print(f"\n{'═'*50}\n🌊 ELLIOTT WAVE ANALYZER\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n{'═'*50}")
    history=load_history()
    activas=[s for s in history["signals"] if s.get("status")=="ACTIVA"]
    print(f"\n📊 Actualizando {len(activas)} señales activas...")
    updated=[]
    for sig in history["signals"]:
        if sig.get("status")=="ACTIVA":
            price=get_current_price(sig["simbolo"],sig.get("asset_type","stock"))
            if price:
                sig=update_signal_tracking(sig,price)
                if sig.get("status")=="CERRADA": print(f"   🏁 {sig['simbolo']}: {sig.get('resultado',0):+.2f}%")
        updated.append(sig)
    history["signals"]=updated
    results=[]
    for symbol,asset_type in ASSETS:
        a=analyze_asset(symbol,asset_type)
        if a: results.append(a); history=register_new_signal(a,history)
    history["stats"]=calculate_stats(history["signals"])
    history["last_update"]=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    save_results(results); save_history(history)
    print(f"\n✅ {len(results)}/{len(ASSETS)} procesados.")
    st=history.get("stats",{})
    if st.get("total_señales"): print(f"📈 {st['total_señales']} señales | {st['tasa_exito']}% éxito | {st['retorno_total']:+.2f}% retorno")

if __name__=="__main__": main()
