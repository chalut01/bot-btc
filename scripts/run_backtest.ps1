param(
    [string]$strategy = "trend",
    [int]$limit = 200
)

# PowerShell wrapper: prefer the 'py' launcher if available (py -3), otherwise use 'python'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m btc_bot.backtest --strategy $strategy --limit $limit
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m btc_bot.backtest --strategy $strategy --limit $limit
} else {
    Write-Error "Python not found. Install Python 3.8+ and ensure 'python' or the 'py' launcher is on PATH."
    exit 1
}
