$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $line = [Console]::In.ReadLine()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -gt 32768) { throw 'invalid_request' }
    $request = $line | ConvertFrom-Json
    if ($request.text -isnot [string] -or [string]::IsNullOrWhiteSpace($request.text) -or
        $request.text.Length -gt 2000 -or $request.text.IndexOf([char]0) -ge 0 -or
        $request.voice -isnot [string] -or [string]::IsNullOrWhiteSpace($request.voice) -or
        $request.voice.Length -gt 160) { throw 'invalid_request' }
    if ($request.rate -isnot [int] -or $request.rate -lt -10 -or $request.rate -gt 10 -or
        $request.volume -isnot [int] -or $request.volume -lt 0 -or $request.volume -gt 100 -or
        $request.timeout_ms -isnot [int] -or $request.timeout_ms -lt 500 -or
        $request.timeout_ms -gt 90000) { throw 'invalid_request' }
    Add-Type -AssemblyName System.Speech
    $source = @'
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Speech.AudioFormat;
using System.Speech.Synthesis;
using System.Threading;
using System.Threading.Tasks;

public static class LocalSapiWave {
    [DllImport("ole32.dll")] private static extern int CoInitializeEx(IntPtr p, uint mode);
    [DllImport("ole32.dll")] private static extern void CoUninitialize();
    public static byte[] Run(string text, string voice, int rate, int volume, int timeoutMs) {
        int hr = CoInitializeEx(IntPtr.Zero, 2);
        if (hr < 0) Marshal.ThrowExceptionForHR(hr);
        SpeechSynthesizer synth = null;
        MemoryStream audio = null;
        ManualResetEvent done = null;
        Exception error = null;
        bool wasCancelled = false;
        EventHandler<SpeakCompletedEventArgs> completed = null;
        try {
            audio = new MemoryStream();
            done = new ManualResetEvent(false);
            synth = new SpeechSynthesizer();
            bool found = false;
            foreach (InstalledVoice installed in synth.GetInstalledVoices()) {
                if (installed.Enabled && installed.VoiceInfo.Name == voice &&
                    installed.VoiceInfo.Culture.TwoLetterISOLanguageName == "zh") {
                    found = true;
                    break;
                }
            }
            if (!found) throw new InvalidOperationException("chinese_voice_missing");
            synth.SelectVoice(voice);
            synth.Rate = rate;
            synth.Volume = volume;
            synth.SetOutputToAudioStream(audio,
                new SpeechAudioFormatInfo(16000, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
            completed = delegate(object sender, SpeakCompletedEventArgs e) {
                error = e.Error;
                wasCancelled = e.Cancelled;
                try { done.Set(); } catch (ObjectDisposedException) {}
            };
            synth.SpeakCompleted += completed;
            Task<string> control = Task.Factory.StartNew<string>(
                delegate { return Console.In.ReadLine(); }, CancellationToken.None,
                TaskCreationOptions.LongRunning, TaskScheduler.Default);
            Stopwatch elapsed = Stopwatch.StartNew();
            synth.SpeakAsync(text); // Literal text, never SSML or executable code.
            while (!done.WaitOne(20)) {
                if (control.IsCompleted || elapsed.ElapsedMilliseconds >= timeoutMs) {
                    synth.SpeakAsyncCancelAll();
                    done.WaitOne(500);
                    throw new OperationCanceledException();
                }
            }
            if (error != null || wasCancelled) throw new InvalidOperationException("synthesis_failed");
            synth.SetOutputToNull();
            byte[] pcm = audio.ToArray();
            using (MemoryStream wav = new MemoryStream()) {
                using (BinaryWriter writer = new BinaryWriter(wav)) {
                    writer.Write(new byte[] { 82, 73, 70, 70 }); // RIFF
                    writer.Write(36 + pcm.Length);
                    writer.Write(new byte[] { 87, 65, 86, 69, 102, 109, 116, 32 }); // WAVEfmt
                    writer.Write(16);
                    writer.Write((short)1); // PCM
                    writer.Write((short)1); // mono
                    writer.Write(16000);
                    writer.Write(32000);
                    writer.Write((short)2);
                    writer.Write((short)16);
                    writer.Write(new byte[] { 100, 97, 116, 97 }); // data
                    writer.Write(pcm.Length);
                    writer.Write(pcm);
                    writer.Flush();
                    return wav.ToArray();
                }
            }
        } finally {
            try {
                if (synth != null) {
                    try { synth.SpeakAsyncCancelAll(); } catch {}
                    if (completed != null) synth.SpeakCompleted -= completed;
                    synth.Dispose();
                }
            } finally {
                try {
                    if (audio != null) audio.Dispose();
                    if (done != null) done.Dispose();
                } finally { CoUninitialize(); }
            }
        }
    }
}
'@
    Add-Type -TypeDefinition $source -ReferencedAssemblies @(
        'System.dll', 'System.Core.dll',
        [System.Speech.Synthesis.SpeechSynthesizer].Assembly.Location)
    [byte[]]$wave = [LocalSapiWave]::Run($request.text, $request.voice,
        $request.rate, $request.volume, $request.timeout_ms)
    $stdout = [Console]::OpenStandardOutput()
    $stdout.Write($wave, 0, $wave.Length)
    $stdout.Flush()
} catch {
    [Console]::Error.WriteLine('local_sapi_failed')
    exit 1
}
