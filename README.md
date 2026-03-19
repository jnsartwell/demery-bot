# Demery Bot

A Discord bot that generates March Madness trash talk via Claude, in the style of a former coworker named Demery.

## Usage

```
/diss @user [intensity]
```

| Intensity | Vibe |
|---|---|
| `mild` | light ribbing, almost affectionate |
| `medium` | no mercy, full roast (default) |
| `harsh` | scorched earth |

Tag someone and let Demery handle the rest.

Not sure what to do? Use `/disshelp` for a quick rundown — only you can see it.

## Bracket Picks

```
/submitbracket [espn_url]
```

Paste your ESPN Tournament Challenge bracket URL and Demery will remember your picks. Future `/diss` roasts will call out your actual bracket choices by name.

## Server Setup

```
/setchannel #channel
```

Requires **Manage Server** permission. Sets the channel where Demery posts a daily digest after games are played — roasting busted brackets and (begrudgingly) acknowledging correct picks.
