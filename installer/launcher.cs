// "ReDrawable.exe" at the top of the portable folder: starts the bundled runtime on pc\app.py.
// The runtime's own exe can't sit up here, it needs the Python DLLs beside it. build.ps1
// compiles this with the C# compiler that ships with Windows (.NET Framework 4, C# 5: no $"" strings).
//
// Before starting it:
//  - Unblocks the folder. Windows' own unzip marks every file "from the internet" (a Zone.Identifier
//    stream) when the zip was downloaded, and .NET Framework then refuses to load such DLLs
//    (pythonnet, pywebview), so the app died silently. The installer's files never carry the mark.
//  - Checks for the WebView2 runtime, which the installer adds when missing and the zip can't.
// After starting it, waits a few seconds: if the app exits with an error, says where the log is.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("ReDrawable")]
[assembly: AssemblyProduct("ReDrawable")]
[assembly: AssemblyVersion(Launcher.Version)]
[assembly: AssemblyFileVersion(Launcher.Version)]

static class Launcher
{
    public const string Version = "0.0.0.0";  // replaced by build.ps1

    const string WebView2Id = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";
    const string WebView2Url = "https://developer.microsoft.com/microsoft-edge/webview2/";

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool DeleteFileW(string path);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern uint GetFileAttributesW(string path);

    static bool Marked(string file)
    {
        return GetFileAttributesW(file + ":Zone.Identifier") != 0xFFFFFFFF;
    }

    // Removes the "from the internet" mark from every file in the folder. Cheap when there is none:
    // the runtime's own DLL is checked first, and the unzip marks all files or none.
    static void Unblock(string root, string probe)
    {
        if (!Marked(probe)) return;
        foreach (string f in Directory.GetFiles(root, "*", SearchOption.AllDirectories))
        {
            try { DeleteFileW(f + ":Zone.Identifier"); } catch { }
        }
    }

    static bool HasWebView2()
    {
        string[] keys = {
            @"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\" + WebView2Id,
            @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\EdgeUpdate\Clients\" + WebView2Id,
            @"HKEY_CURRENT_USER\Software\Microsoft\EdgeUpdate\Clients\" + WebView2Id,
        };
        foreach (string k in keys)
        {
            try
            {
                string v = Registry.GetValue(k, "pv", null) as string;
                if (!string.IsNullOrEmpty(v) && v != "0.0.0.0") return true;
            }
            catch { }
        }
        return false;
    }

    [STAThread]
    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string exe = Path.Combine(root, @"runtime\python\ReDrawable.exe");
        string app = Path.Combine(root, @"pc\app.py");
        if (!File.Exists(exe) || !File.Exists(app))
        {
            MessageBox.Show("ReDrawable's files are missing next to this program.\n\n" +
                "Unzip the whole ReDrawable-Portable zip and start ReDrawable from the unzipped folder.",
                "ReDrawable", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        try { Unblock(root, Path.Combine(root, @"runtime\python\python313.dll")); }
        catch { }  // e.g. a read-only folder: start anyway, the error check below reports a failure

        if (!HasWebView2())
        {
            DialogResult r = MessageBox.Show("ReDrawable needs Microsoft Edge WebView2, which isn't on this PC.\n\n" +
                "Open Microsoft's download page now? Install the \"Evergreen Bootstrapper\", then start ReDrawable again.\n\n" +
                "(The ReDrawable installer adds it by itself.)",
                "ReDrawable", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (r == DialogResult.Yes)
            {
                try { Process.Start(WebView2Url); } catch { }
            }
            return;
        }

        Process p = Process.Start(new ProcessStartInfo(exe, "\"" + app + "\"") { WorkingDirectory = root, UseShellExecute = false });
        // An app that started fine keeps running; one that exits with an error in the first seconds
        // failed to start (exit code 0 is a second copy handing over to the one already running).
        if (p != null && p.WaitForExit(10000) && p.ExitCode != 0)
        {
            string log = Path.Combine(root, @"data\redrawable.log");
            MessageBox.Show("ReDrawable couldn't start (error " + p.ExitCode + ").\n\n" +
                "The details are in\n" + log + "\n\nPlease include that file when you report this.",
                "ReDrawable", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
