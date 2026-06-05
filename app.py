from flask import Flask, request, jsonify
import requests
from datetime import datetime
import pytz

app = Flask(__name__)

# ==========================================
# 🚨 TEST MODU AYARI
# True iken: Saat ne olursa olsun sinyal Telegram'a düşer (Test için).
# False iken: Sadece aşağıdaki seans saatlerinde sinyal gönderir.
TEST_MODE = True
# ==========================================

# Telegram Bot Bilgileri
BOT_TOKEN = "8615953627:AAFXGCiqohep_A95gobPFrLeG148OHz7n1I"
CHAT_ID = "1315197368"

# Zaman Kontrol Fonksiyonu (Türkiye Saati - Istanbul)
def is_valid_session(parite):
    # Eğer test modu aktifse zaman kontrolünü bypass et ve onay ver
    if TEST_MODE:
        return True

    # TR saatini al
    tz = pytz.timezone('Europe/Istanbul')
    now = datetime.now(tz)
    saat = now.hour + (now.minute / 60.0)

    # Paritelere göre seans kontrolleri
    if parite == "DAX":
        # Londra (09:00 - 12:00)
        return 9.0 <= saat <= 12.0
        
    elif parite in ["NAS100", "NQ"]:
        # Londra (10:30 - 12:00) | NY AM (16:30 - 17:00) | NY PM (19:30 - 21:00)
        return (10.5 <= saat <= 12.0) or (16.5 <= saat <= 17.0) or (19.5 <= saat <= 21.0)
        
    elif parite in ["EURUSD", "GBPUSD", "AUDUSD"]:
        # Londra (09:00-12:00) | NY AM (16:30-17:00) | NY PM (19:30-21:00)
        return (9.0 <= saat <= 12.0) or (16.5 <= saat <= 17.0) or (19.5 <= saat <= 21.0)
        
    return False

# TradingView'dan gelecek sinyalleri yakalayan bölüm (Webhook Endpoint)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    parite = data.get('parite', 'Bilinmiyor')
    
    # Sinyal doğru zamanda mı geldi?
    if is_valid_session(parite):
        # Telegram'a gönderilecek mesajı hazırla
        mesaj = f"🚨 <b>{parite} - ICT+CISD Sinyali</b>\n\n"
        mesaj += f"📊 <b>İşlem:</b> {data.get('islem_yonu')}\n"
        mesaj += f"💰 <b>Giriş:</b> {data.get('fiyat')}\n"
        mesaj += f"🛑 <b>Stop:</b> {data.get('stop')}\n\n"
        mesaj += f"📝 <b>Analiz:</b> {data.get('not')}"
        
        # Telegram API'sine gönder
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": mesaj,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload)
        return jsonify({"status": "Basarili", "message": "Sinyal iletildi"}), 200
    else:
        # Seans dışı - sinyali yoksay (seni rahatsız etmez)
        return jsonify({"status": "Reddedildi", "message": "Seans disi sinyal"}), 200

# Sunucuyu Başlat
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
