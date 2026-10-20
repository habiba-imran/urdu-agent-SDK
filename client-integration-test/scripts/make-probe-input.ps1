param([Parameter(Mandatory=$true)][string]$OutputDirectory)

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo -ArgumentList 16000,([System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen),([System.Speech.AudioFormat.AudioChannel]::Mono)
$utterances = @{
  'identity' = 'Are you an AI assistant?'
  'arithmetic' = 'What is two plus two?'
  'long' = 'Describe three ways to prepare for a busy day.'
  'stop' = 'Stop talking please.'
  'close' = 'Goodbye.'
}
try {
  foreach ($name in $utterances.Keys) {
    $path = Join-Path (Resolve-Path $OutputDirectory).Path ($name + '.wav')
    $synth.SetOutputToWaveFile($path, $format)
    $synth.Speak($utterances[$name])
    $synth.SetOutputToNull()
  }
} finally { $synth.Dispose() }
Write-Output 'Generated five synthetic 16kHz mono input clips. No microphone recording.'
