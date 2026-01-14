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
        # WooCommerce Stripe patterns (most specific first)
        r'createAndConfirmSetupIntentNonce["\']?\s*:\s*["\']([^"\']+)["\']',
        r'wc_stripe_create_and_confirm_setup_intent["\']?[^}]*nonce["\']?:\s*["\']([^"\']+)["\']',
        
        # Standard WordPress nonce patterns
        r'name=["\']_ajax_nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']_wpnonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']woocommerce-register-nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']woocommerce-login-nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']nonce["\'][^>]*value=["\']([^"\']+)["\']',
        
        # Data attributes
        r'data-nonce=["\']([^"\']+)["\']',
        r'data-_nonce=["\']([^"\']+)["\']',
        r'data-security=["\']([^"\']+)["\']',
        r'data-nonce-value=["\']([^"\']+)["\']',
        
        # JavaScript variable patterns
        r'var\s+wc_stripe_params\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"',
        r'var\s+stripe_params\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"',
        r'var\s+wc_checkout_params\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"',
        r'wc_stripe_params\s*=\s*\{[^}]*nonce["\']?\s*:\s*["\']([^"\']+)["\']',
        
        # JSON embedded nonces
        r'"nonce"\s*:\s*"([a-zA-Z0-9_-]+)"',
        r"'nonce'\s*:\s*'([a-zA-Z0-9_-]+)'",
        r'"nonce"\s*:\s*"([^"]+)"',
        r'nonce["\']?\s*:\s*["\']([a-zA-Z0-9_-]+)["\']',
        
        # Input fields
        r'<input[^>]*name=["\']nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'<input[^>]*name=["\']_wpnonce["\'][^>]*value=["\']([^"\']+)["\']',
        
        # REST API nonce header patterns
        r'X-WP-Nonce["\']?\s*:\s*["\']([^"\']+)["\']',
        
        # Very generic patterns (catch-all)
        r'nonce["\']?\s*[:=]\s*["\']([a-zA-Z0-9_\-]{10,})["\']',
        r'value=["\']([a-zA-Z0-9_\-]{30,})["\'][^>]*nonce',
        r'nonce["\']?["\']?\s*:\s*["\']([a-zA-Z0-9_\-]+)["\']',
    ]
    
    @staticmethod
    def extract(html_content: str, domain: str = "") -> Optional[str]:
        """Extract nonce from HTML content with comprehensive patterns"""
        if not html_content:
            logger.warning(f"Empty HTML content for domain {domain}")
            return None
        
        nonces_found = []
        
        for i, pattern in enumerate(NonceExtractor.PATTERNS):
            try:
                matches = re.finditer(pattern, html_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    try:
                        nonce = match.group(1).strip()
                        # Validate nonce - be lenient with validation
                        if nonce and 5 <= len(nonce) < 256:
                            # Accept alphanumeric, underscore, hyphen, and common special chars in nonces
                            if re.match(r'^[a-zA-Z0-9_\-+=/.]+$', nonce):
                                if nonce not in nonces_found:
                                    nonces_found.append(nonce)
                                    logger.debug(f"Found nonce via pattern {i}: {nonce[:30]}...")
                                    # Return first valid nonce found
                                    return nonce
                    except (IndexError, AttributeError):
                        continue
            except Exception as e:
                logger.debug(f"Pattern {i} error: {e}")
                continue
        
        if nonces_found:
            logger.debug(f"Found {len(nonces_found)} nonce candidates: {[n[:20] for n in nonces_found[:3]]}")
            return nonces_found[0]
        
        logger.debug(f"No nonce found in {len(html_content)} bytes. Trying fallback extraction...")
        
        # Fallback: try to extract any valid token-like string near "nonce" keyword
        return NonceExtractor._fallback_extract(html_content)
    
    @staticmethod
    def _fallback_extract(html_content: str) -> Optional[str]:
        """Fallback extraction: find any valid nonce-like token with aggressive search"""
        try:
            # Strategy 1: Find all occurrences of word "nonce" and look for nearby quoted values
            nonce_positions = [m.start() for m in re.finditer(r'nonce', html_content, re.IGNORECASE)]
            
            for pos in nonce_positions:
                # Look at surrounding context (300 chars forward)
                start = max(0, pos)
                end = min(len(html_content), pos + 300)
                context = html_content[start:end]
                
                # Try multiple patterns to find quoted value after nonce
                # Pattern 1: quoted strings of various lengths
                for pattern in [
                    r'["\']([a-zA-Z0-9_\-+=/.]{15,})["\']',  # Longer tokens
                    r'["\']([a-zA-Z0-9_\-+=/.]{10,})["\']',  # Medium tokens
                    r'["\']([a-zA-Z0-9_\-]{8,})["\']',       # Short tokens
                    r'value=["\']([^"\']+)["\']',            # HTML input values
                ]:
                    match = re.search(pattern, context)
                    if match:
                        token = match.group(1).strip()
                        if token and 8 <= len(token) < 300:
                            logger.debug(f"Fallback extracted nonce: {token[:30]}...")
                            return token
            
            # Strategy 2: Look for any long string that resembles a token/nonce
            # This catches nonces that aren't explicitly labeled
            potential_tokens = re.findall(r'["\']([a-zA-Z0-9_\-+=/.]{20,})["\']', html_content)
            if potential_tokens:
                # Return longest token (likely to be the real nonce)
                token = max(potential_tokens, key=len)
                if token and not any(x in token.lower() for x in ['href', 'src', 'data:', 'http']):
                    logger.debug(f"Fallback extracted long token: {token[:30]}...")
                    return token
            
            # Strategy 3: Look for base64-like strings (nonces are often base64)
            base64_tokens = re.findall(r'["\']([A-Za-z0-9+/]{20,}={0,2})["\']', html_content)
            if base64_tokens:
                token = base64_tokens[0]
                logger.debug(f"Fallback extracted base64 token: {token[:30]}...")
                return token
        
        except Exception as e:
            logger.debug(f"Fallback extraction error: {e}")
        
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
