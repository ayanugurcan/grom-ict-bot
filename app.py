from flask import Flask, jsonify
import requests
import threading
import time
from datetime import datetime
import pytz
import yfinance as yf

app = Flask(__name__)

# ==========================================
# 🚨 CORES & CONFIGURATIONS
# ==========================================
BOT_TOKEN = "8615953627:AAFXGCiqohep_A95gobPFrLeG148OHz7n1I"
CHAT_ID = "1315197368"

# Parite Eşleştirmeleri (Yahoo Finance Sembolleri)
PARITELER = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "NASDAQ": "NQ=F",
    "DAX": "^GDAXI"
}

# Hafıza Havuzu (Seviyeleri burada saklayacağız)
hafiza = {}

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Hatası: {e}")

# ==========================================
# 🕒 SEANS VE ZAMAN KONTROLLERİ
# ==========================================
def get_tr_saat():
    tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(tz)

def seans_kontrol(parite):
    now = get_tr_saat()
    saat = now.hour + (now.minute / 60.0)
    gun = now.weekday() # 5 = Cumartesi, 6 = Pazar

    if gun >= 5: # Hafta sonu piyasa kapalı
        return False

    if parite == "DAX":
        return 9.0 <= saat <= 12.0 # Sadece Londra
    else:
        # Londra (09:00-12:00) | NY AM (16:30-17:00) | NY PM (19:30-21:00)
        return (9.0 <= saat <= 12.0) or (16.5 <= saat <= 17.0) or (19.5 <= saat <= 21.0)

# ==========================================
# 🔍 LİKİDİTE VE CISD MOTORU (7/24 DÖNGÜ)
# ==========================================
def asistan_ana_dongu():
    print("ICT CISD Asistanı arka planda avlanmaya başladı...")
    while True:
        try:
            now = get_tr_saat()
            
            for ad, sembol in PARITELER.items():
                if not seans_kontrol(ad):
                    continue # Seans dışıysa bu pariteyi pas geç

                # Canlı veriyi çek (15M grafiği seviyeler için, 1M kırılım için)
                ticker = yf.Ticker(sembol)
                df_15m = ticker.history(period="2d", interval="15m")
                df_1m = ticker.history(period="1d", interval="1m")

                if df_15m.empty or df_1m.empty:
                    continue

                # 1. Otomatik Seviye Tespiti (Fractal Mantığı)
                # Son 20 mumun en yüksek ve en düşüğünü 'sağlam' kabul ediyoruz
                majör_bsl = float(df_15m['High'].iloc[-20:].max())
                majör_ssl = float(df_15m['Low'].iloc[-20:].min())
                
                canli_mum = df_1m.iloc[-1]
                su_anki_fiyat = float(canli_mum['Close'])
                yüksek_fiyat = float(canli_mum['High'])
                düsük_fiyat = float(canli_mum['Low'])

                # Parite hafızada yoksa ilklendir
                if ad not in hafiza:
                    hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None}

                # 2. Aşama: Likidite Süpürme Kontrolü (Sweep)
                if hafiza[ad]["durum"] == "BEKLEMEDE":
                    if yüksek_fiyat > majör_bsl and su_anki_fiyat <= majör_bsl:
                        hafiza[ad]["durum"] = "HAZIRLAN"
                        hafiza[ad]["hedef_yon"] = "SHORT"
                        telegram_mesaj_gonder(f"🚨 <b>{ad} - LİKİDİTE ALINDI!</b>\n\nTepe Likiditesi (BSL) süpürüldü. Kurumlar yukarıdaki stopları patlattı.\n💰 Seviye: {majör_bsl}\n\n<b>Pusuya yat, 1M grafikte CISD (Aşağı Kırılım) bekleniyor!</b>")
                    
                    elif düsük_fiyat < majör_ssl and su_anki_fiyat >= majör_ssl:
                        hafiza[ad]["durum"] = "HAZIRLAN"
                        hafiza[ad]["hedef_yon"] = "LONG"
                        telegram_mesaj_gonder(f"🚨 <b>{ad} - LİKİDİTE ALINDI!</b>\n\nDip Likiditesi (SSL) süpürüldü. Küçük yatırımcı elendi.\n💰 Seviye: {majör_ssl}\n\n<b>Pusuya yat, 1M grafikte CISD (Yukarı Kırılım) bekleniyor!</b>")

                # 3. Aşama: CISD Gövde Kapanış Onayı
                elif hafiza[ad]["durum"] == "HAZIRLAN":
                    # Önceki 1M mumun gövde kırılımını kontrol et
                    gecmis_1m_open = float(df_1m['Open'].iloc[-2])
                    gecmis_1m_close = float(df_1m['Close'].iloc[-2])

                    if hafiza[ad]["hedef_yon"] == "SHORT" and gecmis_1m_close < gecmis_1m_open:
                        # Sert bir bearish mum yapıyı kırdı (CISD)
                        telegram_mesaj_gonder(f"🚀 <b>{ad} - GİRİŞ ONAYLANDI (CISD)!</b>\n\nAyılar devreye girdi, 1M gövde kapanışı yapıyı aşağı kırdı.\n\n📊 <b>Yön:</b> SHORT\n💰 <b>Giriş Fiyatı:</b> {su_anki_fiyat}\n🛑 <b>Stop:</b> Süpürülen Tepe Üstü\n\n<i>Kurallarına sadık kal, riskini yönet kanka!</i>")
                        hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None} # Resetle

                    elif hafiza[ad]["hedef_yon"] == "LONG" and gecmis_1m_close > gecmis_1m_open:
                        # Sert bir bullish mum yapıyı kırdı (CISD)
                        telegram_mesaj_gonder(f"🚀 <b>{ad} - GİRİŞ ONAYLANDI (CISD)!</b>\n\nBoğalar devreye girdi, 1M gövde kapanışı yapıyı yukarı kırdı.\n\n📊 <b>Yön:</b> LONG\n💰 <b>Giriş Fiyatı:</b> {su_anki_fiyat}\n🛑 <b>Stop:</b> Süpürülen Dip Altı\n\n<i>Kurallarına sadık kal, riskini yönet kanka!</i>")
                        hafiza[ad] = {"durum": "BEKLEMEDE", "hedef_yon": None} # Resetle

        except Exception as e:
            print(f"Tarama Hatası: {e}")
            
        time.sleep(60) # Her dakika başı tara

# Web sunucusunu açık tutmak için boş ana sayfa (Render kapanmasın diye)
@app.route('/')
def home():
    return jsonify({"status": "Asistan aktif ve avlanıyor", "hafiza": hafiza}), 200

if __name__ == '__main__':
    # Arka plan tarayıcısını ana sunucudan bağımsız başlatıyoruz
    t = threading.Thread(target=asistan_ana_dongu)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=10000)
