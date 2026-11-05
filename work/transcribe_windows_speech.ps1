param(
    [Parameter(Mandatory = $true)]
    [string]$AudioPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$recognizerInfo = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
    Where-Object { $_.Culture.Name -eq 'en-US' } |
    Select-Object -First 1
if ($null -eq $recognizerInfo) {
    throw 'No installed en-US Windows speech recognizer.'
}

$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($recognizerInfo)
try {
    $recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $recognizer.SetInputToWaveFile((Resolve-Path -LiteralPath $AudioPath).Path)
    $parts = @()
    while ($true) {
        try {
            $result = $recognizer.Recognize()
        }
        catch [System.InvalidOperationException] {
            # The legacy desktop recognizer sometimes reports end-of-file as
            # "No audio input" after returning its final recognition result.
            break
        }
        if ($null -eq $result) {
            break
        }
        $parts += [pscustomobject]@{
            text = $result.Text
            confidence = [math]::Round($result.Confidence, 3)
            start = [math]::Round($result.Audio.AudioPosition.TotalSeconds, 2)
            duration = [math]::Round($result.Audio.Duration.TotalSeconds, 2)
        }
    }
    [pscustomobject]@{
        file = (Resolve-Path -LiteralPath $AudioPath).Path
        recognitions = $parts
    } | ConvertTo-Json -Depth 8
}
finally {
    $recognizer.Dispose()
}
