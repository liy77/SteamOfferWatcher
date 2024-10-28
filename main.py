import json
import os
import locale
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

CHECK_INTERVAL = 120  # Time interval between checks in seconds

# Selenium configuration with Chrome
chrome_options = Options()
chrome_options.add_argument("--headless")  # Runs Chrome in headless mode (no GUI)
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Locale configuration for currency formatting
locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')

OFFERS_FILE = "offers.json"

def load_offers():
    # Load offers from file if exists
    if not os.path.exists(OFFERS_FILE):
        return {}
    with open(OFFERS_FILE, 'r') as file:
        return json.load(file)

def save_offers(offers):
    # Save offers to file
    with open(OFFERS_FILE, 'w') as file:
        json.dump(offers, file)

def fetch_games_from_search(start):
    # Initialize Chrome driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    url = f"https://store.steampowered.com/search/results/?query&start={start}&count=100&infinite=1"
    driver.get(url)
    time.sleep(2)  # Wait to ensure content is loaded

    # Extract JSON from the response (the "results_html" field contains the HTML with games)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()

    try:
        data = json.loads(soup.text)  # Load JSON with "results_html"
        results_html = data.get('results_html', '')  # Extract HTML from the results
        soup = BeautifulSoup(results_html, 'html.parser')  # Parse games HTML
    except json.JSONDecodeError:
        print("Error loading JSON.")
        return []

    # Extract game data from HTML
    games = []
    for game in soup.select('.search_result_row'):
        # Check if game has 'data-ds-appid' attribute
        app_id = game.get('data-ds-appid')
        if not app_id:
            continue  # Ignore items without 'data-ds-appid'

        name = game.select_one('.title').get_text()
        
        # Get discount percentage
        discount_tag = game.select_one('.discount_pct')
        discount = int(discount_tag.get_text(strip=True).replace('-', '').replace('%', '')) if discount_tag else 0
        
        # Get original price (before discount)
        original_price = 0.0
        original_price_tag = game.select_one('.discount_original_price')
        if original_price_tag:
            original_price_text = original_price_tag.get_text(strip=True).replace('R$', '').replace('.', '').replace(',', '.')
            original_price = float(original_price_text)

        # Get final price (after discount or normal price)
        final_price = 0.0
        final_price_tag = game.select_one('.discount_final_price')
        if final_price_tag:
            final_price_text = final_price_tag.get_text(strip=True).replace('R$', '').replace('.', '').replace(',', '.')
            # Check if the final price is "Free"
            if final_price_text.lower() == "gratuito":
                final_price = 0.0
            else:
                final_price = float(final_price_text) if final_price_text else 0.0

        games.append({
            'id': app_id,
            'name': name,
            'discount_percent': discount,
            'price_overview': {
                'initial': original_price * 100,  # Represent in cents
                'final': final_price * 100,       # Represent in cents
            }
        })

    print(f"🔍 Found {len(games)} games on page {start // 100 + 1}")
    return games

def process_game(app_data, offers_published):
    app_id = app_data['id']
    name = app_data['name']
    print(f"🕹️ Processing {name}({app_id})")

    price_overview = app_data.get('price_overview', {})
    discount = int(app_data.get('discount_percent', 0))
    initial_price = price_overview.get('initial', 0) / 100
    final_price = price_overview.get('final', 0) / 100

    # Check if discount and price meet criteria
    if discount > 0 and initial_price >= 100:
        final_price_formatted = locale.currency(final_price, grouping=True)
        last_offer = offers_published.get(app_id)

        if last_offer != final_price:
            offers_published[app_id] = final_price
            message = (
                f"🎮 {name} is on sale!\n"
                f"💸 {discount}% discount!\n"
                f"🏷️ {final_price_formatted} instead of {locale.currency(initial_price, grouping=True)}\n"
                f"🔗 Link: https://store.steampowered.com/app/{app_id}"
            )
            print(message)

def check_steam_discounts():
    offers_published = load_offers()
    start = 0
    has_more_results = True

    while has_more_results:
        search_results = fetch_games_from_search(start)
        
        if search_results:
            for app in search_results:
                process_game(app, offers_published)

            # Move to the next page and add a small delay
            start += 100
            has_more_results = len(search_results) == 100
            time.sleep(1)  # 1-second delay between requests
        else:
            has_more_results = False

    save_offers(offers_published)

def start():
    while True:
        print("🔄 Starting Steam discount check...")
        check_steam_discounts()  # Run the discount check
        print(f"✅ Check completed. Waiting {CHECK_INTERVAL // 60} minutes for the next check.")
        time.sleep(CHECK_INTERVAL)  # Pause until next execution

# Start continuous execution
start()
