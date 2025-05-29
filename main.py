import os
import requests
from bs4 import BeautifulSoup
import time
import threading
import logging
import json

from keep_alive import keep_alive  # 👈 Legg til dette

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.error("BOT_TOKEN environment variable is not set!")
    exit(1)

try:
    OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID"))
except (TypeError, ValueError):
    logging.error("OWNER_CHAT_ID environment variable is not set or invalid!")
    exit(1)
OPPDATERINGSINTERVALL = 50
REQUEST_TIMEOUT = 31  # Timeout i sekunder

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
GODKJENTE_FIL = "godkjente_brukere.json"

def last_godkjente_brukere():
    if os.path.exists(GODKJENTE_FIL):
        try:
            with open(GODKJENTE_FIL, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Feil ved lasting av godkjente brukere: {e}")
            return {}
    return {}

def lagre_godkjente_brukere(data):
    try:
        with open(GODKJENTE_FIL, "w") as f:
            json.dump(data, f)
    except IOError as e:
        logging.error(f"Feil ved lagring av godkjente brukere: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

godkjente_brukere = last_godkjente_brukere()
venter_pa_godkjenning = {}
sist_meldinger = set()

def hent_traffikkmeldinger():
    url = "https://www.banenor.no/reise-og-trafikk/trafikkmeldinger/"
    try:
        logging.debug(f"Henter trafikkmeldinger fra: {url}")
        r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        r.raise_for_status()
        logging.debug(f"HTTP status: {r.status_code}")
    except requests.RequestException as e:
        logging.error(f"Feil ved henting av trafikkmeldinger: {e}")
        return []

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        meldinger_divs = soup.find_all("div", class_="traffic-information__item")
        logging.debug(f"Fant {len(meldinger_divs)} trafikkinformasjon-elementer")

        meldinger = []
        for div in meldinger_divs:
            try:
                tittel_tag = div.find("h3", class_="traffic-information__title")
                tekst_tag = div.find("div", class_="traffic-information__text")
                if tittel_tag and tekst_tag:
                    tittel = tittel_tag.get_text(separator=" ", strip=True)
                    tekst = tekst_tag.get_text(separator=" ", strip=True)
                    melding = f"{tittel}\n\n{tekst}"
                    meldinger.append(melding)
                    logging.debug(f"Behandlet melding: {tittel[:50]}...")
            except Exception as e:
                logging.warning(f"Feil ved behandling av enkelt melding: {e}")
                continue

        logging.info(f"Hentet {len(meldinger)} trafikkmeldinger totalt")
        return meldinger
        
    except Exception as e:
        logging.error(f"Feil ved parsing av HTML: {e}")
        return []

def send_telegram_melding(chat_id, tekst):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": tekst}
    try:
        resp = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
        if not resp.ok:
            logging.error(f"Feil ved sending til chat_id {chat_id}: {resp.text}")
        return resp.ok
    except requests.RequestException as e:
        logging.error(f"Unntak ved sending til chat_id {chat_id}: {e}")
        return False

def behandle_melding(melding):
    chat_id = melding["chat"]["id"]
    tekst = melding.get("text", "").strip()

    if tekst == "/register":
        if str(chat_id) in godkjente_brukere:
            send_telegram_melding(chat_id, "Du er allerede godkjent og mottar varsler.")
        elif chat_id in venter_pa_godkjenning:
            send_telegram_melding(chat_id, "Du har allerede sendt registreringsforespørsel. Vennligst vent på godkjenning.")
        else:
            venter_pa_godkjenning[chat_id] = melding["from"].get("first_name", "Ukjent")
            send_telegram_melding(chat_id, "Registreringsforespørselen din er mottatt. Vent på godkjenning.")
            send_telegram_melding(OWNER_CHAT_ID, f"Registreringsforespørsel fra {venter_pa_godkjenning[chat_id]} (chat_id: {chat_id}).\nSend /godkjenn {chat_id} for å godkjenne, eller /avslå {chat_id} for å avslå.")

    elif tekst.startswith("/godkjenn"):
        if chat_id != OWNER_CHAT_ID:
            send_telegram_melding(chat_id, "Du har ikke tilgang til denne kommandoen.")
            return
        deler = tekst.split()
        if len(deler) != 2 or not deler[1].isdigit():
            send_telegram_melding(chat_id, "Bruk formatet /godkjenn <chat_id>")
            return
        godkjenn_id = int(deler[1])
        if godkjenn_id in venter_pa_godkjenning:
            godkjente_brukere[str(godkjenn_id)] = venter_pa_godkjenning.pop(godkjenn_id)
            lagre_godkjente_brukere(godkjente_brukere)
            send_telegram_melding(OWNER_CHAT_ID, f"Bruker med chat_id {godkjenn_id} er godkjent.")
            send_telegram_melding(godkjenn_id, "Du er nå godkjent og vil motta varsler.")
        else:
            send_telegram_melding(chat_id, f"Fant ingen ventende bruker med chat_id {godkjenn_id}.")

    elif tekst.startswith("/avslå"):
        if chat_id != OWNER_CHAT_ID:
            send_telegram_melding(chat_id, "Du har ikke tilgang til denne kommandoen.")
            return
        deler = tekst.split()
        if len(deler) != 2 or not deler[1].isdigit():
            send_telegram_melding(chat_id, "Bruk formatet /avslå <chat_id>")
            return
        avslå_id = int(deler[1])
        if avslå_id in venter_pa_godkjenning:
            venter_pa_godkjenning.pop(avslå_id)
            send_telegram_melding(OWNER_CHAT_ID, f"Bruker med chat_id {avslå_id} er avslått.")
            send_telegram_melding(avslå_id, "Din registreringsforespørsel er dessverre avslått.")
        else:
            send_telegram_melding(chat_id, f"Fant ingen ventende bruker med chat_id {avslå_id}.")

    else:
        send_telegram_melding(chat_id, "Ukjent kommando. Bruk /register for å søke tilgang.")

def hent_oppdateringer(offset=None):
    url = f"{TELEGRAM_API_URL}/getUpdates?timeout=30"
    if offset:
        url += f"&offset={offset}"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok", False):
            logging.error(f"Telegram API feil: {data.get('description', 'Ukjent feil')}")
            return {"result": []}
        return data
    except (requests.RequestException, ValueError) as e:
        logging.error(f"Feil ved henting av oppdateringer: {e}")
        return {"result": []}

def sjekk_trafikkmeldinger():
    global sist_meldinger
    while True:
        try:
            logging.info("Sjekker for nye trafikkmeldinger...")
            meldinger = hent_traffikkmeldinger()
            
            if not meldinger:
                logging.info("Ingen trafikkmeldinger funnet")
                time.sleep(OPPDATERINGSINTERVALL)
                continue
                
            logging.info(f"Hentet {len(meldinger)} trafikkmeldinger")
            nye_meldinger = [m for m in meldinger if m not in sist_meldinger]

            if nye_meldinger:
                logging.info(f"Fant {len(nye_meldinger)} nye trafikkmeldinger")
                for melding in nye_meldinger:
                    for bruker_id in godkjente_brukere:
                        try:
                            success = send_telegram_melding(int(bruker_id), melding)
                            if success:
                                logging.info(f"Sendt melding til bruker {bruker_id}")
                            else:
                                logging.warning(f"Kunne ikke sende melding til bruker {bruker_id}")
                        except ValueError as e:
                            logging.error(f"Ugyldig bruker_id: {bruker_id} - {e}")
                            
                sist_meldinger.update(nye_meldinger)
                # Bedre minnehåndtering - behold bare de 50 siste meldingene
                if len(sist_meldinger) > 100:
                    sist_meldinger_liste = list(sist_meldinger)
                    sist_meldinger = set(sist_meldinger_liste[-50:])
            else:
                logging.info("Ingen nye trafikkmeldinger")
                
        except Exception as e:
            logging.exception(f"Feil i trafikkmeldings-tråd: {e}")
            
        time.sleep(OPPDATERINGSINTERVALL)

def main():
    keep_alive()  # ✅ Start webserver for UptimeRobot
    siste_update_id = None
    logging.info("Starter bot...")

    # Start trafikkmeldinger-tråd
    trafikk_thread = threading.Thread(target=sjekk_trafikkmeldinger, daemon=True)
    trafikk_thread.start()

    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            updates = hent_oppdateringer(offset=siste_update_id)
            
            if not updates.get("result"):
                time.sleep(1)
                continue
                
            for update in updates.get("result", []):
                siste_update_id = update["update_id"] + 1
                if "message" in update:
                    try:
                        behandle_melding(update["message"])
                    except Exception as e:
                        logging.error(f"Feil ved behandling av melding: {e}")
            
            consecutive_errors = 0  # Reset error counter on success
            
        except KeyboardInterrupt:
            logging.info("Bot stopper...")
            break
        except Exception as e:
            consecutive_errors += 1
            logging.exception(f"Uventet feil i hovedløkken (feil #{consecutive_errors})")
            
            if consecutive_errors >= max_consecutive_errors:
                logging.critical("For mange påfølgende feil. Stopper bot.")
                break
                
            # Eksponentiell backoff ved feil
            wait_time = min(60, 2 ** consecutive_errors)
            time.sleep(wait_time)

if __name__ == "__main__":
    main()