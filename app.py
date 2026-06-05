from flask import Flask, jsonify
import requests
import threading
import time
from datetime import datetime
import pytz
import yfinance as yf

app = Flask(__name__)

# ==========================================
# 🚨 CONFIGURATIONS
# ==========================================
BOT_TOKEN = "8615953627:AAFXGCiqohep_A95gobPFrLeG148OHz7n1I"
CHAT_ID = "1315197368"

PARITELER = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "NASDAQ": "NQ=F",
    "DAX": "^GDAXI"
}

hafiza = {}

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_tr_saat():
    tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(tz)

# ==========================================
# ⏱️ YENİ AKILLI SEANS FİLTRESİ
# ==========================================
def seans_kontrol(parite):
    now = get_tr_saat()
    saat = now.hour + (now.minute / 60.0)
    
    # Hafta sonu piyasalar kapalıyken bot dinlenmeye geçer
    if now.weekday() >= 5: 
        return False

    # Londra Sabahı + New York (Pre-Market, Açılış, Silver Bullet ve PM seansı dahil tek blok)
    if (9.0 <= saat <= 12.5) or (15.0 <= saat <= 21.0):
        return True
        
    return False

# ==========================================
# 🎯 GELİŞMİŞ LİKİDİTE MOTORU
# ==========================================
def likidite_seviyelerini_hesapla(sembol, df_15m, ticker):
    tr_tz = pytz.timezone('Europe/Istanbul')
    now = datetime.now(tr_tz)
    bugun = now.date()
    
    # 15M verisinin indexini TR saatine çeviriyoruz
    df_15m.index = df_15m.index.tz_convert('Europe/Istanbul')
    df_bugun = df_15m[df_15m.index.date == bugun]

    seviyeler = {"BSL": {}, "SSL": {}}

    # --- 1. PDH / PDL (Dünün En Yükseği / En Düşüğü) ---
    try:
        df_daily = ticker.history(period="3d", interval="1d")
        if len(df_daily) >= 2:
            seviyeler["BSL"]["PDH"] = float(df_daily['High'].iloc[-2])
            seviyeler["SSL"]["PDL"] = float(df_daily['Low'].iloc[-2])
    except:
        pass

    # --- 2. HTF Swing High/Low (Son 20 Mumun Zirve/Dibi) ---
    seviyeler["BSL"]["HTF_Swing"] = float(df_15m['High'].iloc[-20:].max())
    seviyeler["SSL"]["HTF_Swing"] = float(df_15m['Low'].iloc[-20:].min())

    # --- 3. Asian Range (00:00 - 08:00 TR Saati) ---
    asya_mums = df_bugun
