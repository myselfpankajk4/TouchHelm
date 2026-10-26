// Compiled with the Windows .NET Framework compiler; no separately installed SDK.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using System.Reflection;
using System.Web.Script.Serialization;
#if INSTALLED
[assembly: AssemblyTitle("TouchHelm")]
#else
[assembly: AssemblyTitle("TouchHelm Portable Test")]
#endif
[assembly: AssemblyProduct("TouchHelm")]
#if INSTALLED
[assembly: AssemblyVersion("2.2.0.6")]
#else
[assembly: AssemblyVersion("2.2.0.0")]
#endif

class PortableLauncher {
#if !INSTALLED
    const string PayloadHash = "@@PAYLOAD_HASH@@";
    const long PayloadLength = @@PAYLOAD_LENGTH@@L;
#endif
    static Form preparation;
    static ProgressBar progress;
    static bool cancelled;

    [STAThread]
    static int Main(string[] args) {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Mutex appMutex = null;
        try {
            if (!Environment.Is64BitOperatingSystem)
                throw new InvalidOperationException("This test build needs 64-bit Windows 10 or Windows 11.");
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrEmpty(local)) throw new IOException("Windows LocalAppData is unavailable.");
#if INSTALLED
            string destination = Application.StartupPath;
            if (!File.Exists(Path.Combine(destination,"installed.json")) ||
                !File.Exists(Path.Combine(destination,"runtime","pythonw.exe")))
                throw new IOException("TouchHelm files are missing. Run TouchHelm Setup again to repair the installation.");
            // Guard the entire ordinary launch, including browser preparation.
            // Installer-owned preparation must remain exempt from its own guard.
            if (!args.Contains("--prepare-only"))
                appMutex = new Mutex(false, @"Local\TouchHelm.Desktop");
#else
            string packages = Path.Combine(local, "TouchHelm", "packages");
            Directory.CreateDirectory(packages);
            // Restrict extracted executables to this user and Windows SYSTEM.
            var acl = new DirectorySecurity();
            acl.SetAccessRuleProtection(true, false);
            foreach (var sid in new[] {WindowsIdentity.GetCurrent().User,
                new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null)})
                acl.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl,
                    InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                    PropagationFlags.None, AccessControlType.Allow));
            Directory.SetAccessControl(packages, acl);
            // Keep native Python module paths short even with Windows Store
            // AppData redirection. The marker still checks the full digest.
            string destination = Path.Combine(packages, PayloadHash.Substring(0,16));
            string identity = WindowsIdentity.GetCurrent().User.Value;
            using (var mutex = new Mutex(false, @"Local\TouchHelm-Package-" + identity + "-" + PayloadHash)) {
                bool held = false;
                try {
                    try { held = mutex.WaitOne(TimeSpan.FromMinutes(5)); }
                    catch (AbandonedMutexException) { held = true; }
                    if (!held) throw new IOException("Another TouchHelm copy is preparing its files. Try again shortly.");
                    if (!Ready(destination)) Extract(destination, packages);
                    if (Directory.Exists(Path.Combine(destination,"webview2")))
                        GrantRendererReadAccess(Path.Combine(destination,"webview2"));
                } finally { if (held) mutex.ReleaseMutex(); }
            }
            if (args.Contains("--extract-only")) return 0;
#endif
            if (File.Exists(Path.Combine(destination,"compact.json")) ||
                File.Exists(Path.Combine(destination,"installed.json"))) PrepareComponents(destination);
            if (args.Contains("--prepare-only")) return 0;
            bool test = args.Contains("--self-test");
            string executable = Path.Combine(destination, "runtime", test ? "python.exe" : "pythonw.exe");
            var start = new ProcessStartInfo(executable) {
                WorkingDirectory = Path.Combine(destination, "app"),
                Arguments = "-B " + Quote(Path.Combine(destination, "app", "portable_bootstrap.py")) +
                    (args.Length == 0 ? "" : " " + String.Join(" ", args.Select(Quote))),
                UseShellExecute = false, CreateNoWindow = true
            };
            start.EnvironmentVariables["TOUCHHELM_PORTABLE_ROOT"] = destination;
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables.Remove("PYTHONPATH");
#if INSTALLED
            // Inno checks this handle before setup and uninstall. Keep it alive
            // with the host, including while its window is hidden in the tray.
            using (var child = Process.Start(start)) {
                child.WaitForExit(); return child.ExitCode;
            }
#else
            using (var child = Process.Start(start)) {
                if (test) { child.WaitForExit(); return child.ExitCode; }
            }
            return 0;
#endif
        } catch (OperationCanceledException) { return 2; }
        catch (Exception error) {
            if (preparation != null) preparation.Dispose();
            MessageBox.Show("TouchHelm could not start.\n\n" + error.Message +
                "\n\nCheck available disk space and Windows security notifications. If the download is damaged, download a fresh copy.",
                "TouchHelm", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        finally { if (appMutex != null) appMutex.Dispose(); }
    }
#if !INSTALLED
    static bool Ready(string path) {
        string marker = Path.Combine(path, "package.ready");
        return File.Exists(marker) && File.ReadAllText(marker) == PayloadHash &&
            File.Exists(Path.Combine(path, "runtime", "pythonw.exe")) &&
            File.Exists(Path.Combine(path, "app", "portable_bootstrap.py")) &&
            (File.Exists(Path.Combine(path, "compact.json")) ||
             File.Exists(Path.Combine(path, "webview2", "msedgewebview2.exe")));
    }
#endif
    static void PrepareComponents(string destination) {
        string suffix=Guid.NewGuid().ToString("N");
        string data=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"TouchHelm");
        Directory.CreateDirectory(data);
        string status=Path.Combine(data,"setup-status-"+suffix+".json");
        string cancel=Path.Combine(data,"setup-cancel-"+suffix);
        bool installed=File.Exists(Path.Combine(destination,"installed.json"));
        string message="Preparing TouchHelm for this PC…";
        var start=new ProcessStartInfo(Path.Combine(destination,"runtime","python.exe")) {
            WorkingDirectory=Path.Combine(destination,"app"),UseShellExecute=false,CreateNoWindow=true,
            Arguments="-B "+Quote(Path.Combine(destination,"app","portable_setup.py"))+" --progress "+Quote(status)+" --cancel "+Quote(cancel)+(installed?" --browser-only":"")
        };
        start.EnvironmentVariables.Remove("PYTHONHOME");start.EnvironmentVariables.Remove("PYTHONPATH");
        start.EnvironmentVariables["TOUCHHELM_PORTABLE_ROOT"]=destination;
        start.EnvironmentVariables["PYTHONUTF8"]="1";
        var clock=Stopwatch.StartNew(); DateTime? cancelledAt=null;
        try {
            using(var process=Process.Start(start)) {
                while(!process.WaitForExit(100)) {
                    ReadSetupMessage(status,ref message);
                    if(preparation==null && clock.ElapsedMilliseconds>1200) {
                        preparation=new Form {Text="Preparing TouchHelm",Width=520,Height=210,
                            FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false,
                            StartPosition=FormStartPosition.CenterScreen,Font=new Font("Segoe UI",10)};
                        preparation.Controls.Add(new Label {Name="setupMessage",Text=message,Left=24,Top=24,Width=460,Height=50});
                        preparation.Controls.Add(new Label {Text=installed?
                            "Checking the Windows browser runtime.\nAny missing Microsoft component is prepared automatically.":
                            "First launch downloads missing components automatically.\nKeep this PC connected to the internet.",Left=24,Top=94,Width=460,Height=45,ForeColor=SystemColors.GrayText});
                        progress=new ProgressBar {Left=24,Top=76,Width=450,Height=8,Style=ProgressBarStyle.Marquee};
                        preparation.Controls.Add(progress);
                        preparation.FormClosing+=(s,e)=>{cancelled=true;};preparation.Show();
                    }
                    if(preparation!=null && !preparation.IsDisposed)
                        preparation.Controls["setupMessage"].Text=message;
                    Application.DoEvents();
                    if(cancelled && cancelledAt==null) {File.WriteAllText(cancel,"");cancelledAt=DateTime.UtcNow;}
                    if(cancelledAt!=null && (DateTime.UtcNow-cancelledAt.Value).TotalSeconds>35) {
                        process.Kill();process.WaitForExit();throw new OperationCanceledException();
                    }
                }
                ReadSetupMessage(status,ref message);
                if(cancelled || process.ExitCode==2)throw new OperationCanceledException();
                if(process.ExitCode!=0)throw new IOException(message+"\n\nOpen the same EXE again to retry. Your settings are preserved.");
            }
        } finally {
            if(preparation!=null){preparation.Dispose();preparation=null;}
            if(File.Exists(status))File.Delete(status);if(File.Exists(cancel))File.Delete(cancel);
        }
    }
    static void ReadSetupMessage(string path,ref string message) {
        try {
            if(!File.Exists(path))return;
            var data=new JavaScriptSerializer().DeserializeObject(File.ReadAllText(path)) as System.Collections.Generic.Dictionary<string,object>;
            if(data!=null && data.ContainsKey("message"))message=Convert.ToString(data["message"]);
        } catch(IOException) {} catch(ArgumentException) {}
    }
    static void GrantRendererReadAccess(string runtime) {
        // Microsoft requires these read/execute grants for Fixed Version >=120
        // on Windows 10. Apply only to public browser runtime files, not settings.
        var acl = Directory.GetAccessControl(runtime);
        foreach (string sid in new[] {"S-1-15-2-1", "S-1-15-2-2"})
            acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(sid),
                FileSystemRights.ReadAndExecute, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None, AccessControlType.Allow));
        Directory.SetAccessControl(runtime,acl);
    }
#if !INSTALLED
    static void Tick(int value) {
        progress.Value = Math.Max(0, Math.Min(100, value));
        Application.DoEvents();
        if (cancelled) throw new OperationCanceledException();
    }
    static void Extract(string destination, string parent) {
        preparation = new Form {Text="Preparing TouchHelm", Width=460, Height=180,
            FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false,
            StartPosition=FormStartPosition.CenterScreen, Font=new Font("Segoe UI", 10)};
        var label = new Label {Text="Preparing this PC for the first launch…\nThis only happens once for each test version.",
            Left=24, Top=22, Width=400, Height=54};
        progress = new ProgressBar {Left=24, Top=88, Width=390, Height=10};
        preparation.Controls.Add(label); preparation.Controls.Add(progress);
        preparation.FormClosing += (s,e) => { cancelled = true; };
        preparation.Show();
        string staging = Path.Combine(parent, ".preparing-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try {
            string archive = Path.Combine(staging, "payload.zip");
            using (var source = File.OpenRead(Application.ExecutablePath))
            using (var target = new FileStream(archive, FileMode.CreateNew))
            using (var sha = SHA256.Create()) {
                if (source.Length <= PayloadLength) throw new IOException("Incomplete portable EXE.");
                source.Seek(-PayloadLength, SeekOrigin.End);
                var buffer = new byte[1024*1024]; long remaining=PayloadLength;
                while (remaining > 0) {
                    int count=source.Read(buffer, 0, (int)Math.Min(remaining, buffer.Length));
                    if (count==0) throw new IOException("Incomplete portable payload.");
                    target.Write(buffer,0,count); sha.TransformBlock(buffer,0,count,null,0); remaining-=count;
                    Tick((int)((PayloadLength-remaining)*25/PayloadLength));
                }
                sha.TransformFinalBlock(new byte[0],0,0);
                string digest=BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                if (digest != PayloadHash) throw new IOException("The portable payload failed its SHA-256 integrity check.");
            }
            using (var zip=ZipFile.OpenRead(archive)) {
                long total=zip.Entries.Sum(x=>x.Length), done=0;
                string prefix=Path.GetFullPath(staging)+Path.DirectorySeparatorChar;
                foreach (var entry in zip.Entries) {
                    if (entry.FullName.Contains(":") || entry.FullName.Contains("\\") ||
                        ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                        throw new IOException("Invalid portable archive entry.");
                    string path=Path.GetFullPath(Path.Combine(staging,entry.FullName));
                    if (!path.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))
                        throw new IOException("Invalid portable archive path.");
                    if (entry.FullName.EndsWith("/")) Directory.CreateDirectory(path);
                    else {
                        Directory.CreateDirectory(Path.GetDirectoryName(path));
                        using (var input=entry.Open())
                        using (var output=new FileStream(path,FileMode.CreateNew)) {
                            var buffer=new byte[1024*1024]; int count;
                            while ((count=input.Read(buffer,0,buffer.Length))>0) {
                                output.Write(buffer,0,count); done+=count;
                                Tick(25+(int)(done*74/Math.Max(1,total)));
                            }
                        }
                    }
                }
            }
            File.Delete(archive);
            File.WriteAllText(Path.Combine(staging,"package.ready"),PayloadHash);
            if (Directory.Exists(destination)) {
                // Preserve an incomplete earlier cache rather than deleting user files.
                Directory.Move(destination,destination+".incomplete-"+Guid.NewGuid().ToString("N"));
            }
            Directory.Move(staging,destination);
            preparation.Dispose(); preparation=null;
        } finally {
            // Only our randomly named, verified child of packages may be removed.
            string full=Path.GetFullPath(staging);
            if (full.StartsWith(Path.GetFullPath(parent)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)
                && Path.GetFileName(full).StartsWith(".preparing-") && Directory.Exists(full))
                Directory.Delete(full,true);
            if (preparation!=null) {preparation.Dispose(); preparation=null;}
        }
    }
#endif
    static string Quote(string value) {
        var result = new StringBuilder("\""); int slashes=0;
        foreach (char c in value) {
            if (c=='\\') {slashes++; continue;}
            if (c=='\"') {result.Append('\\',slashes*2+1); result.Append(c);}
            else {result.Append('\\',slashes); result.Append(c);}
            slashes=0;
        }
        result.Append('\\',slashes*2); return result.Append('"').ToString();
    }
}
