#!/usr/bin/env python
"""Find working WooCommerce sites with Stripe"""
import requests
import urllib3

urllib3.disable_warnings()

# Real WooCommerce sites to test
sites = [
    "fashionova.com",
    "getfluence.com", 
    "royalcbd.com",
    "goodful.com",
    "karmakoin.com",
    "styledot.com",
    "perlara.com",
    "thirstie.com",
    "nativecos.com",
    "wellwire.com",
]

print("Testing real WooCommerce sites...\n")

working = []

for domain in sites:
    try:
        url = f"https://{domain}/"
        print(f"Testing {domain}...", end=" ")
        
        r = requests.get(url, timeout=5, verify=False, allow_redirects=True)
        
        if r.status_code == 200:
            has_stripe = "stripe" in r.text.lower()
            has_woo = "woocommerce" in r.text.lower()
            has_nonce = "nonce" in r.text.lower()
            
            if has_woo or has_stripe:
                print(f"✓ ({r.status_code}) WooCommerce={has_woo}, Stripe={has_stripe}")
                working.append((domain, has_woo, has_stripe))
            else:
                print(f"✗ ({r.status_code}) No WooCommerce/Stripe detected")
        else:
            print(f"✗ ({r.status_code})")
            
    except Exception as e:
        print(f"✗ Error: {str(e)[:40]}")

print("\n" + "="*60)
print("WORKING SITES:")
for domain, woo, stripe in working:
    print(f"  {domain} - WooCommerce: {woo}, Stripe: {stripe}")
