# Quick Start Guide

## Installation

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure your settings** (optional):
Edit `config.json` to customize:
- Proxy servers
- User agents
- Payment URLs
- AJAX payloads
- Test domains

## Running the Application

### Development
```bash
python app.py
```
Server will start at `http://localhost:8000`

### Production
```bash
gunicorn app:app --bind 0.0.0.0:8000 --workers 4
```

## Basic Usage

### 1. Single Card Check
```bash
curl "http://localhost:8000/process?key=inferno&site=example.com&cc=4242424242424242|12|25|123"
```

### 2. Bulk Card Check (Concurrent)
```bash
curl "http://localhost:8000/bulk?key=inferno&cc=4242424242424242|12|25|123"
```

### 3. Health Check
```bash
curl "http://localhost:8000/health"
```

## Debug Endpoints

### Check Nonce Extraction
```bash
curl "http://localhost:8000/debug/nonce?domain=example.com"
```
Shows detailed nonce extraction attempts from each URL

### View Configuration
```bash
curl "http://localhost:8000/debug/config"
```
Returns current config values

### Test Session
```bash
curl "http://localhost:8000/debug/session"
```
Tests session creation with all features

## Configuration Guide

### Proxy Rotation
Edit `config.json`:
```json
{
  "enable_proxy_rotation": true,
  "proxy_list": [
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
    "http://proxy3.example.com:8080"
  ]
}
```

### Custom User Agents
```json
{
  "user_agents": [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36..."
  ]
}
```

### Retry Configuration
```json
{
  "retry_config": {
    "max_retries": 3,
    "initial_delay": 1,
    "max_delay": 10,
    "backoff_factor": 2
  }
}
```

### Payment URLs
```json
{
  "payment_urls": [
    "/my-account/add-payment-method/",
    "/checkout/",
    "/my-account/",
    "/wp-admin/admin-ajax.php",
    "/"
  ]
}
```

### Custom AJAX Payloads
```json
{
  "ajax_payloads": [
    {
      "action": "wc_stripe_create_and_confirm_setup_intent",
      "fields": {
        "wc-stripe-payment-method": "payment_method_id",
        "wc-stripe-payment-type": "card",
        "_ajax_nonce": "nonce"
      }
    }
  ]
}
```

## Key Features

✅ **Intelligent Proxy Rotation** - Rotate through proxies to avoid blocking
✅ **Advanced Fingerprinting** - Realistic browser headers to evade detection
✅ **Configurable System** - Manage everything via JSON
✅ **Better Nonce Extraction** - 16+ patterns covering complex HTML
✅ **Concurrent Bulk Operations** - Process multiple domains in parallel
✅ **Automatic Retries** - Exponential backoff for network errors
✅ **Modular Design** - Clean, reusable classes
✅ **Debug Endpoints** - Test and verify functionality

## Architecture

```
app.py
├── Flask app and routes
└── Uses utilities from utils.py

utils.py (All utility classes)
├── ConfigManager - Load/manage config.json
├── ProxyRotator - Cycle through proxies
├── BrowserFingerprint - Generate realistic headers
├── RetryHandler - Exponential backoff logic
├── HTTPSessionManager - Unified HTTP handling
├── NonceExtractor - 16+ pattern nonce extraction
├── StripeKeyExtractor - Extract Stripe keys
└── Async helpers - aiohttp utilities

config.json
└── All configuration (no hardcoding!)
```

## Troubleshooting

### Nonce Not Found
1. Use `/debug/nonce?domain=yoursite.com`
2. Check HTML output to verify nonce pattern
3. Add custom regex pattern to `NonceExtractor.PATTERNS`
4. Check if site requires specific headers

### Proxy Issues
1. Verify proxy URLs in config.json
2. Test proxy connectivity: `curl -x http://proxy:8080 https://example.com`
3. Disable proxy rotation temporarily to test

### Timeouts
1. Increase timeout values in retry_config
2. Check network connectivity
3. Try specific domain with `/debug/nonce`

### High Bot Detection
1. Use different user agents from config
2. Enable proxy rotation
3. Increase delays between requests
4. Add more realistic Accept/Referer headers

## Performance Tips

1. **Tune Worker Count**: Adjust `ThreadPoolExecutor` max_workers for bulk operations
2. **Cache Nonces**: Consider implementing caching for frequently accessed sites
3. **Proxy Pool**: Use a large proxy pool for high volume operations
4. **User Agent Rotation**: Mix various user agent strings

## Logging

Enable debug logging to see detailed operation info:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Logs include:
- URL attempts and responses
- Nonce extraction attempts and results
- Proxy rotation events
- Retry attempts and backoff delays
- Payment processing details

## Files Structure

```
├── app.py              # Main Flask application
├── utils.py            # Utility classes and functions
├── config.json         # Configuration (no hardcoding!)
├── requirements.txt    # Dependencies
├── IMPROVEMENTS.md     # Detailed improvement documentation
├── QUICKSTART.md       # This file
└── Procfile           # Heroku deployment configuration
```

## Deployment

### Heroku
```bash
git push heroku main
```

### Docker
```dockerfile
FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
```

### Environment Variables
```bash
export PORT=8000
python app.py
```

## API Responses

### Successful Response
```json
{
  "Response": "Card Added",
  "Status": "Approved"
}
```

### Declined Response
```json
{
  "Response": "Insufficient funds",
  "Status": "Declined"
}
```

### Error Response
```json
{
  "error": "Invalid card format",
  "status": "Bad Request"
}
```

## Support

For issues or improvements:
1. Check debug endpoints
2. Enable debug logging
3. Review IMPROVEMENTS.md for feature details
4. Check config.json formatting

