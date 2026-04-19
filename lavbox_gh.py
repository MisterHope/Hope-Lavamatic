from dotenv import load_dotenv
load_dotenv()

import os
import json

import requests

from playwright.sync_api import sync_playwright

import gspread
from google.oauth2.service_account import Credentials

from datetime import datetime
import pytz
import time

paris = pytz.timezone("Europe/Paris")
now = datetime.now(paris)

# blocage hors plage horaire
if not (6 <= now.hour < 22):
    print("Hors plage horaire → arrêt")
    exit()

    
#config & index laveries
LOGIN = os.environ["SITE_LOGIN"]
PASSWORD = os.environ["SITE_PASSWORD"]
if not LOGIN or not PASSWORD:
    raise Exception("Variables d'environnement manquantes")

BASE_URL = os.environ["BASE_URL"]
MENU_URL = os.environ["MENU_URL"]

LAVERIES = [
    ("BUFFA", "text=BUFFA"),
    ("SAS ART BUBBLE", "text=SAS ART BUBBLE"),
    ("SAS LAVSPEED 54", "text=SAS LAVSPEED 54"),
    ("SAS TOP SPEED", "text=SAS TOP SPEED")
]

#TG alerts anti spam
STATE_FILE = "alert_state.json"

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        last_alert_state = json.load(f)
else:
    last_alert_state = {}


#GOOGLE
#permissions
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
#load JSON key from service account
creds_info = json.loads(os.environ["GOOGLE_CREDS"])
creds = Credentials.from_service_account_info(
    creds_info,
    scopes=scopes
)
#gSheets connection and open spreadsheet
client = gspread.authorize(creds)
sheet = client.open("Historique Monnayeur").sheet1


#FONCTIONS
#récup des valeurs
def get_monnayeur_value(page):
    page.wait_for_selector("#VALEUR-CASHFLOW")
    # attendre la valeur et la récupérer (sinon valeur sortie = "0000")
    page.wait_for_function("""
    () => {
        const el = document.querySelector("#VALEUR-CASHFLOW");
        return el && el.innerText.trim() !== "0000";
    }
    """, timeout=10000)

    value_text = page.inner_text("#VALEUR-CASHFLOW")
    return value_text.replace("€", "").strip().replace(".", ",") #  formatage de la valeur

#envoi
def send_snapshot_to_sheet(data):
    paris = pytz.timezone("Europe/Paris")
    now = datetime.now(paris)

    date = now.strftime("%d-%m-%Y")
    hour = now.strftime("%H:%M")

    row = [
        date,
        hour,
        data.get("BUFFA", ""),
        data.get("SAS ART BUBBLE", ""),
        data.get("SAS LAVSPEED 54", ""),
        data.get("SAS TOP SPEED", "")
    ]

    sheet.append_row(row, value_input_option="USER_ENTERED")

#alertes telegram
def telegram_alert(message):
    token = os.environ["TG_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    requests.get(url, params={
        "chat_id": chat_id,
        "text": message
    })


#PLAYWRIGHT
#script playwright 
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True, #        mettre en False p debug
        args=["--no-sandbox", "--disable-dev-shm-usage"] # stuff p que gh s'en sorte
    )
    page = browser.new_page()

    #login
    page.goto(BASE_URL)
    page.fill('[name="login"]', LOGIN)
    page.fill('[name="password"]', PASSWORD)
    page.click('input[type="submit"]')
    page.wait_for_load_state("networkidle")

    results = {}
    threshold_raw = sheet.acell("H4").value  # lit le seuil d'alerte depuis une cellule puis le format en float
    threshold = float(threshold_raw.replace("€", "").replace(",", ".").strip())
    #loop p chaque etab
    for name, selector in LAVERIES:
        #revenir état stable : menu index
        if page.url != MENU_URL:
            page.goto(MENU_URL)

        page.wait_for_selector(selector)
        page.click(selector)

        try:
            value = get_monnayeur_value(page)

            print(name, value)

            #alerte TG
            # conversion en float
            try:
                numeric_value = float(value.replace(",", "."))
            except:
                numeric_value = None

            if numeric_value is not None:

                previous_value = last_alert_state.get(name) #valeur précédente, récupérée dans le json

                if previous_value is not None:
                    variation = abs(numeric_value - previous_value) #comparaison anc valeur avec nouv valeur

                    if variation > threshold: #si variation dépasse seuil, envoi alerte TG
                        telegram_alert(
                            f"⚠️ {name} variation : {variation:.2f} € "
                            f"(ancien {previous_value:.2f} → actuel {numeric_value:.2f}, seuil {threshold} €)"
                        )

                # MAJ valeur
                last_alert_state[name] = numeric_value

            # storage p envoi à Gsheets
            if value and value != "0000":
                results[name] = value
            else:
                print(f"[WARN] valeur invalide pour {name}")

        except Exception as e:
            print(f"[ERROR] {name} -> {e}")

        time.sleep(1)  # petite pause stabilité

    browser.close()

#TG: auto json dump anti spam
with open(STATE_FILE, "w") as f:
    json.dump(last_alert_state, f)

#send to Gsheets
send_snapshot_to_sheet(results)
