Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ---------- Шляхи та файли ----------
$AppDir = Join-Path $PSScriptRoot 'monitor_data'
if (-not (Test-Path $AppDir)) { New-Item -Path $AppDir -ItemType Directory | Out-Null }
$TargetsFile = Join-Path $AppDir 'targets.json'
$SettingsFile = Join-Path $AppDir 'settings.json'
$LogFile = Join-Path $AppDir 'monitor.log'

# ---------- Функції для зашифрованого збереження токена ----------
function Save-Token {
    param([string]$PlainToken)
    if (-not $PlainToken) { return }
    $sec = ConvertTo-SecureString $PlainToken -AsPlainText -Force
    $enc = $sec | ConvertFrom-SecureString
    Set-Content -Path $SettingsFile -Value (@{ token = $enc; chat = (Get-Content -Path $SettingsFile -ErrorAction SilentlyContinue | ConvertFrom-Json).chat } | ConvertTo-Json) -Force
}
function Load-Token {
    if (-not (Test-Path $SettingsFile)) { return $null }
    try {
        $j = Get-Content $SettingsFile -Raw | ConvertFrom-Json
        if (-not $j.token) { return $null }
        $sec = $j.token | ConvertTo-SecureString
        $ptr = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        )
        return $ptr
    } catch { return $null }
}
function Save-ChatId {
    param([string]$chat)
    if (-not (Test-Path $SettingsFile)) { $obj = @{ token = $null; chat = $chat } | ConvertTo-Json; Set-Content -Path $SettingsFile -Value $obj -Force; return }
    $j = Get-Content $SettingsFile -Raw | ConvertFrom-Json
    $j.chat = $chat
    $j | ConvertTo-Json | Set-Content -Path $SettingsFile -Force
}
function Load-ChatId {
    if (-not (Test-Path $SettingsFile)) { return $null }
    try { (Get-Content $SettingsFile -Raw | ConvertFrom-Json).chat } catch { $null }
}

# ---------- Логування ----------
function Add-Log {
    param([string]$text)
    $line = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] $text"
    Add-Content -Path $LogFile -Value $line
    $rtbLog.AppendText("$line`r`n")
    $rtbLog.ScrollToCaret()
}

# ---------- Завантаження targets ----------
$Targets = @()
if (Test-Path $TargetsFile) {
    try { $Targets = Get-Content $TargetsFile -Raw | ConvertFrom-Json } catch { $Targets = @() }
}

# ---------- UI ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Ping Monitor'
$form.Size = New-Object System.Drawing.Size(900,600)
$form.StartPosition = 'CenterScreen'

# DataGridView
$grid = New-Object System.Windows.Forms.DataGridView
$grid.Location = New-Object System.Drawing.Point(10,10)
$grid.Size = New-Object System.Drawing.Size(560,420)
$grid.ReadOnly = $true
$grid.AllowUserToAddRows = $false
$grid.SelectionMode = 'FullRowSelect'
$grid.Columns.Add((New-Object System.Windows.Forms.DataGridViewTextBoxColumn -Property @{Name='Address'; HeaderText='Address'; Width=220})) | Out-Null
$grid.Columns.Add((New-Object System.Windows.Forms.DataGridViewTextBoxColumn -Property @{Name='State'; HeaderText='State'; Width=80})) | Out-Null
$grid.Columns.Add((New-Object System.Windows.Forms.DataGridViewTextBoxColumn -Property @{Name='LastChange'; HeaderText='Last Change'; Width=200})) | Out-Null
$form.Controls.Add($grid)

# Input + buttons
$tbAddress = New-Object System.Windows.Forms.TextBox
$tbAddress.Location = New-Object System.Drawing.Point(10,440)
$tbAddress.Size = New-Object System.Drawing.Size(360,22)
$form.Controls.Add($tbAddress)

$btnAdd = New-Object System.Windows.Forms.Button
$btnAdd.Text = 'Add'
$btnAdd.Location = New-Object System.Drawing.Point(380,440)
$btnAdd.Size = New-Object System.Drawing.Size(80,22)
$form.Controls.Add($btnAdd)

$btnRemove = New-Object System.Windows.Forms.Button
$btnRemove.Text = 'Remove'
$btnRemove.Location = New-Object System.Drawing.Point(470,440)
$btnRemove.Size = New-Object System.Drawing.Size(100,22)
$form.Controls.Add($btnRemove)

# Start/Stop
$btnStart = New-Object System.Windows.Forms.Button
$btnStart.Text = 'Start'
$btnStart.Location = New-Object System.Drawing.Point(580,10)
$btnStart.Size = New-Object System.Drawing.Size(120,30)
$form.Controls.Add($btnStart)

$btnStop = New-Object System.Windows.Forms.Button
$btnStop.Text = 'Stop'
$btnStop.Location = New-Object System.Drawing.Point(710,10)
$btnStop.Size = New-Object System.Drawing.Size(120,30)
$btnStop.Enabled = $false
$form.Controls.Add($btnStop)

# Log viewer (right)
$rtbLog = New-Object System.Windows.Forms.RichTextBox
$rtbLog.Location = New-Object System.Drawing.Point(580,50)
$rtbLog.Size = New-Object System.Drawing.Size(300,380)
$rtbLog.ReadOnly = $true
$form.Controls.Add($rtbLog)

# Settings: token/chat
$lblToken = New-Object System.Windows.Forms.Label
$lblToken.Text = 'Bot Token:'
$lblToken.Location = New-Object System.Drawing.Point(580,440)
$form.Controls.Add($lblToken)

$tbToken = New-Object System.Windows.Forms.TextBox
$tbToken.Location = New-Object System.Drawing.Point(650,438)
$tbToken.Size = New-Object System.Drawing.Size(230,22)
$tbToken.UseSystemPasswordChar = $true
$form.Controls.Add($tbToken)

$lblChat = New-Object System.Windows.Forms.Label
$lblChat.Text = 'Chat ID:'
$lblChat.Location = New-Object System.Drawing.Point(580,470)
$form.Controls.Add($lblChat)

$tbChat = New-Object System.Windows.Forms.TextBox
$tbChat.Location = New-Object System.Drawing.Point(650,468)
$tbChat.Size = New-Object System.Drawing.Size(140,22)
$form.Controls.Add($tbChat)

$btnSaveSettings = New-Object System.Windows.Forms.Button
$btnSaveSettings.Text = 'Save'
$btnSaveSettings.Location = New-Object System.Drawing.Point(800,468)
$btnSaveSettings.Size = New-Object System.Drawing.Size(80,22)
$form.Controls.Add($btnSaveSettings)

# Status label
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text = 'Stopped'
$lblStatus.Location = New-Object System.Drawing.Point(10,520)
$form.Controls.Add($lblStatus)

# ---------- Відновлення таблиці з Targets ----------
foreach ($t in $Targets) {
    $grid.Rows.Add($t, 'UNKNOWN', '')
}

# ---------- Telegram helpers ----------
function Send-Telegram {
    param([string]$text)
    $token = Load-Token
    $chat = Load-ChatId
    if (-not $token -or -not $chat) { return }
    try {
        Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/sendMessage" -Method Post -Body @{ chat_id = $chat; text = $text } -ErrorAction Stop | Out-Null
    } catch {
        Add-Log "Telegram send failed: $($_.Exception.Message)"
    }
}

# ---------- Timer (ping loop) ----------
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000   # 5 seconds
$timer.Add_Tick({
    # для кожного рядка таблиці робимо Test-Connection
    for ($i = 0; $i -lt $grid.Rows.Count; $i++) {
        $row = $grid.Rows[$i]
        $addr = $row.Cells['Address'].Value
        if (-not $addr) { continue }
        try {
            $ok = Test-Connection -ComputerName $addr -Count 1 -Quiet -ErrorAction SilentlyContinue
            $newState = if ($ok) { 'ONLINE' } else { 'OFFLINE' }
        } catch {
            $newState = 'ERROR'
        }
        if ($row.Cells['State'].Value -ne $newState) {
            $row.Cells['State'].Value = $newState
            $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            $row.Cells['LastChange'].Value = $ts
            Add-Log "$addr -> $newState"
            # повідомлення в Telegram тільки для ONLINE/OFFLINE (не для UNKNOWN)
            if ($newState -in @('ONLINE','OFFLINE')) { Send-Telegram "$addr is $newState at $ts" }
        }
    }
})

# ---------- Кнопки ----------
$btnAdd.Add_Click({
    $a = $tbAddress.Text.Trim()
    if (-not $a) { return }
    # перевірка дублікату
    $exists = $false
    foreach ($r in $grid.Rows) { if ($r.Cells['Address'].Value -eq $a) { $exists = $true; break } }
    if ($exists) { [System.Windows.Forms.MessageBox]::Show('Address already added.'); return }
    $grid.Rows.Add($a, 'UNKNOWN', '')
    $Targets += $a
    # зберегти targets
    $Targets | ConvertTo-Json | Set-Content -Path $TargetsFile
    $tbAddress.Clear()
})

$btnRemove.Add_Click({
    if ($grid.SelectedRows.Count -eq 0) { return }
    $addr = $grid.SelectedRows[0].Cells['Address'].Value
    $grid.Rows.Remove($grid.SelectedRows[0])
    $Targets = $Targets | Where-Object { $_ -ne $addr }
    $Targets | ConvertTo-Json | Set-Content -Path $TargetsFile
})

$btnSaveSettings.Add_Click({
    # зберігаємо токен зашифрованим і chat plain
    if ($tbToken.Text.Trim()) { Save-Token -PlainToken $tbToken.Text.Trim() }
    if ($tbChat.Text.Trim()) { Save-ChatId -chat $tbChat.Text.Trim() }
    Add-Log 'Settings saved (token encrypted)'
    # очищаємо поле токена для безпеки
    $tbToken.Text = ''
})

$btnStart.Add_Click({
    if ($grid.Rows.Count -lt 1) {
        [System.Windows.Forms.MessageBox]::Show('Add at least one target')
        return
    }
    $timer.Start()
    $btnStart.Enabled = $false
    $btnStop.Enabled = $true
    $lblStatus.Text = 'Running'
    Add-Log 'Monitoring started'
})

$btnStop.Add_Click({
    $timer.Stop()
    $btnStart.Enabled = $true
    $btnStop.Enabled = $false
    $lblStatus.Text = 'Stopped'
    Add-Log 'Monitoring stopped'
})

# ---------- Закриття форми ----------
$form.Add_FormClosing({ $timer.Stop() })

# ---------- Показати форму ----------
[void]$form.ShowDialog()
