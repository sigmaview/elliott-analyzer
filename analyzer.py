"""
Elliott Wave Analyzer - Basado en metodología de Enrique Santos
Analiza activos cada hora y envía señales a Telegram
"""

import os
import json
import requests
import pandas as pd
import ta
from datetime import datetime, timezone
from typing import Optional

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "TU_API_KEY_AQUI")

ASSETS = [
    ("BTCUSDT",  "crypto"),
    ("ETHUSDT",  "crypto"),
    ("AAPL",     "stock"),
    ("NVDA",     "stock"),
    ("MSFT",     "stock"),
    ("AMZN",     "stock"),
    ("GOOGL",    "stock"),
    ("META",     "stock"),
    ("TSLA",     "stock"),
]

RESULTS_FILE = "results.json"
# ──────────────────────────────────────────────────────────────────────────────


def fetch_crypto_ohlcv(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    # Convertir símbolo de Binance a CoinGecko
    coin_map = {
        "BTCUSDT": "bitcoin",
        "ETHUSDT": "ethereum",
        "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin"
    }
    coin_id = coin_map.get(symbol, symbol.lower().replace("usdt",""))
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": "7"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data, columns=["timestamp","open","high","low","close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["volume"] = 0.0
    return df.set_index("timestamp")


def fetch_stock_ohlcv(symbol: str, period: str = "60d", interval: str = "1h") -> pd.DataFrame:
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    df.index = pd.to_datetime(df.index)
    df.columns = [c.lower() for c in df.columns]
    return df[["open","high","low","close","volume"]]


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"]         = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd              = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()
    adx               = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx"]         = adx.adx()
    df["di_pos"]      = adx.adx_pos()
    df["di_neg"]      = adx.adx_neg()
    window            = min(100, len(df))
    df["swing_high"]  = df["high"].rolling(window).max()
    df["swing_low"]   = df["low"].rolling(window).min()
    return df


def build_analysis_prompt(symbol: str, df: pd.DataFrame) -> str:
    last   = df.iloc[-1]
    prev20 = df.iloc[-20:]

    price_data = []
    for i, (ts, row) in enumerate(df.iloc[-50:].iterrows()):
        price_data.append(
            f"  {i+1}. {ts.strftime('%m/%d %H:%M')} | "
            f"O:{row['open']:.4f} H:{row['high']:.4f} L:{row['low']:.4f} C:{row['close']:.4f} | "
            f"Vol:{row['volume']:.0f}"
        )
    price_str = "\n".join(price_data)

    change_1h  = ((last["close"] - df.iloc[-2]["close"]) / df.iloc[-2]["close"] * 100) if len(df) >= 2 else 0
    change_24h = ((last["close"] - df.iloc[-25]["close"]) / df.iloc[-25]["close"] * 100) if len(df) >= 25 else 0

    prompt = f"""Eres un experto en análisis de Ondas de Elliott siguiendo la metodología de Enrique Santos (monografías: Pautas de Impulso, Pautas Correctivas, Pautas Terminales).

## ACTIVO: {symbol}
- Precio actual: {last['close']:.4f}
- Cambio 1h: {change_1h:+.2f}%
- Cambio 24h: {change_24h:+.2f}%
- Máximo swing (100 velas): {last['swing_high']:.4f}
- Mínimo swing (100 velas): {last['swing_low']:.4f}

## INDICADORES ACTUALES (última vela):
- RSI(14): {last['rsi']:.1f}
- MACD: {last['macd']:.6f} | Señal: {last['macd_signal']:.6f} | Histograma: {last['macd_hist']:.6f}
- ADX(14): {last['adx']:.1f} | DI+: {last['di_pos']:.1f} | DI-: {last['di_neg']:.1f}

## ÚLTIMAS 50 VELAS (timeframe 1h):
{price_str}

## INDICADORES ÚLTIMAS 20 VELAS:
{prev20[['rsi','macd','macd_signal','adx','di_pos','di_neg']].round(2).to_string()}

## INSTRUCCIONES DE ANÁLISIS:

Analiza según la metodología Elliott de Enrique Santos y responde EXACTAMENTE en este formato JSON:

{{
  "simbolo": "{symbol}",
  "precio_actual": {last['close']:.4f},
  "timestamp": "{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
  "onda_grado_mayor": {{
    "estructura": "Pauta de Impulso alcista / bajista / Correctiva Plana / Zigzag / Terminal",
    "onda_actual": "Onda 1/2/3/4/5 o A/B/C",
    "descripcion": "Descripción breve del contexto de grado mayor",
    "fibonacci_nivel": "Nivel Fibonacci relevante"
  }},
  "onda_grado_menor": {{
    "estructura": "Estructura de grado menor",
    "onda_actual": "Onda actual de menor grado",
    "descripcion": "Descripción del comportamiento de corto plazo",
    "fibonacci_nivel": "Nivel Fibonacci de corto plazo"
  }},
  "señal": {{
    "tipo": "COMPRA | VENTA | ESPERAR | SIN_SEÑAL",
    "fuerza": "FUERTE | MODERADA | DÉBIL",
    "descripcion": "Por qué hay o no hay señal ahora mismo"
  }},
  "niveles": {{
    "entrada": null,
    "stop_loss": null,
    "objetivo_1": null,
    "objetivo_2": null,
    "objetivo_3": null
  }},
  "indicadores": {{
    "rsi_interpretacion": "Sobreventa/Sobrecompra/Divergencia alcista/bajista/Neutro",
    "macd_interpretacion": "Cruce alcista/bajista/Fallo/Divergencia/Neutro",
    "adx_interpretacion": "Tendencia fuerte(>30)/débil(<20)/corte DI+/DI-",
    "confluencia": "Los 3 indicadores confirman la señal? Explica"
  }},
  "ratio_riesgo_beneficio": null,
  "resumen": "Resumen ejecutivo en 2-3 oraciones para el trader",
  "confianza": "ALTA | MEDIA | BAJA",
  "razon_confianza": "Por qué tiene ese nivel de confianza"
}}

IMPORTANTE:
- Si no hay señal clara pon tipo ESPERAR y niveles en null
- Los niveles solo si hay señal COMPRA o VENTA
- Ratio riesgo/beneficio: (objetivo_1 - entrada) / (entrada - stop_loss) para compras
- Solo señal FUERTE cuando hay confluencia de Elliott + 3 indicadores
- Responde SOLO el JSON sin texto adicional"""

    return prompt


def call_claude(prompt: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    body = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}]
    }
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=body,
        timeout=30
    )
    r.raise_for_status()
    text = r.json()["content"][0]["text"].strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def format_telegram_message(analysis: dict) -> str:
    s      = analysis.get("señal", {})
    tipo   = s.get("tipo", "SIN_SEÑAL")
    fuerza = s.get("fuerza", "")

    emoji_señal = {"COMPRA":"🟢","VENTA":"🔴","ESPERAR":"🟡","SIN_SEÑAL":"⚪"}.get(tipo,"⚪")
    emoji_conf  = {"ALTA":"🔥","MEDIA":"⚡","BAJA":"❄️"}.get(analysis.get("confianza",""),"")

    niveles = analysis.get("niveles", {})
    mayor   = analysis.get("onda_grado_mayor", {})
    menor   = analysis.get("onda_grado_menor", {})
    inds    = analysis.get("indicadores", {})

    msg = f"""╔══════════════════════════╗
║ 📊 {analysis.get('simbolo','?'):^22} ║
╚══════════════════════════╝
💰 Precio: *{analysis.get('precio_actual','?')}*
🕐 {analysis.get('timestamp','')}

{emoji_señal} *SEÑAL: {tipo} {fuerza}* {emoji_señal}
_{s.get('descripcion','')}_

━━━━ 🌊 ONDAS ━━━━
📐 *Grado Mayor:* {mayor.get('onda_actual','')} — {mayor.get('estructura','')}
_{mayor.get('descripcion','')}_
Fib: {mayor.get('fibonacci_nivel','')}

🔍 *Grado Menor:* {menor.get('onda_actual','')} — {menor.get('estructura','')}
_{menor.get('descripcion','')}_
Fib: {menor.get('fibonacci_nivel','')}"""

    if tipo in ("COMPRA","VENTA") and niveles.get("entrada"):
        rr = analysis.get("ratio_riesgo_beneficio")
        rr_str = f"{rr:.1f}x" if rr else "N/A"
        msg += f"""

━━━━ 💹 NIVELES ━━━━
🎯 Entrada:    *{niveles.get('entrada','—')}*
🛑 Stop Loss:  *{niveles.get('stop_loss','—')}*
🏁 Objetivo 1: *{niveles.get('objetivo_1','—')}*
🏁 Objetivo 2: *{niveles.get('objetivo_2','—')}*
🏁 Objetivo 3: *{niveles.get('objetivo_3','—')}*
⚖️  R/B: *{rr_str}*"""

    msg += f"""

━━━━ 📈 INDICADORES ━━━━
- RSI:  {inds.get('rsi_interpretacion','')}
- MACD: {inds.get('macd_interpretacion','')}
- ADX:  {inds.get('adx_interpretacion','')}
- Confluencia: {inds.get('confluencia','')}

━━━━ 📝 RESUMEN ━━━━
{analysis.get('resumen','')}

{emoji_conf} Confianza: *{analysis.get('confianza','')}*
_{analysis.get('razon_confianza','')}_"""

    return msg


def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload, timeout=10)
    return r.ok


def save_results(results: list):
    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "last_update": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "analyses": results
        }, f, indent=2, ensure_ascii=False)


def analyze_asset(symbol: str, asset_type: str) -> Optional[dict]:
    print(f"\n{'─'*50}")
    print(f"⏳ Analizando {symbol} ({asset_type})...")
    try:
        if asset_type == "crypto":
            df = fetch_crypto_ohlcv(symbol)
        else:
            df = fetch_stock_ohlcv(symbol)
        print(f"   ✅ Datos descargados: {len(df)} velas")
        df = calculate_indicators(df)
        df = df.dropna()
        print(f"   ✅ Indicadores calculados")
        prompt   = build_analysis_prompt(symbol, df)
        analysis = call_claude(prompt)
        print(f"   ✅ Análisis: {analysis.get('señal',{}).get('tipo','?')} ({analysis.get('confianza','?')})")
        señal_tipo = analysis.get("señal", {}).get("tipo", "SIN_SEÑAL")
        confianza  = analysis.get("confianza", "BAJA")
        if señal_tipo in ("COMPRA","VENTA") or confianza == "ALTA":
            msg  = format_telegram_message(analysis)
            sent = send_telegram(msg)
            print(f"   {'✅' if sent else '❌'} Telegram {'enviado' if sent else 'falló'}")
        else:
            print(f"   ℹ️  Sin señal relevante")
        return analysis
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def main():
    print(f"\n{'═'*50}")
    print(f"🌊 ELLIOTT WAVE ANALYZER")
    print(f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'═'*50}")
    results = []
    for symbol, asset_type in ASSETS:
        analysis = analyze_asset(symbol, asset_type)
        if analysis:
            results.append(analysis)
    save_results(results)
    print(f"\n✅ Completo. {len(results)}/{len(ASSETS)} activos procesados.")


if __name__ == "__main__":
    main()
