# Architecture Overview

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT REQUESTS                             │
│  (API calls via HTTP: /process, /bulk, /debug/*, /health)          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
        ┌───────▼────────────┐       ┌───────▼────────────┐
        │  Flask Application │       │  Debug Endpoints   │
        │     (app.py)       │       │  /debug/nonce      │
        │                    │       │  /debug/config     │
        │  API Routes:       │       │  /debug/session    │
        │  /process          │       └────────────────────┘
        │  /bulk             │
        │  /health           │
        └────────┬───────────┘
                 │
    ┌────────────┴─────────────┐
    │                          │
    │   Stripe Processing      │   Uses Config
    │   (app.py functions)     │   (config.json)
    │   ├─ get_stripe_key()    │   ◄────────────┐
    │   ├─ extract_nonce()     │               │
    │   ├─ register_account()  │   ConfigManager
    │   ├─ process_card()      │   (utils.py)
    │   └─ process_card_async()│   ├─ Load JSON
    │                          │   ├─ Parse config
    │                          │   └─ Provide values
    └────────────┬─────────────┘
                 │
    ┌────────────▼────────────────────────────────────┐
    │         Utility Classes (utils.py)              │
    │                                                 │
    │  ┌──────────────────────────────────────────┐  │
    │  │ HTTPSessionManager                       │  │
    │  │ ├─ ProxyRotator (cycle proxies)         │  │
    │  │ ├─ BrowserFingerprint (realistic UA)    │  │
    │  │ ├─ RetryHandler (exponential backoff)   │  │
    │  │ └─ requests.Session (HTTP client)       │  │
    │  └──────────────────────────────────────────┘  │
    │                                                 │
    │  ┌──────────────────────────────────────────┐  │
    │  │ NonceExtractor                           │  │
    │  │ └─ 16+ regex patterns                    │  │
    │  │    for nonce detection                   │  │
    │  └──────────────────────────────────────────┘  │
    │                                                 │
    │  ┌──────────────────────────────────────────┐  │
    │  │ StripeKeyExtractor                       │  │
    │  │ └─ Extract publishable keys              │  │
    │  └──────────────────────────────────────────┘  │
    │                                                 │
    │  ┌──────────────────────────────────────────┐  │
    │  │ Helper Functions                         │  │
    │  │ ├─ generate_random_credentials()        │  │
    │  │ └─ async utilities                       │  │
    │  └──────────────────────────────────────────┘  │
    └────────────┬─────────────────────────────────┘
                 │
    ┌────────────▼──────────────────────────────┐
    │      External Services/Resources           │
    │                                            │
    │  ┌────────────────────────────────────┐   │
    │  │ Target Websites                    │   │
    │  │ ├─ Extract nonces                  │   │
    │  │ ├─ Get Stripe keys                 │   │
    │  │ ├─ Register accounts               │   │
    │  │ └─ Submit payments                 │   │
    │  └────────────────────────────────────┘   │
    │                                            │
    │  ┌────────────────────────────────────┐   │
    │  │ Stripe API                         │   │
    │  │ └─ api.stripe.com/v1/payment_...  │   │
    │  └────────────────────────────────────┘   │
    │                                            │
    │  ┌────────────────────────────────────┐   │
    │  │ Proxy Servers (Optional)           │   │
    │  │ └─ Rotate IPs to avoid blocking    │   │
    │  └────────────────────────────────────┘   │
    └────────────────────────────────────────────┘
```

## Data Flow - Single Card Processing

```
Client Request
    │
    ▼
/process?key=inferno&site=example.com&cc=...
    │
    ▼
Validate Input
├─ Check API key
├─ Check domain format
└─ Check card format
    │
    ▼
Get Stripe Key
├─ Create HTTPSessionManager
│  ├─ BrowserFingerprint (realistic headers)
│  ├─ ProxyRotator (select proxy)
│  └─ RetryHandler (retry strategy)
├─ Try multiple payment URLs
└─ StripeKeyExtractor (extract pk_live_*)
    │
    ▼
Register Account (optional)
├─ GET /my-account/
├─ Extract registration nonce
├─ Generate credentials
└─ POST registration
    │
    ▼
Get Nonce for Payment
├─ Try multiple payment URLs
├─ NonceExtractor with 16+ patterns
└─ Validate nonce (5-256 chars)
    │
    ▼
Create Payment Method
├─ POST to api.stripe.com/v1/payment_methods
├─ Send card data + fake fingerprint
└─ Get payment_method_id
    │
    ▼
Confirm Payment
├─ Build AJAX payload (template from config)
├─ Substitute payment_method_id and nonce
├─ POST to target site AJAX endpoint
└─ Parse response
    │
    ▼
Return Result
├─ "Status": "Approved" or "Declined"
└─ "Response": Details message
```

## Data Flow - Bulk Card Processing

```
Client Request: /bulk?key=inferno&cc=...
    │
    ▼
Validate Input (API key, card format)
    │
    ▼
Load Test Domains from config.json
    │
    ▼
Create ThreadPoolExecutor (5 workers)
    │
    ├─ Worker 1: Process domain 1
    ├─ Worker 2: Process domain 2
    ├─ Worker 3: Process domain 3
    │ ... (parallel execution)
    │
    ▼ (all workers run simultaneously)
│
├─ Each worker:
│  ├─ Get Stripe key
│  ├─ Extract nonce
│  ├─ Create payment method
│  ├─ Confirm payment
│  └─ Collect result
│
    ▼
Aggregate Results
    │
    ▼
Return Combined Results
{
  "results": [
    {"Domain": "...", "Response": "...", "Status": "..."},
    ...
  ]
}
```

## Request Flow with Retry Logic

```
Original Request
    │
    ▼
RetryHandler.retry_with_backoff()
    │
    ├─ Attempt 1
    │   ├─ ProxyRotator selects proxy
    │   ├─ BrowserFingerprint creates headers
    │   ├─ Send request with timeout
    │   └─ Exception? ──┐
    │                  │
    ├─ Attempt 2       │
    │   ├─ Calculate delay (1 * 2 = 2 sec)
    │   ├─ Sleep 2 seconds
    │   ├─ ProxyRotator selects next proxy
    │   ├─ Send request
    │   └─ Exception? ──┐
    │                  │
    ├─ Attempt 3       │
    │   ├─ Calculate delay (2 * 2 = 4 sec)
    │   ├─ Sleep 4 seconds
    │   ├─ ProxyRotator selects next proxy
    │   ├─ Send request
    │   └─ Exception? ──┐
    │                  │
    ├─ Attempt 4       │
    │   ├─ Calculate delay (4 * 2 = 8 sec, capped at 10)
    │   ├─ Sleep 8 seconds
    │   ├─ ProxyRotator selects next proxy
    │   └─ Send request
    │
    ▼
Success or Final Failure
```

## Configuration Hierarchy

```
config.json (User configuration)
    │
    ▼
ConfigManager
├─ Load and parse JSON
├─ Provide defaults if missing
├─ Support dot notation access
└─ Cache values
    │
    ├─ app.py initialization
    │   ├─ proxy_rotator = ProxyRotator(config["proxy_list"], ...)
    │   ├─ fingerprint = BrowserFingerprint(config["user_agents"])
    │   ├─ retry_handler = RetryHandler(**config["retry_config"])
    │   └─ http_session_manager = HTTPSessionManager(...)
    │
    └─ Processing functions
        ├─ process_card_enhanced() uses config["payment_urls"]
        ├─ register_account() uses config values
        ├─ bulk endpoint uses config["test_domains"]
        └─ AJAX payloads use config["ajax_payloads"]
```

## Class Relationships

```
HTTPSessionManager (Main coordinator)
├─ Uses ProxyRotator
│  └─ Provides proxy for each request
├─ Uses BrowserFingerprint
│  └─ Provides headers for each request
└─ Uses RetryHandler
   └─ Implements retry logic for requests

NonceExtractor (Static utility)
└─ 16+ regex patterns
   └─ Extract from HTML

StripeKeyExtractor (Static utility)
└─ Multiple regex patterns
   └─ Extract from HTML

ConfigManager (Singleton pattern)
└─ Loads config.json
   └─ Provides values to all modules

Processing Functions
├─ Use HTTPSessionManager for requests
├─ Use NonceExtractor for nonces
├─ Use StripeKeyExtractor for keys
└─ Use ConfigManager for settings
```

## Concurrency Model

```
Single Request Flow (/process endpoint)
├─ Main thread handles Flask request
├─ Creates HTTPSessionManager
└─ Executes sequentially
   ├─ Get Stripe key
   ├─ Extract nonce
   ├─ Create payment method
   └─ Confirm payment

Bulk Request Flow (/bulk endpoint)
├─ Main thread handles Flask request
├─ Creates ThreadPoolExecutor (5 workers)
├─ Submits tasks for all domains
└─ Each worker thread:
   ├─ Creates own HTTPSessionManager
   ├─ Executes domain processing
   ├─ Reports result back
   └─ Worker thread completes
└─ Main thread aggregates results
```

## Error Handling Strategy

```
Any Network Error (Timeout, Connection)
    │
    ▼
RetryHandler.retry_with_backoff()
    │
    ├─ Calculate exponential backoff
    ├─ Sleep appropriate time
    ├─ Select new proxy (if rotation enabled)
    ├─ Try again
    │
    └─ After max_retries attempts
        │
        ▼
    Raise Exception
        │
        ├─ In process_card_enhanced()
        │   └─ Return {"Status": "Declined", "Response": error_msg}
        │
        └─ In /process endpoint
            └─ Return {"error": ..., "status": 500}
```

## Security & Evasion Strategy

```
Bot Detection Evasion
├─ Header Spoofing (BrowserFingerprint)
│  ├─ Realistic User-Agent
│  ├─ Accept-Language
│  ├─ Sec-Fetch headers
│  └─ Cache-Control headers
├─ IP Rotation (ProxyRotator)
│  ├─ Rotate through proxy pool
│  ├─ Avoid single IP blocking
│  └─ Distribute requests
├─ Request Timing
│  ├─ Variable delays with exponential backoff
│  ├─ Avoid suspicious timing patterns
│  └─ Human-like request frequency
└─ Behavior Simulation
   ├─ Follow redirects
   ├─ Keep cookies (session)
   ├─ Realistic referrer patterns
   └─ Accept standard response codes
```

## Performance Considerations

```
Bulk Processing Optimization

Sequential (Before):
request 1 → ████ wait ████ → result 1
request 2 → ████ wait ████ → result 2
request 3 → ████ wait ████ → result 3
Total: 60 seconds

Parallel (After):
request 1 → ████ wait ████ ┐
request 2 → ████ wait ████ ├─ all simultaneous
request 3 → ████ wait ████ ┘
Total: ~20 seconds (3x faster!)

Benefits:
├─ Better resource utilization
├─ Faster overall completion
├─ Scales with worker count
└─ Configurable concurrency level
```

