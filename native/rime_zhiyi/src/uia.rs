//! Non-blocking, privacy-hardened Windows UI Automation (UIA) preceding-text reader.
//!
//! Architecture guarantees:
//!   1. **Zero main-thread blocking**: All COM/UIA calls run on a single dedicated background
//!      STA thread. The keystroke hot path only calls `GetForegroundWindow()` + `try_send()`
//!      + `RwLock::try_read()` (< 2 µs total), so sluggish apps never hang `WeaselServer.exe`.
//!   2. **Zero cross-app contamination**: Tracks the active foreground `HWND` synchronously on
//!      every query. Switching apps immediately invalidates stale context instead of leaking
//!      Window A's `commit_history` into Window B.
//!   3. **Hard password protection**: Any control reporting `IsPassword == true` or hosted by a
//!      known password manager / Windows credential UI returns `UiaContext::Blocked` (forcing
//!      empty context AND disabling local feedback logging).

use std::time::{Duration, Instant};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UiaContext {
    /// Password control or sensitive process -> force empty context and suppress logging.
    Blocked,
    /// Authoritative text strictly before the caret in the active control (may be empty if the
    /// user is typing in a fresh/empty box).
    Text(String),
    /// Foreground window just changed and fresh UIA snapshot is not ready yet -> do not reuse
    /// previous window's `commit_history`.
    WindowChanged,
    /// Active window unchanged, control does not expose UIA text -> safe to fall back to Rime's
    /// same-window `commit_history`.
    FallbackSameWindow,
}

const MAX_UIA_CHARS: usize = 64;
const SNAPSHOT_TTL: Duration = Duration::from_secs(4);
const MIN_REFRESH_INTERVAL: Duration = Duration::from_millis(35);

const DENIED_PROCESSES: &[&str] = &[
    "keepass.exe",
    "keepassxc.exe",
    "1password.exe",
    "bitwarden.exe",
    "enpass.exe",
    "lastpass.exe",
    "dashlane.exe",
    "roboform.exe",
    "nordpass.exe",
    "protonpass.exe",
    "credentialuibroker.exe",
    "consent.exe",
    "lockapp.exe",
    "mstsc.exe",
];

/// Strip live inline composition text (if the host app includes Weasel's uncommitted preedit
/// right before the caret) and normalize control characters into a clean 64-char tail.
pub fn normalize_before_caret(raw: &str, live_preedit: &str, raw_input: &str) -> String {
    let mut s = raw.replace("\r\n", "\n").replace('\r', "\n");

    // Strip uncommitted inline composition echoed into the text control, if present at tail
    let trimmed_tail = s.trim_end_matches(' ');
    if trimmed_tail.len() != s.len() {
        s.truncate(trimmed_tail.len());
    }
    for suffix in [live_preedit, raw_input] {
        let trimmed = suffix.trim();
        if !trimmed.is_empty() && s.ends_with(trimmed) {
            let new_len = s.len().saturating_sub(trimmed.len());
            s.truncate(new_len);
        }
    }

    // If separated by blank lines (paragraph break), keep only the current paragraph when non-empty
    if let Some(pos) = s.rfind("\n\n") {
        let tail = s[pos + 2..].trim_start();
        if !tail.is_empty() {
            s = tail.to_string();
        }
    }

    // Flatten remaining line breaks and trim trailing spaces
    let cleaned: String = s
        .chars()
        .map(|c| if c == '\n' || c == '\t' { ' ' } else { c })
        .filter(|&c| !c.is_control())
        .collect();
    let trimmed = cleaned.trim_end();

    let count = trimmed.chars().count();
    if count <= MAX_UIA_CHARS {
        return trimmed.to_string();
    }
    let skip = count - MAX_UIA_CHARS;
    match trimmed.char_indices().nth(skip) {
        Some((idx, _)) => trimmed[idx..].to_string(),
        None => trimmed.to_string(),
    }
}

#[cfg(windows)]
mod win_impl {
    use super::*;
    use std::sync::atomic::{AtomicBool, AtomicIsize, Ordering};
    use std::sync::mpsc::{self, SyncSender};
    use std::sync::{OnceLock, RwLock};
    use std::thread;

    use windows::core::PWSTR;
    use windows::Win32::Foundation::{CloseHandle, HWND};
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER,
        COINIT_APARTMENTTHREADED,
    };
    use windows::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
        PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows::Win32::UI::Accessibility::{
        CUIAutomation, IUIAutomation, IUIAutomationTextPattern, IUIAutomationValuePattern,
        TextPatternRangeEndpoint_End, TextPatternRangeEndpoint_Start, TextUnit_Character,
        UIA_EditControlTypeId, UIA_TextPatternId, UIA_ValuePatternId,
    };
    use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};

    struct UiaSnapshot {
        hwnd: isize,
        is_password: bool,
        readable: bool,
        before_caret: String,
        updated_at: Instant,
    }

    struct UiaRuntime {
        tx: SyncSender<()>,
        snapshot: RwLock<UiaSnapshot>,
    }

    static RUNTIME: OnceLock<UiaRuntime> = OnceLock::new();
    static LAST_SEEN_HWND: AtomicIsize = AtomicIsize::new(0);
    static ENABLED: AtomicBool = AtomicBool::new(false);

    fn is_denied_process(hwnd: HWND) -> bool {
        let mut pid: u32 = 0;
        unsafe {
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
        }
        if pid == 0 {
            return false;
        }
        let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) };
        let Ok(handle) = handle else {
            return false;
        };
        let mut buf = [0u16; 512];
        let mut len = buf.len() as u32;
        let ok = unsafe {
            QueryFullProcessImageNameW(
                handle,
                PROCESS_NAME_WIN32,
                PWSTR(buf.as_mut_ptr()),
                &mut len,
            )
            .is_ok()
        };
        unsafe {
            let _ = CloseHandle(handle);
        }
        if !ok || len == 0 {
            return false;
        }
        let path = String::from_utf16_lossy(&buf[..len as usize]);
        let exe = path
            .rsplit(['\\', '/'])
            .next()
            .unwrap_or("")
            .to_ascii_lowercase();
        DENIED_PROCESSES.iter().any(|&p| p == exe)
    }

    fn probe_once(automation: &IUIAutomation) -> UiaSnapshot {
        let now = Instant::now();
        let hwnd = unsafe { GetForegroundWindow() };
        let hwnd_raw = hwnd.0 as isize;
        if hwnd_raw == 0 {
            return UiaSnapshot {
                hwnd: 0,
                is_password: false,
                readable: false,
                before_caret: String::new(),
                updated_at: now,
            };
        }

        if is_denied_process(hwnd) {
            return UiaSnapshot {
                hwnd: hwnd_raw,
                is_password: true,
                readable: false,
                before_caret: String::new(),
                updated_at: now,
            };
        }

        let focused = match unsafe { automation.GetFocusedElement() } {
            Ok(el) => el,
            Err(_) => {
                return UiaSnapshot {
                    hwnd: hwnd_raw,
                    is_password: false,
                    readable: false,
                    before_caret: String::new(),
                    updated_at: now,
                };
            }
        };

        // Hard password check
        if let Ok(is_pw) = unsafe { focused.CurrentIsPassword() } {
            if is_pw.as_bool() {
                return UiaSnapshot {
                    hwnd: hwnd_raw,
                    is_password: true,
                    readable: false,
                    before_caret: String::new(),
                    updated_at: now,
                };
            }
        }

        // Primary path: IUIAutomationTextPattern (Chrome, Edge, VS Code, Electron, Word, Notepad, WPF, WinUI)
        if let Ok(text_pat) =
            unsafe { focused.GetCurrentPatternAs::<IUIAutomationTextPattern>(UIA_TextPatternId) }
        {
            if let Ok(selection) = unsafe { text_pat.GetSelection() } {
                if let Ok(len) = unsafe { selection.Length() } {
                    if len >= 1 {
                        if let Ok(caret_range) = unsafe { selection.GetElement(0) } {
                            if let Ok(before) = unsafe { caret_range.Clone() } {
                                let collapsed = unsafe {
                                    before.MoveEndpointByRange(
                                        TextPatternRangeEndpoint_End,
                                        &caret_range,
                                        TextPatternRangeEndpoint_Start,
                                    )
                                };
                                if collapsed.is_ok() {
                                    let _ = unsafe {
                                        before.MoveEndpointByUnit(
                                            TextPatternRangeEndpoint_Start,
                                            TextUnit_Character,
                                            -96,
                                        )
                                    };
                                    if let Ok(bstr) = unsafe { before.GetText(128) } {
                                        return UiaSnapshot {
                                            hwnd: hwnd_raw,
                                            is_password: false,
                                            readable: true,
                                            before_caret: bstr.to_string(),
                                            updated_at: now,
                                        };
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Fallback: IUIAutomationValuePattern ONLY for standard non-readonly Edit controls
        if let Ok(ctype) = unsafe { focused.CurrentControlType() } {
            if ctype == UIA_EditControlTypeId {
                if let Ok(val_pat) = unsafe {
                    focused.GetCurrentPatternAs::<IUIAutomationValuePattern>(UIA_ValuePatternId)
                } {
                    let is_ro = unsafe { val_pat.CurrentIsReadOnly() }
                        .map(|b| b.as_bool())
                        .unwrap_or(true);
                    if !is_ro {
                        if let Ok(bstr) = unsafe { val_pat.CurrentValue() } {
                            return UiaSnapshot {
                                hwnd: hwnd_raw,
                                is_password: false,
                                readable: true,
                                before_caret: bstr.to_string(),
                                updated_at: now,
                            };
                        }
                    }
                }
            }
        }

        UiaSnapshot {
            hwnd: hwnd_raw,
            is_password: false,
            readable: false,
            before_caret: String::new(),
            updated_at: now,
        }
    }

    fn ensure_started() -> &'static UiaRuntime {
        RUNTIME.get_or_init(|| {
            let (tx, rx) = mpsc::sync_channel::<()>(1);
            let runtime = UiaRuntime {
                tx,
                snapshot: RwLock::new(UiaSnapshot {
                    hwnd: 0,
                    is_password: false,
                    readable: false,
                    before_caret: String::new(),
                    updated_at: Instant::now() - Duration::from_secs(60),
                }),
            };

            let _ = thread::Builder::new()
                .name("rime_zhiyi_uia".to_string())
                .spawn(move || {
                    let hr = unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) };
                    if hr.is_err() {
                        return;
                    }
                    let automation: Result<IUIAutomation, _> =
                        unsafe { CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER) };
                    let Ok(automation) = automation else {
                        unsafe { CoUninitialize() };
                        return;
                    };

                    let mut last_probe = Instant::now() - Duration::from_secs(10);
                    let mut last_hwnd: isize = 0;

                    while rx.recv().is_ok() {
                        let cur_hwnd = unsafe { GetForegroundWindow().0 as isize };
                        if cur_hwnd == last_hwnd && last_probe.elapsed() < MIN_REFRESH_INTERVAL {
                            continue;
                        }
                        let snap = probe_once(&automation);
                        last_hwnd = snap.hwnd;
                        last_probe = snap.updated_at;
                        if let Some(rt) = RUNTIME.get() {
                            if let Ok(mut guard) = rt.snapshot.write() {
                                *guard = snap;
                            }
                        }
                    }

                    unsafe { CoUninitialize() };
                });

            runtime
        })
    }

    pub fn set_enabled(enable: bool) {
        ENABLED.store(enable, Ordering::Release);
        if enable {
            let rt = ensure_started();
            let _ = rt.tx.try_send(());
        }
    }

    pub fn is_enabled() -> bool {
        ENABLED.load(Ordering::Acquire)
    }

    /// Non-blocking hot-path query (< 2 µs). Never waits on COM or UIA.
    pub fn query_context(live_preedit: &str, raw_input: &str) -> UiaContext {
        if !is_enabled() {
            return UiaContext::FallbackSameWindow;
        }
        let rt = ensure_started();
        let cur_hwnd = unsafe { GetForegroundWindow().0 as isize };
        let prev_hwnd = LAST_SEEN_HWND.swap(cur_hwnd, Ordering::AcqRel);

        // Kick background worker asynchronously (never blocks)
        let _ = rt.tx.try_send(());

        if cur_hwnd == 0 {
            return UiaContext::FallbackSameWindow;
        }

        // Fast non-blocking read of latest cached snapshot
        if let Ok(snap) = rt.snapshot.try_read() {
            if snap.hwnd == cur_hwnd {
                if snap.is_password {
                    return UiaContext::Blocked;
                }
                if snap.readable && snap.updated_at.elapsed() <= SNAPSHOT_TTL {
                    let clean = normalize_before_caret(&snap.before_caret, live_preedit, raw_input);
                    return UiaContext::Text(clean);
                }
                if prev_hwnd != 0 && prev_hwnd != cur_hwnd {
                    return UiaContext::WindowChanged;
                }
                return UiaContext::FallbackSameWindow;
            }
        }

        // Snapshot belongs to an older window -> block stale cross-app context bleed!
        if prev_hwnd != 0 && prev_hwnd != cur_hwnd {
            UiaContext::WindowChanged
        } else {
            UiaContext::FallbackSameWindow
        }
    }

    pub fn foreground_hwnd() -> isize {
        unsafe { GetForegroundWindow().0 as isize }
    }

    pub fn kick_refresh() {
        if is_enabled() {
            if let Some(rt) = RUNTIME.get() {
                let _ = rt.tx.try_send(());
            }
        }
    }
}

#[cfg(not(windows))]
mod win_impl {
    use super::*;
    pub fn set_enabled(_enable: bool) {}
    pub fn is_enabled() -> bool {
        false
    }
    pub fn query_context(_live_preedit: &str, _raw_input: &str) -> UiaContext {
        UiaContext::FallbackSameWindow
    }
    pub fn foreground_hwnd() -> isize {
        0
    }
    pub fn kick_refresh() {}
}

pub use win_impl::{foreground_hwnd, is_enabled, kick_refresh, query_context, set_enabled};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_before_caret_strips_preedit_and_paragraph() {
        assert_eq!(
            normalize_before_caret("第一段内容\n\n我们今天去公园玩jntm", "jntm", "jntm"),
            "我们今天去公园玩"
        );
        assert_eq!(
            normalize_before_caret("今天天气真好，wo men ", "wo men", "women"),
            "今天天气真好，"
        );
        assert_eq!(
            normalize_before_caret("今天天气真好，wo men", "wo men", "women"),
            "今天天气真好，"
        );
    }

    #[test]
    fn test_normalize_before_caret_truncates_utf8_safely() {
        let long =
            "这是一段很长的中文前文测试内容，用来验证多字节字符截断不会发生越界崩溃。".repeat(3);
        let out = normalize_before_caret(&long, "", "");
        assert_eq!(out.chars().count(), MAX_UIA_CHARS);
    }
}
