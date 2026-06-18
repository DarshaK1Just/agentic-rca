# Convert each DOCX deliverable to PDF via MS Word COM, updating the TOC first.
$dir = "D:\N7-AI Solution Engineer Round2\rca-engine\deliverables"
$files = @(
  "01_Technical_Design_Document",
  "02_Conceptual_Architecture_Blueprint",
  "03_Prototype_Code_and_How_to_Run"
)
$wdFormatPDF = 17
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
foreach ($f in $files) {
  $docx = Join-Path $dir "$f.docx"
  $pdf  = Join-Path $dir "$f.pdf"
  $doc = $word.Documents.Open($docx, $false, $true)  # ConfirmConversions=false, ReadOnly=true
  # Update every Table of Contents so the page references populate.
  if ($doc.TablesOfContents.Count -gt 0) {
    for ($i = 1; $i -le $doc.TablesOfContents.Count; $i++) { $doc.TablesOfContents.Item($i).Update() }
  }
  $doc.Fields.Update() | Out-Null
  $doc.ExportAsFixedFormat($pdf, $wdFormatPDF)
  $doc.Close($false)
  $pages = "?"
  Write-Output "PDF written: $f.pdf"
}
$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
Write-Output "DONE"
