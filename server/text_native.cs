using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Automation;
using System.Windows.Automation.Text;

// This helper runs outside the desktop process: an unresponsive accessibility
// provider can be killed without blocking input, capture, media or the UI.
public static class TouchHelmFocusedText {
    static readonly string salt = Guid.NewGuid().ToString();
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    static AutomationElement lastTarget;
    static IntPtr lastWindow;
    [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public UNION u; }
    [StructLayout(LayoutKind.Explicit)] struct UNION {
        [FieldOffset(0)] public KEYBOARD key;
        [FieldOffset(0)] public MOUSE mouse;
    }
    [StructLayout(LayoutKind.Sequential)] struct KEYBOARD { public ushort vk, scan; public uint flags, time; public UIntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSE { public int x,y; public uint data,flags,time; public UIntPtr extra; }
    static string Hash(string value) {
        using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(salt+value))).Replace("-", "");
    }
    static string Normalize(string value) { return value.Replace("\r\n", "\n").Replace("\r", "\n"); }
    static Dictionary<string,object> Missing(string message) { return new Dictionary<string,object>{{"available",false},{"message",message}}; }
    static AutomationElement Focused() {
        var element = AutomationElement.FocusedElement;
        if (element == null) return null;
        var c = element.Current;
        if (c.IsPassword || !c.IsEnabled || c.IsOffscreen || !c.HasKeyboardFocus ||
            (c.ControlType != ControlType.Edit && c.ControlType != ControlType.Document)) return null;
        uint pid; GetWindowThreadProcessId(GetForegroundWindow(), out pid);
        if (pid != c.ProcessId) return null;
        // Some providers put protected state on a parent of the editable node.
        var parent = element;
        for(int i=0;i<6 && parent!=null;i++) {
            if(parent.Current.IsPassword) return null;
            parent = TreeWalker.ControlViewWalker.GetParent(parent);
        }
        return element;
    }
    static bool Content(AutomationElement e, out string text, out ValuePattern value, out TextPattern pattern) {
        object p; text="";value=null;pattern=null;
        if (e.TryGetCurrentPattern(ValuePattern.Pattern,out p)) {
            value=(ValuePattern)p;
            if(value.Current.IsReadOnly)return false;
            text=value.Current.Value;
        } else if(e.TryGetCurrentPattern(TextPattern.Pattern,out p)) {
            pattern=(TextPattern)p;
            // A browser article/document is not an editable text field.
            var readOnly=pattern.DocumentRange.GetAttributeValue(TextPattern.IsReadOnlyAttribute);
            if(!(readOnly is bool) || (bool)readOnly)return false;
            text=pattern.DocumentRange.GetText(10001);
        } else return false;
        return text.Length<=10000;
    }
    static string Identity(AutomationElement e) { return Hash(e.Current.ProcessId+":"+String.Join(",",e.GetRuntimeId())); }
    public static Dictionary<string,object> Target() {
        var e=Focused();object p;bool editable=false;
        if(e!=null && e.TryGetCurrentPattern(ValuePattern.Pattern,out p))editable=!((ValuePattern)p).Current.IsReadOnly;
        else if(e!=null && e.TryGetCurrentPattern(TextPattern.Pattern,out p)) {
            var readOnly=((TextPattern)p).DocumentRange.GetAttributeValue(TextPattern.IsReadOnlyAttribute);
            editable=readOnly is bool && !(bool)readOnly;
        }
        if(!editable)return Missing("Select an editable field outside TouchHelm, then use Dictate.");
        lastTarget=e;lastWindow=GetForegroundWindow();
        return new Dictionary<string,object>{{"available",true},{"field_id",Identity(e)},{"process_id",e.Current.ProcessId}};
    }
    public static Dictionary<string,object> RestoreTarget(string id) {
        if(lastTarget==null || Identity(lastTarget)!=id)return Missing("Select the destination field again.");
        if(!SetForegroundWindow(lastWindow))return Missing("Windows refused foreground activation. Select the destination field again.");
        lastTarget.SetFocus();return Target();
    }
    public static Dictionary<string,object> SpeechStatus() {
        bool access=System.Diagnostics.Process.GetProcessesByName("VoiceAccess").Length>0;
        bool open=false,unknown=false;
        foreach(var process in System.Diagnostics.Process.GetProcessesByName("TextInputHost")) {
            var windows=AutomationElement.RootElement.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.ProcessIdProperty,process.Id));
            foreach(AutomationElement window in windows) {
                if(window.Current.IsOffscreen || window.Current.BoundingRectangle.Width<30 || window.Current.BoundingRectangle.Height<20)continue;
                foreach(string id in new string[]{"VoiceTyping","Dictation","VoiceTypingPanel","VoiceTypingWindow"}) {
                    var item=window.FindFirst(TreeScope.Subtree,new PropertyCondition(AutomationElement.AutomationIdProperty,id));
                    if(item!=null && !item.Current.IsOffscreen)open=true;
                }
                if(!open)unknown=true;
            }
        }
        return new Dictionary<string,object>{{"voice_access",access},{"toolbar_open",open},{"toolbar_unknown",unknown}};
    }
    public static Dictionary<string,object> Read() {
        var e=Focused();string text;ValuePattern value;TextPattern pattern;
        if(e==null || !Content(e,out text,out value,out pattern))return Missing("Focus an editable PC text field. Protected, read-only and unsupported fields are excluded.");
        return new Dictionary<string,object>{{"available",true},{"field_id",Identity(e)},
            {"revision",Hash(text)},{"text",Normalize(text)},{"editable",true},{"message","PC field linked · two-way text"}};
    }
    static void Key(List<INPUT> list, ushort vk, ushort scan, uint flags) {
        list.Add(new INPUT{type=1,u=new UNION{key=new KEYBOARD{vk=vk,scan=scan,flags=flags}}});
    }
    static void Type(string text, string newlineMode) {
        var list=new List<INPUT>();
        if(text.Length==0) { Key(list,0x2e,0,0);Key(list,0x2e,0,2); }
        foreach(char c in text) {
            if(c=='\n') {
                if(newlineMode!="enter")Key(list,0x10,0,0);
                Key(list,0x0d,0,0);Key(list,0x0d,0,2);
                if(newlineMode!="enter")Key(list,0x10,0,2);
            } else { Key(list,0,c,4);Key(list,0,c,6); }
        }
        if(list.Count>0 && SendInput((uint)list.Count,list.ToArray(),Marshal.SizeOf(typeof(INPUT)))!=list.Count)
            throw new InvalidOperationException("Input refused");
    }
    public static Dictionary<string,object> Write(string id,string revision,string next,string newlineMode) {
        var e=Focused();string previous;ValuePattern value;TextPattern pattern;
        if(e==null || !Content(e,out previous,out value,out pattern))return Missing("PC field unavailable; your phone draft is kept.");
        if(Identity(e)!=id || Hash(previous)!=revision || next.Length>10000)
            return Missing("PC text or focus changed. Review the PC text before sending your draft.");
        // SetValue preserves the destination control's normal change notifications.
        if(value!=null)value.SetValue(next);
        else {
            foreach(int key in new int[]{0x10,0x11,0x12,0x5b,0x5c})
                if((GetAsyncKeyState(key)&0x8000)!=0)return Missing("Release held modifiers before syncing this field. Your draft is kept.");
            // Select only the changed range, preserving the rest of a rich document.
            string target=previous.Contains("\r\n")?next.Replace("\n","\r\n"):next;
            int start=0,end=0;
            while(start<previous.Length && start<target.Length && previous[start]==target[start])start++;
            while(end<previous.Length-start && end<target.Length-start && previous[previous.Length-end-1]==target[target.Length-end-1])end++;
            if(start==previous.Length && start==target.Length)return Read();
            var range=pattern.DocumentRange.Clone();
            range.MoveEndpointByRange(TextPatternRangeEndpoint.End,range,TextPatternRangeEndpoint.Start);
            range.MoveEndpointByUnit(TextPatternRangeEndpoint.End,TextUnit.Character,start);
            // Character units differ between providers; validate offsets before selection.
            if(range.GetText(-1)!=previous.Substring(0,start))return Missing("This app cannot safely select the edit. Your draft is kept.");
            range.MoveEndpointByRange(TextPatternRangeEndpoint.Start,range,TextPatternRangeEndpoint.End);
            range.MoveEndpointByUnit(TextPatternRangeEndpoint.End,TextUnit.Character,previous.Length-start-end);
            if(range.GetText(-1)!=previous.Substring(start,previous.Length-start-end))return Missing("This app cannot safely select the edit. Your draft is kept.");
            range.Select();
            var verify=Focused();string check;ValuePattern v;TextPattern t;
            if(verify==null || Identity(verify)!=id || !Content(verify,out check,out v,out t) || Hash(check)!=revision)
                return Missing("PC text changed before the edit. Your draft is kept.");
            Type(Normalize(target.Substring(start,target.Length-start-end)),newlineMode);
        }
        for(int i=0;i<8;i++) {
            var state=Read();
            if(!state.ContainsKey("text") || (string)state["text"]==Normalize(next))return state;
            System.Threading.Thread.Sleep(25);
        }
        return Read();
    }
}
