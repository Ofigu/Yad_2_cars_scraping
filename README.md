# Yad2 Car Monitor

A GitHub Actions-based monitoring tool that tracks car listings on Yad2 (Israeli marketplace) and sends Telegram notifications when new cars are added to your search results.

## What it does

The monitor runs every 20 minutes and checks the total number of results for your saved Yad2 search. When new cars appear, you get a Telegram notification with details of the new listings.

## How it works

Instead of using a browser, the scraper makes a plain HTTP request and extracts listing data from the `__NEXT_DATA__` JSON blob that Yad2 embeds in every page (it's a Next.js app). This avoids headless browser fingerprinting and is much faster and lighter than Selenium.

The total count and history are persisted between runs using GitHub Actions cache.

## Setup

### Prerequisites

- GitHub account
- Telegram bot token (get one from [@BotFather](https://t.me/botfather))
- Telegram chat ID (your personal chat ID or a group chat ID)
- A Yad2 search URL for the cars you want to monitor

### 1. Fork this repository

Fork or clone this repo to your own GitHub account.

### 2. Add GitHub Secrets

Go to your repository **Settings → Secrets and variables → Actions** and add:

| Secret | Description | Example |
|---|---|---|
| `LISTING_URL` | Your Yad2 search URL | `https://www.yad2.co.il/vehicles/cars?manufacturer=21&year=2020--1` |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | `123456789` |

### 3. Enable GitHub Actions

Go to the **Actions** tab in your repository and enable workflows if prompted.

That's it — the monitor will run automatically on schedule.

### Getting your Telegram Chat ID

1. Start a conversation with your bot on Telegram
2. Visit this URL in your browser (replace with your token):
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
3. Look for the `"chat"` object — your ID is the `"id"` field inside it

## Running manually

To trigger a check immediately:
1. Go to the **Actions** tab in your repository
2. Select **Yad2 Listing Monitor**
3. Click **Run workflow**

## Schedule

The workflow runs every 20 minutes from 6 AM to midnight UTC (roughly 9 AM–3 AM Israel time). To change it, edit the cron expression in [.github/workflows/yad2_monitor.yml](.github/workflows/yad2_monitor.yml):

```yaml
- cron: '*/20 6-23 * * *'
```

## Notifications

- **New listings added**: notification with count change and details of up to 3 new listings
- **Listings removed**: notification with count change
- **First run**: confirmation message with the current total

## Troubleshooting

**403 Forbidden / blocked**: Yad2's WAF (Imperva) blocks some GitHub Actions IP ranges. If this happens consistently, trigger a new run — GitHub assigns a different IP each time. Alternatively, set up a self-hosted runner on your home PC for a stable residential IP.

**Total not found**: If the scraper can't find the listing count, it uploads a `debug_next_data.json` artifact in the Actions run. Download it to inspect the raw JSON structure from Yad2.

**No Telegram message received**: Double-check that `LISTING_URL`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` are all set correctly in repository secrets. The secret name must be exactly `LISTING_URL` (not `CAR_LISTING_URL`).

## Files

- `yad2_monitor.py` — Main monitoring script
- `.github/workflows/yad2_monitor.yml` — GitHub Actions workflow
- `requirements.txt` — Python dependencies

## License

MIT
