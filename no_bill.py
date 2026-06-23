from dotenv import load_dotenv
load_dotenv()

import os

import requests

from playwright.sync_api import sync_playwright

from datetime import datetime, timedelta
import pytz
import time

paris = pytz.timezone("Europe/Paris")
now = datetime.now(paris)

    
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


#FONCTIONS
#lecture historique
def get_last_bill_event(page):
    page.wait_for_selector("#historique")

    events = page.locator(".item-machine")

    for i in range(events.count()):

        event = events.nth(i)

        text = event.inner_text()

        if "Insertion d'un billet" not in text:
            continue

        date_block = event.locator("div.left").nth(0).inner_text()

        lines = [x.strip() for x in date_block.splitlines() if x.strip()]

        hour_str = lines[0].replace("h", ":")
        day_str = lines[1].lower()

        now = datetime.now(paris)

        if "aujourd" in day_str:
            event_date = now.date()

        elif "hier" in day_str:
            event_date = (now - timedelta(days=1)).date()

        else:
            return None

        return paris.localize(
            datetime.combine(
                event_date,
                datetime.strptime(hour_str, "%H:%M").time()
            )
        )

    return None


#alertes telegram
def telegram_alert(message):
    token = os.environ["TG_TOKEN"]
    chat_id = os.environ["TG_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.get(url, params={
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
    
    
    #loop p chaque etab
    for name, selector in LAVERIES:

        if page.url != MENU_URL:
            page.goto(MENU_URL)

        page.wait_for_selector(selector)
        page.click(selector)

        try:
            page.wait_for_load_state("networkidle")

            page.click('a[href*="historique.php"]')

            last_bill = get_last_bill_event(page)

            now = datetime.now(paris)

            if last_bill is None:

                telegram_alert(
                    f"⚠️ {name}\n"
                    f"Aucune billet trouvé dans l'historique.\n"
                    f"Vérifier si lecteur fonctionne."
                )

            else:

                age_hours = (now - last_bill).total_seconds() / 3600

                print(
                    f"{name} - dernier billet : "
                    f"{last_bill.strftime('%d/%m %H:%M')} "
                    f"({age_hours:.1f} h)"
                )

                if age_hours > 24:

                    telegram_alert(
                        f"⚠️ {name}\n"
                        f"Aucun billet depuis plus de 24 h.\n"
                        f"Dernier billet : {last_bill.strftime('%d/%m à %H:%M')}."
                    )

        except Exception as e:
            print(f"[ERROR] {name} -> {e}")

        time.sleep(1)


