# Railway Garmin Token Refresh

Garmin OAuth tokens expire periodically (~30 days for the refresh token). When Railway's sync fails with "Garmin sync failed", refresh the tokens.

## Steps

1. **Sync locally first** to refresh your local tokens:
   ```bash
   cd personal_health/running
   source venv/bin/activate
   python scripts/sync.py
   ```

2. **Generate base64 tokens** from your refreshed local tokens:
   ```bash
   python3 -c "
   import base64, os
   d = os.path.expanduser('~/.garminconnect')
   print('GARMIN_OAUTH1:')
   print(base64.b64encode(open(f'{d}/oauth1_token.json').read().encode()).decode())
   print()
   print('GARMIN_OAUTH2:')
   print(base64.b64encode(open(f'{d}/oauth2_token.json').read().encode()).decode())
   "
   ```

3. **Update Railway environment variables:**
   - Go to [Railway Dashboard](https://railway.app/dashboard)
   - Open your project → select the service
   - Go to **Variables** tab
   - Update `GARMIN_OAUTH1` and `GARMIN_OAUTH2` with the new values
   - Railway will auto-redeploy

## Note

With the "local sync only" approach, Railway doesn't need these tokens for normal operation — it serves the static `weeks_cache.json`. Tokens are only needed if you want the Railway "Sync with Garmin" button to work directly.
