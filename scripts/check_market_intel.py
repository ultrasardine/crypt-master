#!/usr/bin/env python
"""Check market intelligence data."""

import httpx
from bs4 import BeautifulSoup


def main():
    base_url = "http://localhost:14800"
    
    with httpx.Client(follow_redirects=True) as client:
        # Login
        resp = client.get(f"{base_url}/accounts/login/")
        soup = BeautifulSoup(resp.text, "html.parser")
        csrf = soup.find("input", {"name": "csrfmiddlewaretoken"})
        client.post(f"{base_url}/accounts/login/", data={
            "csrfmiddlewaretoken": csrf["value"] if csrf else "",
            "username": "admin",
            "password": "admin123",
        })
        
        # Check regimes page in detail
        resp = client.get(f"{base_url}/analysis/regimes/")
        soup = BeautifulSoup(resp.text, "html.parser")
        print("=== REGIMES PAGE ===")
        main = soup.find("main") or soup.body
        if main:
            for elem in main.find_all(["h1", "h2", "h3", "p", "span", "div"])[:30]:
                text = elem.get_text(strip=True)[:100]
                if text and len(text) > 5:
                    print(f"  {text}")
        
        # Check API for market context
        print("\n=== API: Market Context ===")
        resp = client.get(f"{base_url}/api/market-context/")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"Data: {data}")
            except Exception:
                print(f"Response: {resp.text[:500]}")
        else:
            print(f"Response: {resp.text[:200]}")
        
        # Check API for snapshots
        print("\n=== API: Snapshots ===")
        resp = client.get(f"{base_url}/api/market-context-snapshots/")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list):
                    print(f"Snapshots count: {len(data)}")
                    if data:
                        print(f"Latest: {data[0]}")
                else:
                    print(f"Data: {data}")
            except Exception:
                print(f"Response: {resp.text[:500]}")


if __name__ == "__main__":
    main()
