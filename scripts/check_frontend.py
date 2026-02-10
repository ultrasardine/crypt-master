#!/usr/bin/env python
"""Script to check frontend data using httpx and BeautifulSoup."""

import httpx
from bs4 import BeautifulSoup


def main():
    base_url = "http://localhost:14800"
    
    with httpx.Client(follow_redirects=True) as client:
        # Login
        login_url = f"{base_url}/accounts/login/"
        resp = client.get(login_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        csrf_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
        csrf_token = csrf_input["value"] if csrf_input else ""
        
        login_data = {
            "csrfmiddlewaretoken": csrf_token,
            "username": "admin",
            "password": "admin123",
        }
        resp = client.post(login_url, data=login_data)
        print(f"Login status: {resp.status_code}")
        
        # Check dashboard
        resp = client.get(base_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.find("title")
        print(f"\n=== Dashboard ===")
        print(f"Title: {title.text.strip() if title else 'N/A'}")
        
        # Find key stats
        stats = soup.find_all("div", class_="stat-card")
        for stat in stats[:5]:
            label = stat.find("span", class_="stat-label")
            value = stat.find("span", class_="stat-value")
            if label and value:
                print(f"  {label.text.strip()}: {value.text.strip()}")
        
        # Check signals page
        resp = client.get(f"{base_url}/trading/signals/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print(f"\n=== Signals Page ===")
        table = soup.find("table")
        if table:
            rows = table.find_all("tr")
            print(f"Signal rows: {len(rows) - 1}")  # minus header
            for row in rows[1:4]:  # First 3 signals
                cells = row.find_all("td")
                if cells:
                    print(f"  {' | '.join(c.text.strip()[:20] for c in cells[:4])}")
        
        # Check bots page
        resp = client.get(f"{base_url}/bots/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print(f"\n=== Bots Page ===")
        bot_cards = soup.find_all("div", class_="bot-card")
        print(f"Bot cards found: {len(bot_cards)}")
        
        # Check regimes page
        resp = client.get(f"{base_url}/analysis/regimes/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print(f"\n=== Regimes Page ===")
        print(f"Status: {resp.status_code}")
        regime_info = soup.find("div", class_="regime")
        if regime_info:
            print(f"Regime info: {regime_info.text.strip()[:100]}")
        
        # Check signal quality page
        resp = client.get(f"{base_url}/analysis/signal-quality/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print(f"\n=== Signal Quality Page ===")
        print(f"Status: {resp.status_code}")


if __name__ == "__main__":
    main()
