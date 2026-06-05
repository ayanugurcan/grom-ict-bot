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
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_tr_saat():
    tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(tz)

def seans_kontrol(parite):
    now = get_tr_saat()
    saat = now.hour + (now.minute / 60.0)
    if now.weekday() >= 5: 
        return False

    if parite == "DAX":
        return 9.0 <= saat <= 12.0
    else:
        return (9.0 <= saat <= 12.0) or (16.5 <= saat <= 17.0) or (19.5 <= saat <= 21.0)

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
    asya_mums = df_bugun[(df_bugun.index.hour >= 0) & (df_bugun.index.hour < 8)]
    if not asya_mums.empty:
        seviyeler["BSL"]["Asian_High"] = float(asya_mums['High'].max())
        seviyeler["SSL"]["Asian_Low"] = float(asya_mums['Low'].min())

    # --- 4. London Range (09:00 - 12:00 TR Saati) ---
    # Sadece saat 12:00'den sonra NY seansında korumak üzere kilitlenir
    if now.hour >= 12:
        london_mums = df_bugun[(df_bugun.index.hour >= 9) & (df_bugun.index.hour < 12)]
        if not london_mums.empty:
            seviyeler["BSL"]["London_High"] = float(london_mums['High'].max())
            seviyeler["SSL"]["London_Low"] = float(london_mums['Low'].min())

    return seviyeler

# ==========================================
# 🔍 TARAMA VE TETİKLEME DÖNGÜSÜ
# ==========================================
def asistan_ana_dongu():
    print("Gelişmiş ICT Likidite Asistanı v2.5 devrede...")
    while True:
        try:
            for ad, sembol in PARITELER.items():
                if not seans_kontrol(ad):
                    continue

                ticker = yf.Ticker(sembol)
                df_15m = ticker.history(period="2d", interval="15m")
                df_1m = ticker.history(period="1d", interval="1m")

                if df_15m.empty or df_1m.empty:
                    continue

                # Canlı seviyeleri al
                havuzlar = likidite_seviyelerini_hesapla(sembol, df_15m, ticker)
                
                canli_mum = df_1m.iloc[-1]
                su_anki_fiyat = float(canli_mum['Close'])
                yurek_high = float(canli_mum['High'])
                yurek_low = float(canli_mum['Low'])

                if ad not in hafiza:
                    hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None, "patlayan_seviye": ""}

                # LİKİDİTE SÜPÜRME KONTROLÜ (SWEEP)
                if hafiza[ad]["durum"] == "BEKLEMEDE":
                    # Üst Likiditeler (BSL) Kontrolü
                    for etiket, seviye_fiyat in havuzlar["BSL"].items():
                        if yurek_high > seviye_fiyat and su_anki_fiyat <= seviye_fiyat:
                            hafiza[ad] = {
                                "durum": "HAZIRLAN",
                                "hedef_yon": "SHORT",
                                "patlayan_seviye": f"{etiket} ({seviye_fiyat})"
                            }
                            telegram_mesaj_gonder(f"🚨 <b>{ad} - LİKİDİTE SÜPÜRÜLDÜ!</b>\n\n🎯 <b>Seviye:</b> {etiket}\n💰 <b>Fiyat:</b> {seviye_fiyat}\n\n<b>1M grafikte CISD (Aşağı Gövde Kapanışı) bekleniyor, pusuya yat boss!</b>")
                            break
                    
                    # Alt Likiditeler (SSL) Kontrolü
                    if hafiza[ad]["durum"] == "BEKLEMEDE": # Üst taraf patlamadıysa alta bak
                        for etiket, seviye_fiyat in havuzlar["SSL"].items():
                            if yurek_low < seviye_fiyat and su_anki_fiyat >= seviye_fiyat:
                                hafiza[ad] = {
                                    "durum": "HAZIRLAN",
                                    "hedef_yon": "LONG",
                                    "patlayan_seviye": f"{etiket} ({seviye_fiyat})"
                                }
                                telegram_mesaj_gonder(f"🚨 <b>{ad} - LİKİDİTE SÜPÜRÜLDÜ!</b>\n\n🎯 <b>Seviye:</b> {etiket}\n💰 <b>Fiyat:</b> {seviye_fiyat}\n\n<b>1M grafikte CISD (Yukarı Gövde Kapanışı) bekleniyor, pusuya yat boss!</b>")
                                break

                # CISD ONAY KONTROLÜ (1M Gövde Kapanışı)
                elif hafiza[ad]["durum"] == "HAZIRLAN":
                    gecmis_1m_open = float(df_1m['Open'].iloc[-2])
                    gecmis_1m_close = float(df_1m['Close'].iloc[-2])

                    if hafiza[ad]["hedef_yon"] == "SHORT" and gecmis_1m_close < gecmis_1m_open:
                        telegram_mesaj_gonder(f"🚀 <b>{ad} - GİRİŞ ONAYLANDI (CISD)!</b>\n\n💥 <b>Süpürülen Yer:</b> {hafiza[ad]['patlayan_seviye']}\n📊 <b>Yön:</b> SHORT\n💰 <b>Giriş:</b> {su_anki_fiyat}\n🛑 <b>Stop:</b> Süpürülen Tepe Üstü\n\n<i>Alchemy ekranından emrini yönetebilirsin. Başarılar!</i>")
                        hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None, "patlayan_seviye": ""}

                    elif hafiza[ad]["hedef_yon"] == "LONG" and gecmis_1m_close > gecmis_1m_open:
                        telegram_mesaj_gonder(f"🚀 <b>{ad} - GİRİŞ ONAYLANDI (CISD)!</b>\n\n💥 <b>Süpürülen Yer:</b> {hafiza[ad]['patlayan_seviye']}\n📊 <b>Yön:</b> LONG\n💰 <b>Giriş:</b> {su_anki_fiyat}\n🛑 <b>Stop:</b> Süpürülen Dip Altı\n\n<i>Alchemy ekranından emrini yönetebilirsin. Başarılar!</i>")
                        hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None, "patlayan_seviye": ""}

        except Exception as e:
            print(f"Tarama Döngü Hatası: {e}")
            
        time.sleep(60)

@app.route('/')
def home():
    return jsonify({"status": "Gelişmiş ICT Asistanı v2.5 Aktif", "hafiza": hafiza}), 200

if __name__ == '__main__':
    t = threading.Thread(target=asistan_ana_dongu)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=10000)
