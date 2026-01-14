#!/usr/bin/env python
"""Quick test of real WooCommerce sites"""
import requests
import urllib3

urllib3.disable_warnings()

# Real working WooCommerce + Stripe sites
sites = [
    ("bookandpencil.com", "https://bookandpencil.com/checkout/"),
    ("demo.woocommerce.com", "https://demo.woocommerce.com/my-account/add-payment-method/"),
    ("store.woocommerce.com", "https://store.woocommerce.com/shop/"),
]

print("Testing sites for Stripe integration...")
print("=" * 60)

for domain, url in sites:
    print(f"\nDomain: {domain}")
    print(f"URL: {url}")
    
    try:
        r = requests.get(url, timeout=5, verify=False, allow_redirects=True)
        print(f"Status: {r.status_code}")
        print(f"Size: {len(r.text)} bytes")
        
        # Quick checks
        has_stripe = "stripe" in r.text.lower()
        has_nonce = "nonce" in r.text.lower()
        has_woo = "woocommerce" in r.text.lower()
        
        print(f"Stripe: {has_stripe}, Nonce: {has_nonce}, WooCommerce: {has_woo}")
        
    except Exception as e:
        print(f"Error: {str(e)[:50]}")

print("\n" + "=" * 60)
print("Use the one with all indicators: True")
