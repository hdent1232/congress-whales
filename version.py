"""Single source of truth for the app version and update/repo coordinates."""

VERSION = "1.0.6"

# GitHub repo used for the auto-update check and release downloads.
GITHUB_OWNER = "hdent1232"
GITHUB_REPO = "congress-whales"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
