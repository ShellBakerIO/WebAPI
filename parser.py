import time
import requests
from bs4 import BeautifulSoup

base_url = 'https://www.maxidom.ru/catalog/smesiteli-dlya-dusha/'


def parse_category():
    page_number = 1
    has_next_page = True
    parsed_items = []

    while has_next_page:
        print(f"Парсинг страницы {page_number}...")

        url = f"{base_url}?amount=30&PAGEN_2={page_number}"
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "lxml")

        products = soup.select('div.lvl1__product-body-info-code span')
        for product in products:
            product_id = int(product.get_text(strip=True))
            product_url = f"{base_url}{product_id}"
            product_response = requests.get(product_url)
            product_soup = BeautifulSoup(product_response.content, "lxml")

            product_name = product_soup.find('div', class_='flypage__header-mobile').find('p').get_text(strip=True)
            product_price = int(product_soup.find('div', class_='lvl1__product-body-buy-price-base')['data-repid_price'])

            parsed_items.append({
                "id": product_id,
                "name": product_name,
                "price": product_price,
            })

        has_next_page = bool(soup.select_one('i.lvl2__content-nav-numbers-next'))
        if not has_next_page:
            break

        page_number += 1
        time.sleep(1)

    print("Парсинг окончен")
    return parsed_items
