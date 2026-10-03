<#
.SYNOPSIS
    Rebuilds the Skyrim SE/AE port of the Mannoroth Shield from the original Skyrim LE archive and packages it in 2K
    and 4K.

.DESCRIPTION
    Extracts the original archive and converts its mesh to Skyrim SE, then builds the remastered meshes (subdivided
    body, glowing eyes, handle taken from the vanilla iron shield, third- and first-person models in three sizes), the
    texture sets (upscaled diffuse, normal, environment and glow maps, BC7; the 2K package holds 4096 px textures and
    the 4K package 8192 px ones, labelled by the detail of the 512 px source upscale), compiles the Papyrus
    script (the compiler's user and computer names are removed from the .pex) and generates
    "[Tinesh] Mannoroth Shield.esp" with Mutagen. Each resolution is packed as a complete, MO2-installable archive
    "Mannoroth Shield SE (<res>) - <version>.7z" in -Packages. Upscaled intermediates are kept in <Cache> and reused;
    -Upscaler is only needed when the cache is empty.
    With -Install the chosen resolution replaces the contents of the Mod Organizer 2 mod folder (meta.ini is kept);
    MO2 must be closed.

.EXAMPLE
    .\build.ps1 -Install
#>
param(
    [string] $Version = "1.0",
    [string] $Archive = "$PSScriptRoot\original\MannorothShield-74030-1-1.rar",
    [string] $Out = "$PSScriptRoot\out",
    [string] $Cache = "$PSScriptRoot\cache",
    [string] $Packages = "$PSScriptRoot\dist",
    [string] $Game = "C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition",
    [string] $ModFolder = "$env:LOCALAPPDATA\ModOrganizer\Skyrim Special Edition\mods\[WEAPON] Mannoroth Shield (WoW)",
    [string] $Blender = "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
    [string] $SevenZip = "C:\Program Files\Vortex\resources\app.asar.unpacked\node_modules\7z-bin\win32\7z.exe",
    [string] $Upscaler = "realesrgan-ncnn-vulkan.exe",
    [ValidateSet("2K", "4K")] [string] $InstallResolution = "4K",
    [switch] $Install
)
# Not "Stop": PowerShell 5.1 turns the normal stderr output of native tools into terminating errors.
$ErrorActionPreference = "Continue"
$tools = "$PSScriptRoot\tools\lib"
$resolutions = @("2K", "4K")

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
$original = Join-Path $Out "original"
$work = Join-Path $Out "work"
$data = Join-Path $Out "Data"
$textureSets = Join-Path $Out "textures"
& $sevenZip x -y "-o$original" $Archive | Out-Null
if ($LASTEXITCODE) { throw "Could not extract $Archive" }
$srcData = Join-Path $original "Data"

New-Item -ItemType Directory -Force $work | Out-Null
$base = Join-Path $work "mannorothshield.nif"
& $blender --background --factory-startup --python "$tools\nif_le_to_se_rigid.py" -- `
    "$srcData\meshes\weapons\mannoroth\mannorothshield.nif" $base --scale 1.0 `
    --root-name MannorothShield --shape-name "MannorothShield:0" `
    --tex "Diffuse=textures\weapons\mannoroth\Mannoroth Shield.dds" `
    --tex "Normal=textures\weapons\mannoroth\Mannoroth Shield_n.dds" `
    --tex "EnvMask=textures\weapons\mannoroth\Mannoroth Shield_m.dds" | Select-String "CONVERT"
if (-not (Test-Path $base)) { throw "Mesh conversion failed" }

python "$tools\bsa_get.py" "$Game\Data\Skyrim - Meshes0.bsa" $work "meshes\armor\iron\shield.nif"
$iron = Join-Path $work "meshes\armor\iron\shield.nif"
if (-not (Test-Path $iron)) { throw "Could not extract the vanilla iron shield" }

$meshes = Join-Path $data "meshes\weapons\mannoroth"
$report = Join-Path $Out "meshes_report.json"
& $blender --background --factory-startup --python "$PSScriptRoot\tools\build_meshes.py" -- $base $iron $meshes $report | Select-String "MESHES"
if (-not (Test-Path $report)) { throw "Mesh build failed" }

python "$PSScriptRoot\tools\make_textures.py" "$srcData\textures\weapons\mannoroth\Mannoroth Shield.dds" $textureSets $Cache `
    --sets "2K=4096,4K=8192" --upscaler $Upscaler
if ($LASTEXITCODE) { throw "Texture build failed" }

$scriptSource = Join-Path $data "Source\Scripts"
$scriptOut = Join-Path $data "Scripts"
New-Item -ItemType Directory -Force $scriptSource, $scriptOut | Out-Null
Copy-Item "$PSScriptRoot\scripts\MannorothShieldFelRebukeScript.psc" $scriptSource
& "$Game\Papyrus Compiler\PapyrusCompiler.exe" "$scriptSource\MannorothShieldFelRebukeScript.psc" `
    -f="$Game\Data\Source\Scripts\TESV_Papyrus_Flags.flg" -i="$scriptSource;$Game\Data\Scripts\Source;$Game\Data\Source\Scripts" `
    -o="$scriptOut" -op -q
if ($LASTEXITCODE) { throw "Papyrus compilation failed" }
python "$tools\pex_anonymize.py" "$scriptOut\MannorothShieldFelRebukeScript.pex"

dotnet run -c Release --project "$PSScriptRoot\plugin" -- "$srcData\MannorothShield.esp" "$Game\Data\Skyrim.esm" $data $report
if ($LASTEXITCODE) { throw "Plugin generation failed" }

Remove-Item -Recurse -Force $original, $work
New-Item -ItemType Directory -Force $Packages | Out-Null
foreach ($res in $resolutions) {
    $stage = Join-Path $Out "package\$res"
    New-Item -ItemType Directory -Force $stage | Out-Null
    Get-ChildItem -LiteralPath $data, "$textureSets\$res" |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force }
    $package = Join-Path $Packages "Mannoroth Shield SE ($res) - $Version.7z"
    if (Test-Path -LiteralPath $package) { Remove-Item -LiteralPath $package -Force }
    & $sevenZip a -t7z -mx=9 $package "$stage\*" | Out-Null
    if ($LASTEXITCODE) { throw "Packaging failed: $res" }
    "{0}  {1:N1} MB" -f $package, ((Get-Item -LiteralPath $package).Length / 1MB)
}
Get-ChildItem -Recurse -File (Join-Path $Out "package\$InstallResolution") |
    ForEach-Object { "{0,10}  {1}" -f $_.Length, $_.FullName.Substring((Join-Path $Out "package\$InstallResolution").Length + 1) }

if ($Install) {
    if (Get-Process ModOrganizer -ErrorAction SilentlyContinue) { throw "Close Mod Organizer 2 before installing." }
    Get-ChildItem -LiteralPath $ModFolder | Where-Object { $_.Name -ne "meta.ini" } | Remove-Item -Recurse -Force
    Get-ChildItem (Join-Path $Out "package\$InstallResolution") |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $ModFolder -Recurse -Force }
    Write-Host "Installed $InstallResolution to $ModFolder"
}
