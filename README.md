# LINE Translate Bot

Python Flask LINE Messaging API translation bot for Render Web Service deployment.

## Current mode

- Chinese messages are translated to Indonesian.
- Non-Chinese messages are translated to Traditional Chinese.
- Translation engine: `deep-translator` GoogleTranslator.
- Deployment target: Render Web Service.

## Required Render environment variables

Set these in Render > Web Service > Environment:

```text
LINE_CHANNEL_SECRET
LINE_CHANNEL_ACCESS_TOKEN
```

After editing environment variables, redeploy the service.

## Render settings

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn main:app --bind 0.0.0.0:$PORT
```

## Health checks

Replace `https://your-service.onrender.com` with the actual Render public service URL.

```text
https://your-service.onrender.com/
```

Expected result:

```text
OK
```

```text
https://your-service.onrender.com/health
```

Expected result:

```json
{
  "status": "OK",
  "line_channel_secret_set": true,
  "line_channel_access_token_set": true
}
```

If `status` is `CONFIG_MISSING`, Render environment variables are missing or named incorrectly.

## Translation test without LINE

```text
https://your-service.onrender.com/test-translate?q=你好
```

Expected: Indonesian output.

```text
https://your-service.onrender.com/test-translate?q=selamat pagi
```

Expected: Traditional Chinese output.

## LINE webhook URL

In LINE Developers Console > Messaging API > Webhook URL, use:

```text
https://your-service.onrender.com/callback
```

Required LINE settings:

```text
Use webhook: Enabled
Auto-reply messages: Disabled
Greeting messages: Disabled or not interfering
```

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `/` does not return `OK` | Render service did not deploy or is sleeping | Open the Render service and redeploy latest commit |
| `/health` returns `CONFIG_MISSING` | Environment variables are missing | Set `LINE_CHANNEL_SECRET` and `LINE_CHANNEL_ACCESS_TOKEN` |
| LINE Verify returns 400 | Wrong Channel Secret | Recopy Channel secret to Render |
| LINE Verify returns 500 | App error | Check Render Logs |
| LINE Verify succeeds but bot does not reply | Wrong Access Token | Recopy long-lived Channel access token to Render |
| `/test-translate` fails | Translation engine issue | Check Render Logs for translation fallback errors |
