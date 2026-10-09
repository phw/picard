# Apply fixes to the build result

Param(
  [ValidateScript({Test-Path $_ -PathType Container})]
  [String]
  $Path
)

$ErrorActionPreference = 'Stop'

$InternalPath = (Join-Path -Path $Path -ChildPath _internal)

# Move all Qt5 DLLs into the main folder to avoid conflicts with system wide
# versions of those dependencies. Since some version PyInstaller tries to
# maintain the file hierarchy of imported modules, but this easily breaks
# DLL loading on Windows.
# Workaround for https://tickets.metabrainz.org/browse/PICARD-2736
$Qt5BinDir = (Join-Path -Path $InternalPath -ChildPath PyQt5\Qt5\bin)
Write-Output "Moving DLLs from $Qt5BinDir to package root..."
Move-Item -Path (Join-Path -Path $Qt5BinDir -ChildPath *.dll) -Destination $Path -Verbose -Force
Remove-Item -Path $Qt5BinDir
Move-Item -Path (Join-Path -Path $InternalPath -ChildPath libcrypto-3*.dll) -Destination $Path -Force
Move-Item -Path (Join-Path -Path $InternalPath -ChildPath libssl-3*.dll) -Destination $Path -Force
