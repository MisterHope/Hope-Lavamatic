from dotenv import load_dotenv
load_dotenv()

import os
import json
import time

from playwright.sync_api import sync_playwright

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz


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

SHEET_COLUMN_MAP = {
    "BUFFA": "B",
    "SAS ART BUBBLE": "D",
    "SAS LAVSPEED 54": "F",
    "SAS TOP SPEED": "H"
}


#GOOGLE
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_info = json.loads(os.environ["GOOGLE_CREDS"])
creds = Credentials.from_service_account_info(
    creds_info,
    scopes=scopes
)

client = gspread.authorize(creds)
sheet = client.open("Répartition Pièces Banque").worksheet("Collecte")


#FONCTIONS
#récup valeurs
def get_bill_counts(page):
    # cibler la ligne "Billets" qui ouvre la modale
    billets_row = page.locator("div.select-line", has=page.locator("text=Billets")).first
    billets_row.wait_for()
    billets_row.click()

    # attendre que la modale billets soit visible
    page.wait_for_selector("#Cmodal-billets")
    page.wait_for_selector("#CVALEUR-BILLETS-5")
    page.wait_for_selector("#CVALEUR-BILLETS-10")
    page.wait_for_selector("#CVALEUR-BILLETS-20")

    count_5 = page.inner_text("#CVALEUR-BILLETS-5").strip()
    count_10 = page.inner_text("#CVALEUR-BILLETS-10").strip()
    count_20 = page.inner_text("#CVALEUR-BILLETS-20").strip()

    # fermer la modale billets en restant scope dans Cmodal-billets
    page.locator("#Cmodal-billets input.mod-bouton[value='Fermer']").click()

    return {
        "5": count_5,
        "10": count_10,
        "20": count_20
    }

def send_snapshot_to_sheet(data):
    paris = pytz.timezone("Europe/Paris")
    now = datetime.now(paris)

    # format simple pour A1
    timestamp = now.strftime("%d/%m/%Y %H:%M")

    updates = {
        "A1": timestamp
    }

    for laverie_name, bills in data.items():
        col = SHEET_COLUMN_MAP.get(laverie_name)
        if not col:
            continue

        updates[f"{col}2"] = bills.get("5", "")
        updates[f"{col}3"] = bills.get("10", "")
        updates[f"{col}4"] = bills.get("20", "")

    # envoi cellule par cellule
    for cell, value in updates.items():
        sheet.update_acell(cell, value)

    print("Export GSheets terminé :", updates)


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
    
    #loop p chaque etab
    for name, selector in LAVERIES:
        try:
            # revenir au menu si besoin
            if page.url != MENU_URL:
                page.goto(MENU_URL)
                page.wait_for_load_state("networkidle")

            page.wait_for_selector(selector)
            page.click(selector)
            page.wait_for_load_state("networkidle")

            bill_counts = get_bill_counts(page)
            results[name] = bill_counts

            print(name, bill_counts)

        except Exception as e:
            print(f"[ERROR] {name} -> {e}")

        time.sleep(1)

    browser.close()

#send to Gsheets
print("RESULTS:", results)
send_snapshot_to_sheet(results)
