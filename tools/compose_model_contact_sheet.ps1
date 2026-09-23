param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
Add-Type -AssemblyName System.Drawing
$canvas = New-Object System.Drawing.Bitmap 1440, 660
$graphics = [System.Drawing.Graphics]::FromImage($canvas)
$graphics.Clear([System.Drawing.Color]::White)
$viewNames = @('front','back','left','right','top','hero')
try {
    for ($viewIndex=0; $viewIndex -lt $viewNames.Count; $viewIndex++) {
        $img=[System.Drawing.Image]::FromFile((Join-Path $EvidenceDirectory ($viewNames[$viewIndex]+'.png')))
        try { $graphics.DrawImage($img,($viewIndex%3)*480,[math]::Floor($viewIndex/3)*330,480,330) }
        finally { $img.Dispose() }
    }
    $canvas.Save((Join-Path $EvidenceDirectory 'contact-sheet.png'),[System.Drawing.Imaging.ImageFormat]::Png)
} finally { $graphics.Dispose(); $canvas.Dispose() }
