# Yad2 Car Monitor

A GitHub Actions-based monitoring tool that tracks car listings on Yad2 (Israeli marketplace) and sends Telegram notifications when new cars are added to your search results.

## What it does

The monitor runs every 20 minutes and checks the total number of results for your saved Yad2 search. When new cars appear, you get a Telegram notification with details about the new listings.

## Setup

### Prerequisites

- GitHub account
- Telegram bot token (get one from [@BotFather](https://t.me/botfather))
- Telegram chat ID (your personal chat ID or a group chat ID)
- Yad2 search URL for the cars you want to monitor

### Installation

1. Fork or clone this repository to your GitHub account

2. Go to your repository Settings → Secrets and variables → Actions

3. Add the following secrets:
   - `CAR_LISTING_URL` - Your Yad2 search URL (e.g., `https://www.yad2.co.il/vehicles/cars?manufacturer=...`)
   - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
   - `TELEGRAM_CHAT_ID` - Your Telegram chat ID

4. Enable GitHub Actions in your repository if not already enabled

### Getting your Telegram Chat ID

Send a message to your bot, then visit:
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```
Look for the "chat" object to find your ID.

## How it works

The monitor uses Selenium to load the Yad2 page and extract the total number of results. It stores this count between runs using GitHub Actions cache. When the count changes:

- If cars were added: Sends notification with details of the new listings
- If cars were removed: Sends notification about the decrease

The workflow runs automatically every 20 minutes from 6 AM to midnight (Israel time). You can also trigger it manually from the Actions tab.

## Configuration

The monitoring schedule can be adjusted in `.github/workflows/yad2_monitor.yml`. The default schedule is:
- Every 20 minutes
- Between 6 AM and midnight Israel time
- Every day

To change the schedule, modify the cron expression in the workflow file.

## Manual Run

You can trigger the monitor manually:
1. Go to the Actions tab in your repository
2. Select "Yad2 Car Monitor"
3. Click "Run workflow"

## Troubleshooting

If the monitor fails to extract the total count:
- Yad2 might have changed their page structure
- The search URL might be invalid
- Network issues with GitHub Actions

Check the Actions tab for detailed logs of each run.

## Files

- `yad2_monitor.py` - Main monitoring script
- `.github/workflows/yad2_monitor.yml` - GitHub Actions workflow configuration
- `requirements.txt` - Python dependencies

## License

MIT
