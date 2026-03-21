# Demery Bot

A Discord bot that generates March Madness trash talk via Claude, channeling the energy of Demery, who never lets a bad bracket pick slide.

## Features

- **AI-powered roasts** — Demery generates unique trash talk in a deadpan, whimsical voice using Claude
- **Bracket-aware** — upload your bracket and Demery will roast your actual picks by name
- **Daily digest** — every morning after tournament games, Demery recaps busted picks and (begrudgingly) acknowledges survivors
- **Intensity levels** — dial the roasts from mild ribbing to pointed jabs

## Commands

| Command | Description |
|---|---|
| `/diss @user [intensity]` | Demery roasts someone's bracket picks |
| `/submitbracket [image]` | Upload a bracket screenshot so Demery knows your picks |
| `/setchannel #channel` | Set the channel for daily digest posts *(requires Manage Channels)* |
| `/about` | Public intro message — what Demery Bot is and how to use it |
| `/disshelp` | Full usage guide and intensity levels *(only you can see it)* |

### Intensity Levels

| Intensity | Vibe |
|---|---|
| `mild` | light ribbing, almost affectionate |
| `medium` | sharp but fun *(default)* |
| `harsh` | the most pointed, lands with a wink |

## Getting Started

See the [Dev Guide](docs/dev-guide.md) for local setup, environment variables, and deploy instructions.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to file issues, submit PRs, and the development workflow.
