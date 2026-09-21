param(
    [string]$ApiUrl = "https://legal-rag-advisor-api.onrender.com",
    [ValidateRange(60, 3600)]
    [int]$IntervalSeconds = 300,
    [ValidateRange(5, 120)]
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$healthUrl = "$($ApiUrl.TrimEnd('/'))/health"

function Get-IndiaTime {
    $indiaTimeZone = [System.TimeZoneInfo]::FindSystemTimeZoneById("India Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $indiaTimeZone)
}

Write-Host "TRANA Render keep-alive started."
Write-Host "Endpoint: $healthUrl"
Write-Host "Interval: every $IntervalSeconds seconds"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

while ($true) {
    $timestamp = (Get-IndiaTime).ToString("yyyy-MM-dd HH:mm:ss")
    $requestSucceeded = $false

    for ($attempt = 1; $attempt -le 3 -and -not $requestSucceeded; $attempt++) {
        try {
            $response = Invoke-WebRequest `
                -Uri $healthUrl `
                -Method Get `
                -TimeoutSec $TimeoutSeconds `
                -UseBasicParsing

            $health = $response.Content | ConvertFrom-Json
            $indexed = if ($null -ne $health.documents_indexed) { $health.documents_indexed } else { "unknown" }
            $store = if ($null -ne $health.vector_store_ready) { $health.vector_store_ready } else { "unknown" }

            Write-Host "[$timestamp IST] $($response.StatusCode) $($health.status) | indexed: $indexed | vector store ready: $store"
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

    Start-Sleep -Seconds $IntervalSeconds
}
