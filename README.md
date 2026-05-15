# 🌊 Elliott Wave Analyzer

Análisis automático de Ondas de Elliott cada hora, basado en la metodología de **Enrique Santos**.

## ¿Qué hace?
- Descarga datos OHLCV de **Binance** (cripto) y **Yahoo Finance** (acciones)
- Calcula RSI(14), MACD y ADX automáticamente
- Le pide a **Claude** que analice la estructura Elliott en grado mayor y menor
- Si hay señal, te avisa por **Telegram** con entrada, stop y 3 objetivos
- Muestra todo en un **dashboard web** actualizado cada hora

---

## ⚙️ Setup (15 minutos)

### 1. Bot de Telegram
1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot` y sigue los pasos → obtienes el **TOKEN**
3. Busca **@userinfobot** y envíate un mensaje → obtienes tu **CHAT_ID**

### 2. API Key de Anthropic
1. Ve a https://console.anthropic.com
2. Crea una API Key

### 3. Subir a GitHub
```bash
git init
git add .
git commit -m "Elliott Wave Analyzer"
git remote add origin https://github.com/TU_USUARIO/elliott-analyzer.git
git push -u origin main
```

### 4. Configurar secretos en GitHub
Ve a tu repo → Settings → Secrets → Actions → New repository secret:
- `TELEGRAM_TOKEN`    → el token del bot
- `TELEGRAM_CHAT_ID`  → tu chat ID
- `ANTHROPIC_API_KEY` → tu API key de Anthropic

### 5. Activar GitHub Pages (dashboard web)
Settings → Pages → Source: `gh-pages` branch

### 6. Configurar tus activos
Edita `analyzer.py` y modifica la lista `ASSETS`:
```python
ASSETS = [
    ("BTCUSDT", "crypto"),
    ("ETHUSDT", "crypto"),
    ("AAPL",    "stock"),
    ("NVDA",    "stock"),
]
```

---

## 💰 Costo estimado

| Componente       | Costo        |
|-----------------|--------------|
| Binance API     | Gratis       |
| Yahoo Finance   | Gratis       |
| GitHub Actions  | Gratis       |
| GitHub Pages    | Gratis       |
| Telegram Bot    | Gratis       |
| Claude API      | ~$0.01/análisis |

Con 4 activos cada hora → ~$1/día máximo. En práctica mucho menos porque solo envía cuando hay señal.

---

## 📱 Ejemplo de alerta Telegram

```
╔══════════════════════════╗
║        BTCUSDT           ║
╚══════════════════════════╝
💰 Precio: 67,450.00
🕐 2025-05-15 14:00 UTC

🟢 SEÑAL: COMPRA FUERTE 🟢
_El precio completa onda 2 con retroceso del 66% sobre onda 1._

━━━━ 🌊 ONDAS ━━━━
📐 Grado Mayor: Onda 3 — Pauta de Impulso alcista
🔍 Grado Menor: Onda 2 finalizada — Zigzag correctivo

━━━━ 💹 NIVELES ━━━━
🎯 Entrada:    67,450
🛑 Stop Loss:  66,100
🏁 Objetivo 1: 69,640
🏁 Objetivo 2: 71,850
🏁 Objetivo 3: 75,200
⚖️  R/B: 3.2x

🔥 Confianza: ALTA
```
