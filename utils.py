"""
Advanced HTTP and Stripe processing utilities with proxy rotation, fingerprinting, and retries
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as URLRetry
from fake_useragent import UserAgent
import uuid
import time
import re
import json
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, List, Tuple
import random
import string

logger = logging.getLogger(__name__)


class ConfigManager:
    """Loads and manages configuration from JSON"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            return self._default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return self._default_config()
    
    def _default_config(self) -> dict:
        """Return default configuration"""
        return {
            "proxy_list": [],
            "enable_proxy_rotation": False,
            "retry_config": {
                "max_retries": 3,
                "initial_delay": 1,
                "max_delay": 10,
                "backoff_factor": 2
            },
            "payment_urls": [
                "/my-account/add-payment-method/",
                "/checkout/",
                "/my-account/",
                "/wp-admin/admin-ajax.php",
                "/"
            ],
            "ajax_payloads": [
                {
                    "action": "wc_stripe_create_and_confirm_setup_intent",
                    "fields": {
                        "wc-stripe-payment-method": "payment_method_id",
                        "wc-stripe-payment-type": "card",
                        "_ajax_nonce": "nonce"
                    }
                },
                {
                    "action": "wc_stripe_create_setup_intent",
                    "fields": {
                        "payment_method_id": "payment_method_id",
                        "_wpnonce": "nonce"
                    }
                }
            ],
            "test_domains": [],
            "user_agents": []
        }
    
    def get(self, key: str, default=None):
        """Get config value with dot notation support"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default


class ProxyRotator:
    """Manages proxy rotation and selection"""
    
    def __init__(self, proxy_list: List[str] = None, enable_rotation: bool = False):
        self.proxy_list = proxy_list or []
        self.enable_rotation = enable_rotation
        self.current_index = 0
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Get next proxy in rotation"""
        if not self.enable_rotation or not self.proxy_list:
            return None
        
        proxy = self.proxy_list[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxy_list)
        
        return {
            'http': proxy,
            'https': proxy
        }
    
    def add_proxy(self, proxy: str):
        """Add proxy to rotation list"""
        if proxy not in self.proxy_list:
            self.proxy_list.append(proxy)


class BrowserFingerprint:
    """Generates realistic browser fingerprints"""
    
    def __init__(self, custom_user_agents: List[str] = None):
        self.user_agent_gen = UserAgent()
        self.custom_user_agents = custom_user_agents or []
    
    def get_user_agent(self) -> str:
        """Get a user agent string"""
        if self.custom_user_agents:
            return random.choice(self.custom_user_agents)
        return self.user_agent_gen.random
    
    def get_headers(self) -> Dict[str, str]:
        """Generate realistic browser headers"""
        user_agent = self.get_user_agent()
        
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
        
        # Add browser-specific headers
        if 'Chrome' in user_agent:
            headers['Sec-CH-UA'] = '"Not_A Brand";v="8", "Chromium";v="120"'
            headers['Sec-CH-UA-Mobile'] = '?0'
            headers['Sec-CH-UA-Platform'] = '"Windows"'
        
        return headers
    
    def get_stripe_headers(self, domain: str = "stripe.com") -> Dict[str, str]:
        """Generate headers for Stripe API calls"""
        headers = self.get_headers()
        headers.update({
            'Origin': f'https://js.stripe.com',
            'Referer': f'https://js.stripe.com/',
            'Content-Type': 'application/x-www-form-urlencoded',
        })
        return headers


class RetryHandler:
    """Handles retry logic with exponential backoff"""
    
    def __init__(self, max_retries: int = 3, initial_delay: float = 1, 
                 max_delay: float = 10, backoff_factor: float = 2):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff"""
        delay = self.initial_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)
    
    def retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with retry logic"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (requests.exceptions.Timeout, 
                    requests.exceptions.ConnectionError,
                    requests.exceptions.RequestException) as e:
                last_exception = e
                
                if attempt < self.max_retries - 1:
                    delay = self.calculate_delay(attempt)
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"All {self.max_retries} attempts failed: {e}")
        
        raise last_exception


class HTTPSessionManager:
    """Manages HTTP sessions with retry strategy and proxies"""
    
    def __init__(self, proxy_rotator: ProxyRotator = None, 
                 fingerprint: BrowserFingerprint = None,
                 retry_handler: RetryHandler = None):
        self.proxy_rotator = proxy_rotator or ProxyRotator()
        self.fingerprint = fingerprint or BrowserFingerprint()
        self.retry_handler = retry_handler or RetryHandler()
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy"""
        session = requests.Session()
        
        # Configure retries
        retry_strategy = URLRetry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            backoff_factor=1
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers
        session.headers.update(self.fingerprint.get_headers())
        
        return session
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with proxy and retry"""
        kwargs['proxies'] = self.proxy_rotator.get_proxy()
        kwargs['verify'] = False
        kwargs['timeout'] = kwargs.get('timeout', 15)
        
        return self.retry_handler.retry_with_backoff(self.session.get, url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with proxy and retry"""
        kwargs['proxies'] = self.proxy_rotator.get_proxy()
        kwargs['verify'] = False
        kwargs['timeout'] = kwargs.get('timeout', 15)
        
        return self.retry_handler.retry_with_backoff(self.session.post, url, **kwargs)
    
    def close(self):
        """Close the session"""
        self.session.close()


class NonceExtractor:
    """Advanced nonce extraction with support for complex HTML structures"""
    
    # Comprehensive pattern list
    PATTERNS = [
        # WooCommerce Stripe patterns
        r'createAndConfirmSetupIntentNonce["\']?\s*:\s*["\']([^"\']+)["\']',
        r'wc_stripe_create_and_confirm_setup_intent["\']?[^}]*nonce["\']?:\s*["\']([^"\']+)["\']',
        
        # Standard WordPress nonce patterns
        r'name=["\']_ajax_nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']_wpnonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']woocommerce-register-nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']woocommerce-login-nonce["\'][^>]*value=["\']([^"\']+)["\']',
        
        # Data attributes
        r'data-nonce=["\']([^"\']+)["\']',
        r'data-_nonce=["\']([^"\']+)["\']',
        r'data-security=["\']([^"\']+)["\']',
        
        # JavaScript variable patterns
        r'var\s+wc_stripe_params\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"',
        r'var\s+stripe_params\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"',
        r'var\s+wc_checkout_params\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"',
        
        # Generic nonce patterns (more flexible)
        r'nonce["\']?\s*:\s*["\']([a-zA-Z0-9]+)["\']',
        r'"nonce"\s*:\s*"([a-zA-Z0-9]+)"',
        r"'nonce'\s*:\s*'([a-zA-Z0-9]+)'",
        
        # REST API nonce header patterns
        r'X-WP-Nonce["\']?\s*:\s*["\']([^"\']+)["\']',
    ]
    
    @staticmethod
    def extract(html_content: str, domain: str = "") -> Optional[str]:
        """Extract nonce from HTML content"""
        if not html_content:
            logger.warning(f"Empty HTML content for domain {domain}")
            return None
        
        for i, pattern in enumerate(NonceExtractor.PATTERNS):
            try:
                match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
                if match:
                    nonce = match.group(1).strip()
                    # Validate nonce
                    if nonce and 5 <= len(nonce) < 256:
                        logger.debug(f"Found nonce using pattern {i}: {nonce[:20]}...")
                        return nonce
            except Exception as e:
                logger.debug(f"Pattern {i} error: {e}")
                continue
        
        logger.debug(f"No nonce found. HTML preview: {html_content[:500]}")
        return None
    
    @staticmethod
    def extract_multiple_from_forms(html_content: str) -> Dict[str, str]:
        """Extract nonces from multiple forms"""
        nonces = {}
        
        # Extract from form inputs
        form_pattern = r'<form[^>]*>(.*?)</form>'
        forms = re.findall(form_pattern, html_content, re.IGNORECASE | re.DOTALL)
        
        for i, form in enumerate(forms):
            nonce = NonceExtractor.extract(form)
            if nonce:
                nonces[f"form_{i}"] = nonce
        
        return nonces


class StripeKeyExtractor:
    """Extracts Stripe publishable keys"""
    
    PATTERNS = [
        r'pk_live_[a-zA-Z0-9_]+',
        r'stripe_params[^}]*"key":"(pk_live_[^"]+)"',
        r'wc_stripe_params[^}]*"key":"(pk_live_[^"]+)"',
        r'"publishableKey":"(pk_live_[^"]+)"',
        r'var stripe = Stripe[\'"]((pk_live_[^\'"]+))[\'"]',
    ]
    
    @staticmethod
    def extract(html_content: str) -> Optional[str]:
        """Extract Stripe key from HTML"""
        if not html_content:
            return None
        
        for pattern in StripeKeyExtractor.PATTERNS:
            try:
                match = re.search(pattern, html_content)
                if match:
                    key_match = re.search(r'pk_live_[a-zA-Z0-9_]+', match.group(0))
                    if key_match:
                        key = key_match.group(0)
                        logger.debug(f"Found Stripe key: {key}")
                        return key
            except Exception as e:
                logger.debug(f"Error extracting Stripe key: {e}")
                continue
        
        return None


def generate_random_credentials() -> Tuple[str, str, str]:
    """Generate random registration credentials"""
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email = f"{username}@gmail.com"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    return username, email, password


async def async_fetch(session: aiohttp.ClientSession, url: str, **kwargs) -> Tuple[int, str]:
    """Async HTTP GET"""
    try:
        async with session.get(url, **kwargs) as response:
            text = await response.text()
            return response.status, text
    except Exception as e:
        logger.error(f"Async fetch error for {url}: {e}")
        return 0, ""


async def async_post(session: aiohttp.ClientSession, url: str, **kwargs) -> Tuple[int, Dict]:
    """Async HTTP POST"""
    try:
        async with session.post(url, **kwargs) as response:
            data = await response.json()
            return response.status, data
    except Exception as e:
        logger.error(f"Async post error for {url}: {e}")
        return 0, {}
