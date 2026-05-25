# PortIQ — Evaluate Smarter. Grow Faster.
Built by **Surabhi**

## Setup

```bash
pip install -r requirements.txt
```

## Setting GitHub Token (Required for GitHub evaluation)

GitHub API returns 401 if no token is set. Get a free token at:
https://github.com/settings/tokens → Generate new token (classic) → No scopes needed for public repos

**On Windows (CMD):**
```
set GITHUB_TOKEN=your_token_here
python app.py
```

**On Mac/Linux:**
```
export GITHUB_TOKEN=your_token_here
python app.py
```

**Or create a `.env` file** in the project folder:
```
GITHUB_TOKEN=your_token_here
FLASK_SECRET=any_random_string
```
Then install python-dotenv: `pip install python-dotenv`
And add to top of app.py: `from dotenv import load_dotenv; load_dotenv()`

## Run
```bash
python app.py
```
Open http://localhost:5000
