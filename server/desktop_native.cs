using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

// Private provider boundary. None of these methods accepts a phone path or HWND.
public static class TouchHelmNative {
    public class Window {
        public long handle; public uint pid; public string title, exe, aumid, identity;
    }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int left, top, right, bottom; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct Monitor {
        public int cbSize; public Rect monitor, work; public uint flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string device;
    }
    [StructLayout(LayoutKind.Sequential)] struct PropertyKey { public Guid fmtid; public uint pid; }
    [StructLayout(LayoutKind.Explicit, Size=24)] struct PropVariant {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr pointer;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface PropertyStore {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }
    [StructLayout(LayoutKind.Sequential)] struct Size { public int x, y; }
    [ComImport, Guid("BCC18B79-BA16-442F-80C4-8A59C30C463B"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ImageFactory { [PreserveSig] int GetImage(Size size, uint flags, out IntPtr bitmap); }
    delegate bool EnumWindow(IntPtr hwnd, IntPtr data);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindow callback, IntPtr data);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll", SetLastError=true)] static extern bool PostMessage(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr hwnd, uint command);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hwnd, int state);
    [DllImport("user32.dll")] public static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool GetMonitorInfo(IntPtr handle, ref Monitor info);
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr handle, uint flags, StringBuilder name, ref uint size);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern int GetApplicationUserModelId(IntPtr handle, ref uint size, StringBuilder id);
    [DllImport("shell32.dll")] static extern int SHGetPropertyStoreForWindow(IntPtr hwnd, ref Guid iid, out PropertyStore store);
    [DllImport("ole32.dll")] static extern int PropVariantClear(ref PropVariant value);
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)] static extern int SHCreateItemFromParsingName(string name, IntPtr bind, ref Guid iid, out ImageFactory item);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr bitmap);

    static string WindowId(IntPtr hwnd) {
        PropertyStore store = null; PropVariant value = new PropVariant();
        try {
            Guid iid = typeof(PropertyStore).GUID;
            if (SHGetPropertyStoreForWindow(hwnd, ref iid, out store) != 0) return "";
            PropertyKey key = new PropertyKey {fmtid=new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),pid=5};
            if (store.GetValue(ref key, out value) == 0 && value.type == 31)
                return Marshal.PtrToStringUni(value.pointer) ?? "";
        } catch {} finally { PropVariantClear(ref value); if (store != null) Marshal.ReleaseComObject(store); }
        return "";
    }
    public static Window[] Windows() {
        List<Window> result = new List<Window>();
        EnumWindows(delegate(IntPtr hwnd, IntPtr unused) {
            if (!IsWindowVisible(hwnd) || GetWindow(hwnd,4) != IntPtr.Zero) return true;
            StringBuilder title = new StringBuilder(2048); GetWindowText(hwnd,title,title.Capacity);
            if (title.Length == 0) return true;
            uint pid; GetWindowThreadProcessId(hwnd,out pid);
            string exe="", appId=WindowId(hwnd), started="";
            IntPtr process=OpenProcess(0x1000,false,pid);
            try {
                if (process != IntPtr.Zero) {
                    uint size=32768; StringBuilder path=new StringBuilder((int)size);
                    if (QueryFullProcessImageName(process,0,path,ref size)) exe=path.ToString();
                    if (appId.Length == 0) {
                        size=1024; StringBuilder id=new StringBuilder((int)size);
                        if (GetApplicationUserModelId(process,ref size,id)==0) appId=id.ToString();
                    }
                }
                try { started=System.Diagnostics.Process.GetProcessById((int)pid).StartTime.ToUniversalTime().Ticks.ToString(); } catch {}
            } finally { if (process != IntPtr.Zero) CloseHandle(process); }
            result.Add(new Window {handle=hwnd.ToInt64(),pid=pid,title=title.ToString(),exe=exe,aumid=appId,
                identity=pid+":"+started+":"+hwnd.ToInt64()+":"+appId+":"+exe});
            return true;
        },IntPtr.Zero);
        return result.ToArray();
    }
    public static bool Focus(long handle) {
        IntPtr hwnd=new IntPtr(handle);
        if (IsIconic(hwnd)) ShowWindow(hwnd,9);
        return SetForegroundWindow(hwnd);
    }
    public static bool PostClose(long handle, uint expectedPid) {
        IntPtr hwnd = new IntPtr(handle);
        uint actualPid;
        if (handle == 0 || expectedPid == 0 || !IsWindow(hwnd) ||
            GetWindowThreadProcessId(hwnd, out actualPid) == 0 || actualPid != expectedPid)
            return false;
        // WM_CLOSE lets the application show its normal save/discard dialog.
        // Posting confirms delivery only; the caller checks disappearance later.
        return PostMessage(hwnd, 0x0010, IntPtr.Zero, IntPtr.Zero);
    }
    public static string ShellIcon(string appId) {
        ImageFactory factory=null; IntPtr bitmap=IntPtr.Zero;
        try {
            Guid iid=typeof(ImageFactory).GUID;
            if (SHCreateItemFromParsingName("shell:AppsFolder\\"+appId,IntPtr.Zero,ref iid,out factory)!=0) return null;
            if (factory.GetImage(new Size {x=64,y=64},4,out bitmap)!=0) return null;
            using(Bitmap image=Image.FromHbitmap(bitmap)) using(MemoryStream stream=new MemoryStream()) {
                image.Save(stream,ImageFormat.Png); return Convert.ToBase64String(stream.ToArray());
            }
        } catch { return null; }
        finally { if(bitmap!=IntPtr.Zero) DeleteObject(bitmap); if(factory!=null) Marshal.ReleaseComObject(factory); }
    }
}
