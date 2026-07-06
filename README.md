

An asynchronous Discord bot built with `discord.py` and `aiohttp` that raid a server!

## Features

### Administrative & Server Operations
* **`/servernuke`**: Server nuke with your bot token lol
* **`/create_invites`**: Generates invite links for servers YOUR bot lives in (yes your token)
* **`/preset-message`**: Premium feature allowing users to set up a custom message template.

### Automation & Communication Utilities
* **`/fast-spam` / `/spam`**: Sends predefined text formatting variations (such as ASCII, Unicode strings, or custom messages) at defined intervals and spams it in servers.
* **`/threadspam`**: Utility for automating thread creation within specified channels.
* **`/webhookspam`**: Dispatches automated messages to a target Discord Webhook URL.
* **`/say`**: Instructs the bot to repeat an input message anonymously.
* **`/anon-dm` / `/flooduser`**: Sends anonymous or high-frequency direct messages to specified users.
* **`/ghostping`**: Sends and immediately removes mentions to specific users.
* **`/raid`**: Sends our raid text to raid servers and promote the bot and the discord server.


### Simulation & Fake Commands
* **`/ip`**: Simulates a network alert interface containing randomized parameters.
* **`/hack`**: Displays a mock account information output block containing placeholder data fields.
* **`/avatar`**: Fetches and provides download links for a specified user's profile icon and banner.
* **`/roast`**: Randomly selects text strings from a local storage file (`roasts.txt`) to mention a targeted user.
* **`/spoof-message`**: Uses the Pillow library to draw a simulated Discord message card image using user-defined metrics.
* **`/blame`**: Outputs a mock confirmation text entry targeting a specific user.

### Credential Logging Integration
* **`/createlogger`**: Integrates with the IPLogger API to produce redirection URLs using chosen template masks.

### Access Control
* **Premium User Database**: Stores specialized system access lists using a localized JSON configuration state (`premium.json`).
* **`/x-add-premium` / `/x-rem-premium`**: Whitelist-restricted commands to manage access control lists.

## Setup & Prerequisites

### Required Files
The workspace expects the following layout structures:
* `config.json`: Contains global configuration variables such as token variables or user whitelists.
* `premium.json`: Initialized JSON array handling subscriber metrics.
* `presets.json`: Maps unique identifier strings to user-defined messaging arrays.
* `roasts.txt`: Simple plaintext text documents containing line-delimited response vectors.

### Installation
Ensure that Python 3.10+ is installed alongside the required package structures:
