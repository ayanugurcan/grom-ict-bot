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

# ==========================================
# ⏱️ AKILLI SEANS FİLTRESİ
# ==========================================
def seans_kontrol(parite):
    now = get_tr_saat()
    saat = now.hour + (now.minute / 60.0)
    
    if now.weekday() >= 5: 
        return False

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
    
    df_15m.index = df_15m.index.tz_convert('Europe/Istanbul')
    df_bugun = df_15m[df_15m.index.date == bugun]

    seviyeler = {"BSL": {}, "SSL": {}}

    try:
        df_daily = ticker.history(period="3d", interval="1d")
        if len(df_daily) >= 2:
            seviyeler["BSL"]["PDH"] = float(df_daily['High'].iloc[-2])
            seviyeler["SSL"]["PDL"] = float(df_daily['Low'].iloc[-2])
    except:
        pass

    seviyeler["BSL"]["HTF_Swing"] = float(df_15m['High'].iloc[-20:].max())
    seviyeler["SSL"]["HTF_Swing"] = float(df_15m['Low'].iloc[-20:].min())

    asya_mums = df_bugun[(df_bugun.index.hour >= 0) & (df_bugun.index.hour < 8)]
    if not asya_mums.empty:
        seviyeler["BSL"]["Asian_High"] = float(asya_mums['High'].max())
        seviyeler["SSL"]["Asian_Low"] = float(asya_mums['Low'].min())

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
    print("Gelişmiş ICT Likidite Asistanı v2.6 devrede...")
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

                havuzlar = likidite_seviyelerini_hesapla(sembol, df_15m, ticker)
                
                canli_mum = df_1m.iloc[-1]
                su_anki_fiyat = float(canli_mum['Close'])
                yurek_high = float(canli_mum['High'])
                yurek_low = float(canli_mum['Low'])

                if ad not in hafiza:
                    hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None, "patlayan_seviye": "", "likidite_fiyat": 0.0, "cisd_esik": 0.0}

                # 1️⃣ LİKİDİTE SÜPÜRME KONTROLÜ (SWEEP)
                if hafiza[ad]["durum"] == "BEKLEMEDE":
                    # Üst Likiditeler (BSL)
                    for etiket, seviye_fiyat in havuzlar["BSL"].items():
                        if yurek_high > seviye_fiyat and su_anki_fiyat <= seviye_fiyat:
                            # Son 5 mumdaki en son boğa (yeşil) mumun açılışını bul (SHORT CISD Eşiği)
                            esik_fiyat = seviye_fiyat
                            for i in range(len(df_1m)-1, max(-1, len(df_1m)-6), -1):
                                if df_1m['Close'].iloc[i] > df_1m['Open'].iloc[i]:
                                    esik_fiyat = float(df_1m['Open'].iloc[i])
                                    break
                            
                            hafiza[ad] = {
                                "durum": "HAZIRLAN",
                                "hedef_yon": "SHORT",
                                "patlayan_seviye": f"{etiket} ({seviye_fiyat})",
                                "likidite_fiyat": seviye_fiyat,
                                "cisd_esik": esik_fiyat
                            }
                            telegram_mesaj_gonder(f"🚨 <b>{ad} - LİKİDİTE SÜPÜRÜLDÜ!</b>\n\n🎯 <b>Seviye:</b> {etiket}\n💰 <b>Çizgi Fiyatı:</b> {seviye_fiyat}\n⚠️ <b>CISD Tetik Seviyesi:</b> {esik_fiyat}\n\n<b>1M gövdesi hem çizginin hem de tetik seviyesinin ALTINDA kapattığı an sinyal gelecek. Pusuya devam boss!</b>")
                            break
                    
                    # Alt Likiditeler (SSL)
                    if hafiza[ad]["durum"] == "BEKLEMEDE":
                        for etiket, seviye_fiyat in havuzlar["SSL"].items():
                            if yurek_low < seviye_fiyat and su_anki_fiyat >= seviye_fiyat:
                                # Son 5 mumdaki en son ayı (kırmızı) mumun açılışını bul (LONG CISD Eşiği)
                                esik_fiyat = seviye_fiyat
                                for i in range(len(df_1m)-1, max(-1, len(df_1m)-6), -1):
                                    if df_1m['Close'].iloc[i] < df_1m['Open'].iloc[i]:
                                        esik_fiyat = float(df_1m['Open'].iloc[i])
                                        break
                                
                                hafiza[ad] = {
                                    "durum": "HAZIRLAN",
                                    "hedef_yon": "LONG",
                                    "patlayan_seviye": f"{etiket} ({seviye_fiyat})",
                                    "likidite_fiyat": seviye_fiyat,
                                    "cisd_esik": esik_fiyat
                                }
                                telegram_mesaj_gonder(f"🚨 <b>{ad} - LİKİDİTE SÜPÜRÜLDÜ!</b>\n\n🎯 <b>Seviye:</b> {etiket}\n💰 <b>Çizgi Fiyatı:</b> {seviye_fiyat}\n⚠️ <b>CISD Tetik Seviyesi:</b> {esik_fiyat}\n\n<b>1M gövdesi hem çizginin hem de tetik seviyesinin ÜSTÜNDE kapattığı an sinyal gelecek. Pusuya devam boss!</b>")
                                break

                # 2️⃣ GERÇEK VE MİLMETRİK CISD ONAY KONTROLÜ
                elif hafiza[ad]["durum"] == "HAZIRLAN":
                    gecmis_1m_open = float(df_1m['Open'].iloc[-2])
                    gecmis_1m_close = float(df_1m['Close'].iloc[-2])
                    liq_fiyat = hafiza[ad]["likidite_fiyat"]
                    esik_fiyat = hafiza[ad]["cisd_esik"]

                    if hafiza[ad]["hedef_yon"] == "SHORT":
                        # Şartlar: Mum kırmızı olmalı AND çizginin altında kapatmalı AND son boğa mumunun açılışını aşağı kırmalı
                        if gecmis_1m_close < gecmis_1m_open and gecmis_1m_close < liq_fiyat and gecmis_1m_close < esik_fiyat:
                            telegram_mesaj_gonder(f"🚀 <b>{ad} - GİRİŞ ONAYLANDI (CISD)!</b>\n\n💥 <b>Süpürülen Yer:</b> {hafiza[ad]['patlayan_seviye']}\n📊 <b>Yön:</b> SHORT\n💰 <b>Anlık Giriş:</b> {su_anki_fiyat}\n🛑 <b>Stop:</b> Süpürülen Tepe Üstü\n\n<i>Kapanış nizami geldi, emrini yönetebilirsin boss!</i>")
                            hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None, "patlayan_seviye": "", "likidite_fiyat": 0.0, "cisd_esik": 0.0}

                    elif hafiza[ad]["hedef_yon"] == "LONG":
                        # Şartlar: Mum yeşil olmalı AND çizginin üstünde kapatmalı AND son ayı mumunun açılışını yukarı kırmalı
                        if gecmis_1m_close > gecmis_1m_open and gecmis_1m_close > liq_fiyat and gecmis_1m_close > esik_fiyat:
                            telegram_mesaj_gonder(f"🚀 <b>{ad} - GİRİŞ ONAYLANDI (CISD)!</b>\n\n💥 <b>Süpürülen Yer:</b> {hafiza[ad]['patlayan_seviye']}\n📊 <b>Yön:</b> LONG\n💰 <b>Anlık Giriş:</b> {su_anki_fiyat}\n🛑 <b>Stop:</b> Süpürülen Dip Altı\n\n<i>Kapanış nizami geldi, emrini yönetebilirsin boss!</i>")
                            hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None, "patlayan_seviye": "", "likidite_fiyat": 0.0, "cisd_esik": 0.0}

        except Exception as e:
            print(f"Tarama Döngü Hatası: {e}")
            
        time.sleep(60)

@app.route('/')
def home():
    return jsonify({"status": "Gelişmiş ICT Asistanı v2.6 Aktif", "hafiza": hafiza}), 200

if __name__ == '__main__':
    t = threading.Thread(target=asistan_ana_dongu)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=10000)
