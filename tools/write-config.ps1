# Writes config.js from the PostHog project token in I:\shunya-systems\.secret\logger.env.
# Prints names and lengths only. Refuses when the token is missing or is not a project token.
$ErrorActionPreference = 'Stop'
$envFile = 'I:\shunya-systems\.secret\logger.env'
$e = @{}; Get-Content $envFile | % { if ($_ -match '^(\w+)=(.*)$') { $e[$matches[1]] = $matches[2].Trim() } }
$token = $e.POSTHOG_TOKEN; $hostUrl = $e.POSTHOG_HOST; if (-not $hostUrl) { $hostUrl = 'https://us.i.posthog.com' }
if (-not $token -or $token -notlike 'phc_*') { throw 'POSTHOG_TOKEN is missing or is not a phc_ project token; nothing written' }
$out = Join-Path (Split-Path $PSScriptRoot -Parent) 'config.js'
[IO.File]::WriteAllText($out, "window.WAITLIST_CONFIG = { token: `"$token`", host: `"$hostUrl`" };`n")
Write-Host "config.js written: token length $($token.Length), host $hostUrl"
