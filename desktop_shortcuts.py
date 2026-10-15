"""Rename only existing Desktop links targeting this exact packaged executable."""
import base64
import json
import os
import subprocess
import sys

SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$shell = New-Object -ComObject WScript.Shell
$target = [IO.Path]::GetFullPath($env:FILETRIPITAKA_SHORTCUT_TARGET)
$name = $env:FILETRIPITAKA_SHORTCUT_NAME
$changed = @()
$failures = @()
$desktops = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory')) | Select-Object -Unique
foreach ($desktop in $desktops) {
    if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) { continue }
    foreach ($file in @(Get-ChildItem -LiteralPath $desktop -Filter '*.lnk' -File)) {
        try {
            $link = $shell.CreateShortcut($file.FullName)
            if (-not $link.TargetPath) { continue }
            $linkTarget = [IO.Path]::GetFullPath($link.TargetPath)
            if (-not [String]::Equals($linkTarget, $target, [StringComparison]::OrdinalIgnoreCase)) { continue }
            $newPath = Join-Path $desktop ($name + '.lnk')
            if ([String]::Equals($newPath, $file.FullName, [StringComparison]::OrdinalIgnoreCase)) { continue }
            if (Test-Path -LiteralPath $newPath) {
                $existing = $shell.CreateShortcut($newPath)
                if ($existing.TargetPath -and [String]::Equals([IO.Path]::GetFullPath($existing.TargetPath), $target, [StringComparison]::OrdinalIgnoreCase)) {
                    continue
                }
                $failures += ('Shortcut name already exists: ' + $newPath)
                continue
            }
            Rename-Item -LiteralPath $file.FullName -NewName ($name + '.lnk')
            $changed += $newPath
        } catch { $failures += $_.Exception.Message }
    }
}
@{renamed=@($changed); errors=@($failures)} | ConvertTo-Json -Compress
'''


def rename_desktop_shortcuts(language):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return dict(renamed=[], errors=[])
    executable = os.path.abspath(sys.executable)
    environment = dict(os.environ, FILETRIPITAKA_SHORTCUT_TARGET=executable,
                       FILETRIPITAKA_SHORTCUT_NAME='File Tripitaka' if language == 'en' else '파일만대장경')
    encoded = base64.b64encode(SCRIPT.encode('utf-16le')).decode('ascii')
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                env=environment, capture_output=True, encoding='utf-8-sig', errors='replace',
                                timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            return dict(renamed=[], errors=[result.stderr.strip() or 'Desktop shortcut update failed.'])
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return dict(renamed=[], errors=[str(exc)])
