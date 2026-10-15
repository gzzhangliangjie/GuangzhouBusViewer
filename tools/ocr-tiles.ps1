param([string]$Dir = "C:\tmp\ocrtiles")
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStreamReference,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { Write-Error "no ocr engine"; exit 1 }

function Await($WinRtTask, $ResultType) {
  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  $netTask.Result
}

$out = @()
Get-ChildItem "$Dir\t*.jpg" | Sort-Object Name | ForEach-Object {
  $tile = $_.BaseName
  $meta = (Get-Content "$Dir\$tile.meta" -Raw).Trim()
  $parts = $meta.Split(',')
  $cx = [double]$parts[0]; $cy = [double]$parts[1]; $sc = [double]$parts[2]
  $uri = [Uri]("file:///" + $_.FullName.Replace('\','/'))
  $stream = Await ([Windows.Storage.Streams.RandomAccessStreamReference]::CreateFromUri($uri).OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
  $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
  foreach ($line in $res.Lines) {
    foreach ($w in $line.Words) {
      $r = $w.BoundingRect
      $out += [PSCustomObject]@{
        tile = $tile; text = $w.Text
        x = [math]::Round($cx + (($r.X + $r.Width/2) / $sc), 1)
        y = [math]::Round($cy + (($r.Y + $r.Height/2) / $sc), 1)
        w = [math]::Round($r.Width / $sc, 1); h = [math]::Round($r.Height / $sc, 1)
      }
    }
  }
}
$out | ConvertTo-Json -Compress | Out-File "$Dir\words.json" -Encoding utf8
Write-Host ("words: " + $out.Count)
