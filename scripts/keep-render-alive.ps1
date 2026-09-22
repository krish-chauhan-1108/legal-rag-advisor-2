param(
    [string]$ApiUrl = "https://legal-rag-advisor-api.onrender.com",
    [ValidateRange(60, 3600)]
    [int]$IntervalSeconds = 240,
    [ValidateRange(5, 120)]
    [int]$TimeoutSeconds = 30,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$normalizedApiUrl = $ApiUrl.Trim().Trim('"').Trim("'").Trim()

try {
    $baseUri = [Uri]$normalizedApiUrl
    if (-not $baseUri.IsAbsoluteUri -or $baseUri.Scheme -notin @('http', 'https') -or [string]::IsNullOrWhiteSpace($baseUri.Host)) {
        throw "The API URL must be an absolute http(s) URL."
    }
}
catch {
    throw "Invalid API URL '$ApiUrl'. Use a value such as https://legal-rag-advisor-api.onrender.com"
}

$healthUriBuilder = [UriBuilder]$baseUri
$healthPath = $healthUriBuilder.Path.TrimEnd('/')
if ([string]::IsNullOrWhiteSpace($healthPath)) {
    $healthPath = "/health"
}
elseif (-not $healthPath.EndsWith("/health", [System.StringComparison]::OrdinalIgnoreCase)) {
    $healthPath = "$healthPath/health"
}
$healthUriBuilder.Path = $healthPath
$healthUriBuilder.Query = ""
$healthUrl = $healthUriBuilder.Uri.AbsoluteUri.TrimEnd('/')

function Get-IndiaTime {
    $indiaTimeZone = [System.TimeZoneInfo]::FindSystemTimeZoneById("India Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $indiaTimeZone)
}

Write-Host "TRANA Render keep-alive started."
Write-Host "Endpoint: $healthUrl"
if ($Once) {
    Write-Host "Mode: one request"
}
else {
    Write-Host "Interval: every $IntervalSeconds seconds"
}
Write-Host "Press Ctrl+C to stop."
Write-Host ""

while ($true) {
    $requestSucceeded = $false

    for ($attempt = 1; $attempt -le 3 -and -not $requestSucceeded; $attempt++) {
        $timestamp = (Get-IndiaTime).ToString("yyyy-MM-dd HH:mm:ss")
        try {
            $separator = if ($healthUrl.Contains('?')) { '&' } else { '?' }
            $requestUrl = "$healthUrl$separator`ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
            $response = Invoke-WebRequest `
                -Uri $requestUrl `
                -Method Get `
                -TimeoutSec $TimeoutSeconds `
                -Headers @{ 'Cache-Control' = 'no-cache'; 'Pragma' = 'no-cache' } `
                -UseBasicParsing

            $health = $response.Content | ConvertFrom-Json
            $indexed = if ($null -ne $health.documents_indexed) { $health.documents_indexed } else { "unknown" }
            $store = if ($null -ne $health.vector_store_ready) { $health.vector_store_ready } else { "unknown" }

            if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
                throw "Health endpoint returned HTTP $($response.StatusCode)."
            }

            Write-Host "[$timestamp IST] Ping OK | HTTP $($response.StatusCode) | $($health.status) | indexed: $indexed | vector store ready: $store"
            $requestSucceeded = $true
        }
        catch {
            if ($attempt -lt 3) {
                Write-Warning "[$timestamp IST] Attempt $attempt failed; retrying in 5 seconds: $($_.Exception.Message)"
                Start-Sleep -Seconds 5
            }
            else {
                Write-Warning "[$timestamp IST] Keep-alive request failed after 3 attempts: $($_.Exception.Message)"
            }
        }
    }

    if ($Once) {
        if (-not $requestSucceeded) { exit 1 }
        exit 0
    }

    Start-Sleep -Seconds $IntervalSeconds
}
