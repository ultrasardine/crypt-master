#!/usr/bin/env python
"""Detailed frontend check."""

import httpx
from bs4 import BeautifulSoup


def main():
    base_url = "http://localhost:14800"
    
    with httpx.Client(follow_redirects=True) as client:
        # Login
        login_url = f"{base_url}/accounts/login/"
        resp = client.get(login_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        csrf = soup.find("input", {"name": "csrfmiddlewaretoken"})
        csrf_token = csrf["value"] if csrf else ""
        
        client.post(login_url, data={
            "csrfmiddlewaretoken": csrf_token,
            "username": "admin",
            "password": "admin123",
        })
        
        # Dashboard details
        resp = client.get(base_url)
        soup = BeautifulSoup(resp.text, "html.parser")
        print("=== DASHBOARD ===")
        
        # Get all text content from main area
        main = soup.find("main") or soup.find("div", class_="container")
        if main:
            # Find cards/stats
            cards = main.find_all(["div"], class_=lambda x: x and ("card" in x or "stat" in x))
            for card in cards[:10]:
                text = " ".join(card.stripped_strings)[:80]
                if text:
                    print(f"  {text}")
        
        # Recent signals on dashboard
        signals_section = soup.find(string=lambda t: t and "signal" in t.lower())
        if signals_section:
            parent = signals_section.find_parent("div")
            if parent:
                print(f"\nSignals section found")
        
        # Analysis page
        resp = client.get(f"{base_url}/analysis/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print("\n=== ANALYSIS ===")
        main = soup.find("main") or soup.body
        if main:
            for elem in main.find_all(["h1", "h2", "h3", "p"])[:10]:
                text = elem.get_text(strip=True)[:60]
                if text:
                    print(f"  {text}")
        
        # Profile page
        resp = client.get(f"{base_url}/profile/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print("\n=== PROFILE ===")
        print(f"Status: {resp.status_code}")
        user_info = soup.find_all(["dt", "dd"])
        for i in range(0, min(len(user_info), 8), 2):
            if i + 1 < len(user_info):
                label = user_info[i].get_text(strip=True)
                value = user_info[i + 1].get_text(strip=True)[:30]
                print(f"  {label}: {value}")


if __name__ == "__main__":
    main()
