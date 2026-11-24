# Runs the queued long jobs, one after another, and carries on after a stop.
#
#   powershell -ExecutionPolicy Bypass -File tools\jobs.ps1            run the queue
#   powershell -ExecutionPolicy Bypass -File tools\jobs.ps1 -Install   also start it at every logon
#
# The queue is data\jobs.txt: one command a line, run from the project folder
# with the project's Python ("python" means .venv\Scripts\python.exe). A job
# is taken off the queue only when it exits 0, so after a restart or a power
# cut the job it was on runs again; every job queued must therefore pick up
# where it stopped (matched.py bliss skips the blocks already recorded).
#
# An outage is not a failure of the job. Jobs run with SSY_WAIT_FOR_NETWORK
# set, so their reads wait it out (reading.py); a job that still ends on a
# network error exits 75 and is run again after 10 minutes, as often as it
# takes, and that is not counted. Any other failure is tried three times, 10 minutes apart;
# then the job stays on the queue and the queue stops, since later jobs may
# build on it. Output goes to data\logs\jobs.log, appended.
# Only one copy runs: a second finds the lock held and exits.
param([switch]$Install)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$queue = Join-Path $root "data\jobs.txt"
$log = Join-Path $root "data\logs\jobs.log"
$python = Join-Path $root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

if ($Install) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
    Register-ScheduledTask -TaskName "SignalSearchYoke jobs" -Action $action -Trigger $trigger -Settings $settings `
        -Description "Resumes SignalSearchYoke's queued long jobs (tools\jobs.ps1)" -Force | Out-Null
    "installed: runs at logon"
    exit 0
}

function Say($text) {
    Add-Content -Path $log -Encoding utf8 -Value ("{0:yyyy-MM-ddTHH:mm:ss} {1}" -f (Get-Date), $text)
}

try {
    $lock = [System.IO.File]::Open((Join-Path $root "data\jobs.lock"), "OpenOrCreate", "ReadWrite", "None")
} catch {
    exit 0  # another copy is running the queue
}

$networkExit = 75  # yoke.NETWORK_EXIT: the job itself says a network error ended it

Start-Sleep -Seconds 60  # after a logon, let WSL and the drives come up
Say "queue started"
$env:SSY_WAIT_FOR_NETWORK = "1"
while ((Test-Path $queue) -and
       ($job = Get-Content $queue | Where-Object { $_.Trim() } | Select-Object -First 1)) {
    $ok = $false
    $try = 1
    while ($try -le 3 -and -not $ok) {
        Say "run (try $try): $job"
        $cmd = $job -replace '^python ', "`"$python`" "
        cmd.exe /c "$cmd >> `"$log`" 2>&1"
        $code = $LASTEXITCODE
        $ok = ($code -eq 0)
        Say "exit $code`: $job"
        if ($ok) { break }
        if ($code -eq $networkExit) {
            Say "network failure, not counted; running it again in 10 minutes"
            Start-Sleep -Seconds 600
            continue
        }
        $try++
        if ($try -le 3) { Start-Sleep -Seconds 600 }
    }
    if (-not $ok) {
        Say "stopped after 3 tries; this job and those after it stay on the queue: $job"
        break
    }
    $rest = @(Get-Content $queue | Where-Object { $_.Trim() -and $_ -ne $job })
    Set-Content -Path $queue -Value $rest -Encoding utf8
}
Say "queue ended"
$lock.Close()
