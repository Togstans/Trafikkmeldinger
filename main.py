import os
import time
import requests
from bs4 import BeautifulSoup

# Henter inn miljøvariabler
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Telegram API URL
TELEGRAM_API_URL = f"https://api.telegram.org/bot{7645788825:AAH5bu4KWRl7HOISsRq-lXmNTg2bCRYXplw}/sendMessage"

# Bane NOR trafikkmeldinger-side
BANENOR_URL = "https://www.banenor.no/reise-og-trafikk/trafikkmeldinger/"

def hent_trafikkmeldinger():
    try:
        res = requests.get(BANENOR_URL)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        meldinger = soup.select(".traffic-message__content")
        tekst = "\n\n".join([m.get_text(strip=True) for m in meldinger])
        
        return tekst if tekst else "Ingen trafikkmeldinger nå."
    except Exception as e:
        return f"Feil ved henting av trafikkmeldinger: {e}"

def send_telegram_melding(melding):
    payload = {
        "chat_id": CHAT_ID,
        "text": melding,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(TELEGRAM_API_URL, data=payload)
        return response.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def main():
    siste_melding = ""
    while True:
        melding = hent_trafikkmeldinger()
        if melding != siste_melding:
            print("Ny melding – sender til Telegram...")
            send_telegram_melding(melding)
            siste_melding = melding
        time.sleep(3)  # Sjekker hvert 3. sekund

if __name__ == "__main__":
    main() 
