Param(
  [String]
  $DiscidVersion,
  [String]
  $DiscidSha256Sum,
  [String]
  $FpcalcVersion,
  [String]
  $FpcalcSha256Sum
)

$ErrorActionPreference = "Stop"

$ScriptDirectory = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
. $ScriptDirectory\win-common.ps1

New-Item -Name .\build -ItemType Directory -ErrorAction Ignore

If ($DiscidVersion) {
    $ArchiveFile = ".\build\libdiscid.zip"
    Write-Output "Downloading libdiscid $DiscidVersion to $ArchiveFile..."
    DownloadFile -Url "http://ftp.musicbrainz.org/pub/musicbrainz/libdiscid/libdiscid-$DiscidVersion-win.zip" `
        -FileName $ArchiveFile
    if ($DiscidSha256Sum) {
        VerifyHash -FileName $ArchiveFile -Sha256Sum $DiscidSha256Sum
    }
    Expand-Archive -Path $ArchiveFile -DestinationPath .\build\libdiscid -Force
    Copy-Item .\build\libdiscid\libdiscid-$DiscidVersion-win\x64\discid.dll .
}

If ($FpcalcVersion) {
    $ArchiveFile = ".\build\fpcalc.zip"
    Write-Output "Downloading chromaprint-fpcalc $FpcalcVersion to $ArchiveFile..."
    DownloadFile -Url "https://github.com/acoustid/chromaprint/releases/download/v$FpcalcVersion/chromaprint-fpcalc-$FpcalcVersion-windows-x86_64.zip" `
        -FileName $ArchiveFile
    if ($FpcalcSha256Sum) {
        VerifyHash -FileName $ArchiveFile -Sha256Sum $FpcalcSha256Sum
    }
    Expand-Archive -Path $ArchiveFile -DestinationPath .\build\fpcalc -Force
    Copy-Item .\build\fpcalc\chromaprint-fpcalc-$FpcalcVersion-windows-x86_64\fpcalc.exe .
}
