#!/usr/bin/env python
"""Test real WooCommerce sites with Stripe integration"""
import requests
import urllib3
import re
from utils import NonceExtractor, StripeKeyExtractor

urllib3.disable_warnings()

# Real WooCommerce sites to test
test_sites = [
    'woostify.com',
    'demo.woothemes.com',
    'bookandpencil.com',
    'scandinavia-furniture.myshopify.com'
]

print("=" * 80)
print("WOOCOMMERCE STRIPE INTEGRATION TEST")
print("=" * 80)

for domain in test_sites:
    print(f"\n[TEST] Domain: {domain}")
    print("-" * 80)
    
    urls_to_test = [
        f'https://{domain}/my-account/add-payment-method/',
        f'https://{domain}/checkout/',
        f'https://{domain}/my-account/'
    ]
    
    for url in urls_to_test:
        try:
            print(f"\n  Trying: {url}")
            response = requests.get(url, timeout=10, verify=False, allow_redirects=True)
            
            if response.status_code == 200:
                html = response.text
                print(f"  ✓ Status: {response.status_code}")
                print(f"  ✓ Content Length: {len(html):,} bytes")
                
                # Extract nonce
                nonce = NonceExtractor.extract(html, domain)
                if nonce:
                    print(f"  ✓ NONCE FOUND: {nonce[:50]}...")
                else:
                    print(f"  ✗ No nonce found")
                
                # Extract Stripe key
                stripe_key = StripeKeyExtractor.extract(html)
                if stripe_key:
                    print(f"  ✓ STRIPE KEY FOUND: {stripe_key[:40]}...")
                else:
                    print(f"  ✗ No Stripe key found")
                
                # Check for payment forms
                if 'stripe' in html.lower():
                    print(f"  ✓ Stripe references found in HTML")
                if 'woocommerce' in html.lower():
                    print(f"  ✓ WooCommerce detected")
                
                # Found good site, stop testing URLs
                if nonce and stripe_key:
                    print(f"\n  ✅ READY FOR PAYMENT TEST!")
                    break
            else:
                print(f"  ✗ Status: {response.status_code}")
                
        except requests.Timeout:
            print(f"  ✗ Timeout")
        except requests.ConnectionError:
            print(f"  ✗ Connection error")
        except Exception as e:
            print(f"  ✗ Error: {str(e)[:100]}")

print("\n" + "=" * 80)
print("Test complete!")
print("=" * 80)
