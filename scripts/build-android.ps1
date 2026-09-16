param(
    [string]$JavaHome,
    [string]$AndroidHome,
    [switch]$UseMirror,
    [switch]$DeviceTests
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$androidProject = Join-Path $projectRoot 'android'

if ($JavaHome) { $env:JAVA_HOME = (Resolve-Path -LiteralPath $JavaHome).Path }
if ($AndroidHome) { $env:ANDROID_HOME = (Resolve-Path -LiteralPath $AndroidHome).Path }
if (-not $env:JAVA_HOME -or -not (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe'))) {
    throw 'Set JAVA_HOME to JDK 17, or pass -JavaHome.'
}
if (-not $env:ANDROID_HOME -and $env:ANDROID_SDK_ROOT) { $env:ANDROID_HOME = $env:ANDROID_SDK_ROOT }
if (-not $env:ANDROID_HOME) {
    $defaultSdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
    if (Test-Path -LiteralPath $defaultSdk) { $env:ANDROID_HOME = $defaultSdk }
}
if (-not $env:ANDROID_HOME -or -not (Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'platforms\android-35\android.jar'))) {
    throw 'Install Android SDK Platform 35 and Build Tools 34.0.0, then set ANDROID_HOME.'
}

$env:GRADLE_USER_HOME = Join-Path $androidProject '.gradle-user-home'
$gradleExe = Join-Path $androidProject 'gradlew.bat'
if ($UseMirror) {
    # The mirror archive must match the official checksum pinned in the wrapper.
    $properties = Get-Content -LiteralPath (Join-Path $androidProject 'gradle\wrapper\gradle-wrapper.properties')
    $expected = (($properties | Where-Object { $_ -match '^distributionSha256Sum=' }) -split '=', 2)[1].Trim()
    if ($expected -notmatch '^[a-f0-9]{64}$') { throw 'Missing pinned Gradle checksum.' }
    $toolsDirectory = Join-Path $androidProject '.gradle-tools'
    $gradleZip = Join-Path $toolsDirectory 'gradle-8.9-bin.zip'
    $gradleExe = Join-Path $toolsDirectory 'gradle-8.9\bin\gradle.bat'
    $checksumFile = Join-Path $toolsDirectory 'distribution.sha256'
    $cached = (Test-Path -LiteralPath $gradleExe) -and (Test-Path -LiteralPath $checksumFile)
    if ($cached) { $cached = (Get-Content -LiteralPath $checksumFile -Raw).Trim() -eq $expected }
    if (-not $cached) {
        New-Item -ItemType Directory -Force -Path $toolsDirectory | Out-Null
        Write-Host 'Downloading Gradle from the mirror and verifying the pinned official checksum...'
        Invoke-WebRequest -Uri 'https://repo.huaweicloud.com/gradle/gradle-8.9-bin.zip' -OutFile $gradleZip -UseBasicParsing
        $actual = (Get-FileHash -LiteralPath $gradleZip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw 'Gradle checksum mismatch. Archive was not executed.' }
        Expand-Archive -LiteralPath $gradleZip -DestinationPath $toolsDirectory -Force
        Set-Content -LiteralPath $checksumFile -Value $expected -Encoding ascii
    }
}
Push-Location $androidProject
try {
    & $gradleExe testDebugUnitTest lintDebug assembleDebug --console=plain
    if ($LASTEXITCODE -ne 0) { throw 'Android build or verification failed.' }
    if ($DeviceTests) {
        & $gradleExe connectedDebugAndroidTest --console=plain
        if ($LASTEXITCODE -ne 0) { throw 'Device tests failed.' }
    }
    Write-Host "APK: $(Join-Path $androidProject 'app\build\outputs\apk\debug\app-debug.apk')"
} finally { Pop-Location }
