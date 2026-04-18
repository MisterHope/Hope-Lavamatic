import os
import json

from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import time

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
#fonction de récupération de valeur
def get_monnayeur_value(page):
    page.wait_for_selector("#VALEUR-CASHFLOW")
    # attendre la valeur et la récupérer (sinon valeur sortie = "0000")
    page.wait_for_function("""
    () => {
        const el = document.querySelector("#VALEUR-CASHFLOW");
        return el && el.innerText.trim() !== "0000";
    }
    """)

    value_text = page.inner_text("#VALEUR-CASHFLOW")
    return value_text.replace("€", "").strip().replace(".", ",") #  formatage de la valeur

#fonction d'envoi
def send_snapshot_to_sheet(data):
    paris = pytz.timezone("Europe/Paris")
    now = datetime.now(paris)

    date = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H:%M:%S")

    row = [
        date,
        hour,
        data.get("BUFFA", ""),
        data.get("SAS ART BUBBLE", ""),
        data.get("SAS LAVSPEED 54", ""),
        data.get("SAS TOP SPEED", "")
    ]

    sheet.append_row(row)


#PLAYWRIGHT
#script playwright 
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) #        mettre en False p debug
    page = browser.new_page()

    #login
    page.goto(BASE_URL)
    page.fill('[name="login"]', LOGIN)
    page.fill('[name="password"]', PASSWORD)
    page.click('input[type="submit"]')
    page.wait_for_load_state("networkidle")

    #loop p chaque etab
    results = {}
    for name, selector in LAVERIES:
        #revenir état stable : menu index
        if page.url != MENU_URL:
            page.goto(MENU_URL)

        page.wait_for_selector(selector)
        page.click(selector)

        try:
            value = get_monnayeur_value(page)

            print(name, value)

            if value and value != "0000":
                results[name] = value
            else:
                print(f"[WARN] valeur invalide pour {name}")

        except Exception as e:
            print(f"[ERROR] {name} -> {e}")

        time.sleep(1)  # petite pause stabilité

    browser.close()


#send to Gsheets
send_snapshot_to_sheet(results)
