param(
    [string]$OutputPath = "deployment-seed.zip"
)

$ErrorActionPreference = "Stop"
$root = (Get-Item -LiteralPath (Join-Path $PSScriptRoot "..")).FullName.TrimEnd('\', '/')
$output = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$required = @(
    (Join-Path $root "legal.db"),
    (Join-Path $root "data\chroma_db")
)

foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required seed path is missing: $path"
    }
}

if (Test-Path -LiteralPath $output) {
    Remove-Item -LiteralPath $output -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$archive = [System.IO.Compression.ZipFile]::Open($output, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $files = Get-ChildItem -LiteralPath (Join-Path $root "legal.db"), (Join-Path $root "data\chroma_db"), (Join-Path $root "data\uploads") -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($root.Length).TrimStart('\', '/').Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $relative, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $output).Length / 1MB, 2)
Write-Output "Created $output ($sizeMb MB)"
