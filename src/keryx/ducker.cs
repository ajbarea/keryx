// Lowers other apps' volume while keryx speaks, through Core Audio's per-app volume
// (ISimpleAudioVolume on each audio session, on every active output device). What it
// changed is written to a state file before it changes anything, so a crashed player's
// successor can put the volumes back.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxDeviceEnumerator {
    int EnumAudioEndpoints(int dataFlow, int stateMask, out IKeryxDeviceCollection devices);
}

[Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxDeviceCollection {
    int GetCount(out uint count);
    int Item(uint index, out IKeryxDevice device);
}

[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxDevice {
    int Activate(ref Guid iid, int clsCtx, IntPtr activationParams,
                 [MarshalAs(UnmanagedType.IUnknown)] out object iface);
}

[Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxSessionManager2 {
    int GetAudioSessionControl(IntPtr guid, int flags, out IntPtr control);
    int GetSimpleAudioVolume(IntPtr guid, int flags, out IntPtr volume);
    int GetSessionEnumerator(out IKeryxSessionEnumerator sessions);
}

[Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxSessionEnumerator {
    int GetCount(out int count);
    int GetSession(int index, out IKeryxSessionControl2 session);
}

[Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxSessionControl2 {
    int GetState(out int state);
    int GetDisplayName(out IntPtr name);
    int SetDisplayName(string name, ref Guid ctx);
    int GetIconPath(out IntPtr path);
    int SetIconPath(string path, ref Guid ctx);
    int GetGroupingParam(out Guid param);
    int SetGroupingParam(ref Guid param, ref Guid ctx);
    int RegisterAudioSessionNotification(IntPtr client);
    int UnregisterAudioSessionNotification(IntPtr client);
    int GetSessionIdentifier(out IntPtr id);
    int GetSessionInstanceIdentifier(out IntPtr id);
    int GetProcessId(out uint pid);
}

[Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IKeryxSimpleVolume {
    int SetMasterVolume(float level, ref Guid ctx);
    int GetMasterVolume(out float level);
}

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class KeryxDeviceEnumerator {}

public static class KeryxDucker {
    static Guid ctx = Guid.Empty;

    class Session {
        public string Id;  // the session instance id, unique per session even within one app
        public IKeryxSimpleVolume Volume;
    }

    static string ProcessName(uint pid) {
        try {
            using (var p = System.Diagnostics.Process.GetProcessById((int)pid)) return p.ProcessName;
        } catch { return null; }
    }

    // Audio sessions on every active output device, filtered by process name unless `apps` is
    // null; null when the devices cannot be listed at all.
    static List<Session> Sessions(ICollection<string> apps) {
        var found = new List<Session>();
        var en = (IKeryxDeviceEnumerator)new KeryxDeviceEnumerator();
        IKeryxDeviceCollection devices;
        if (en.EnumAudioEndpoints(0, 1, out devices) != 0) return null;  // eRender, ACTIVE
        uint count;
        devices.GetCount(out count);
        for (uint d = 0; d < count; d++) {
            IKeryxDevice dev;
            if (devices.Item(d, out dev) != 0) continue;
            Guid iid = typeof(IKeryxSessionManager2).GUID;
            object manager;
            if (dev.Activate(ref iid, 23, IntPtr.Zero, out manager) != 0) continue;  // CLSCTX_ALL
            IKeryxSessionEnumerator sessions;
            if (((IKeryxSessionManager2)manager).GetSessionEnumerator(out sessions) != 0) continue;
            int n;
            sessions.GetCount(out n);
            for (int i = 0; i < n; i++) {
                IKeryxSessionControl2 control;
                if (sessions.GetSession(i, out control) != 0) continue;
                uint pid;
                control.GetProcessId(out pid);
                bool wanted = apps == null;
                if (!wanted) {
                    string name = ProcessName(pid);
                    foreach (var app in apps)
                        if (name != null && string.Equals(name, app.Trim(), StringComparison.OrdinalIgnoreCase))
                            wanted = true;
                }
                IntPtr raw;
                if (!wanted || control.GetSessionInstanceIdentifier(out raw) != 0) {
                    Marshal.ReleaseComObject(control);
                    continue;
                }
                string id = Marshal.PtrToStringUni(raw);
                Marshal.FreeCoTaskMem(raw);
                found.Add(new Session { Id = id, Volume = (IKeryxSimpleVolume)control });
            }
            Marshal.ReleaseComObject(sessions);
            Marshal.ReleaseComObject(manager);
            Marshal.ReleaseComObject(dev);
        }
        Marshal.ReleaseComObject(devices);
        Marshal.ReleaseComObject(en);
        return found;
    }

    static void Release(List<Session> sessions) {
        foreach (var s in sessions) Marshal.ReleaseComObject(s.Volume);
    }

    // Lowers each matching session to ratio x its volume. State lines: id TAB original TAB ducked.
    public static int Duck(string statePath, string appList, float ratio) {
        if (File.Exists(statePath)) return 0;  // already ducked
        var targets = Sessions(appList.Split(','));
        if (targets == null || targets.Count == 0) return 0;
        var levels = new float[targets.Count];
        var lines = new string[targets.Count];
        for (int i = 0; i < targets.Count; i++) {
            targets[i].Volume.GetMasterVolume(out levels[i]);
            lines[i] = string.Format(CultureInfo.InvariantCulture, "{0}\t{1}\t{2}",
                                     targets[i].Id, levels[i], levels[i] * ratio);
        }
        File.WriteAllLines(statePath, lines);
        for (int i = 0; i < targets.Count; i++)
            targets[i].Volume.SetMasterVolume(levels[i] * ratio, ref ctx);
        Release(targets);
        return targets.Count;
    }

    // Puts back what the state file records, unless the user changed a volume meanwhile.
    // Keeps the file when the devices cannot be listed, so a later call can still restore.
    public static int Unduck(string statePath) {
        if (!File.Exists(statePath)) return 0;
        var saved = new Dictionary<string, float[]>();
        foreach (var line in File.ReadAllLines(statePath)) {
            var f = line.Split('\t');
            float original, ducked;
            if (f.Length == 3
                && float.TryParse(f[1], NumberStyles.Float, CultureInfo.InvariantCulture, out original)
                && float.TryParse(f[2], NumberStyles.Float, CultureInfo.InvariantCulture, out ducked))
                saved[f[0]] = new[] { original, ducked };
        }
        var sessions = Sessions(null);
        if (sessions == null) return -1;
        int restored = 0;
        foreach (var s in sessions) {
            float[] v;
            if (!saved.TryGetValue(s.Id, out v)) continue;
            float now;
            s.Volume.GetMasterVolume(out now);
            if (Math.Abs(now - v[1]) > 0.01f) continue;  // changed by hand: the user's choice stands
            s.Volume.SetMasterVolume(v[0], ref ctx);
            restored++;
        }
        Release(sessions);
        File.Delete(statePath);
        return restored;
    }
}
