using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public class TouchHelmAirHud : Form {
    [DllImport("user32.dll")]static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override CreateParams CreateParams { get {
        var value=base.CreateParams;value.ExStyle|=0x08000000|0x80;return value;
    }}
    protected override void WndProc(ref Message message) {
        if(message.Msg==0x21){message.Result=new IntPtr(3);return;}
        base.WndProc(ref message);
    }
    class Ghost : Form {
        protected override bool ShowWithoutActivation { get { return true; } }
        protected override CreateParams CreateParams { get { var value=base.CreateParams;value.ExStyle|=0x08000000|0x80|0x20;return value; } }
        public Ghost() {
            FormBorderStyle=FormBorderStyle.None;ShowInTaskbar=false;TopMost=true;
            StartPosition=FormStartPosition.Manual;Size=new Size(30,30);
            BackColor=Color.FromArgb(1,2,3);TransparencyKey=BackColor;DoubleBuffered=true;
        }
        protected override void OnPaint(PaintEventArgs e) {
            e.Graphics.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using(var pen=new Pen(Color.FromArgb(132,219,227),3))e.Graphics.DrawEllipse(pen,4,4,21,21);
            using(var brush=new SolidBrush(Color.White))e.Graphics.FillEllipse(brush,12,12,5,5);
        }
    }
    static void Emit(string action) { Console.WriteLine("{\"action\":\""+action+"\"}");Console.Out.Flush(); }
    static int Integer(Dictionary<string,object> value,string key){return Convert.ToInt32(value[key]);}
    public static void Run() {
        try{SetProcessDpiAwarenessContext(new IntPtr(-4));}catch{}
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        var window=new TouchHelmAirHud();var ghost=new Ghost();
        window.Text="TouchHelm AirControl";window.FormBorderStyle=FormBorderStyle.None;
        window.AutoScaleMode=AutoScaleMode.None;
        window.ShowInTaskbar=false;window.TopMost=true;window.StartPosition=FormStartPosition.Manual;
        window.ClientSize=new Size(300,124);window.Location=new Point(-5000,-5000);
        window.BackColor=Color.FromArgb(16,37,46);window.Font=new Font("Segoe UI",10);
        var title=new Label{Text="AirControl",ForeColor=Color.FromArgb(233,246,245),Location=new Point(12,8),Size=new Size(276,22),Font=new Font("Segoe UI",11,FontStyle.Bold)};
        var detail=new Label{Text="Ready",ForeColor=Color.FromArgb(183,210,211),Location=new Point(12,32),Size=new Size(276,22),Font=new Font("Segoe UI",9)};
        var bar=new Panel{Location=new Point(12,61),Size=new Size(276,5),BackColor=Color.FromArgb(35,62,71)};
        var fill=new Panel{Location=Point.Empty,Size=new Size(0,5),BackColor=Color.FromArgb(132,219,227)};bar.Controls.Add(fill);
        var toggle=new Button{Text="Pause",Location=new Point(12,76),Size=new Size(133,42),FlatStyle=FlatStyle.Flat,BackColor=Color.FromArgb(132,219,227),ForeColor=window.BackColor,TabStop=false};
        var stop=new Button{Text="Stop",Location=new Point(155,76),Size=new Size(133,42),FlatStyle=FlatStyle.Flat,BackColor=Color.FromArgb(41,67,76),ForeColor=Color.White,TabStop=false};
        var recenter=new Button{Text="Recenter",Location=new Point(106,76),Size=new Size(88,42),FlatStyle=FlatStyle.Flat,BackColor=Color.FromArgb(41,67,76),ForeColor=Color.White,TabStop=false,Visible=false};
        window.Controls.AddRange(new Control[]{title,detail,bar,toggle,recenter,stop});
        bool active=false;toggle.Click+=(s,e)=>Emit(active?"pause":"resume");stop.Click+=(s,e)=>Emit("stop");
        recenter.Click+=(s,e)=>Emit("recenter");
        var incoming=new ConcurrentQueue<Dictionary<string,object>>();bool closed=false;
        var reader=new Thread(()=>{
            var serializer=new JavaScriptSerializer();string line;
            while((line=Console.ReadLine())!=null) {
                if(line.Length>8000)continue;
                try { var item=serializer.Deserialize<Dictionary<string,object>>(line);Dictionary<string,object> old;
                    while(incoming.TryDequeue(out old)){}incoming.Enqueue(item);
                } catch{}
            }
            closed=true;
        });reader.IsBackground=true;reader.Start();
        var timer=new System.Windows.Forms.Timer{Interval=40};
        timer.Tick+=(s,e)=>{
            if(closed){window.Close();return;}
            Dictionary<string,object> state;if(!incoming.TryDequeue(out state))return;
            try {
                active=(string)state["state"]=="active";title.Text="AirControl · "+(active?"Active":"Paused");
                detail.Text=active?(string)state["gesture_label"]:"Aim at Resume / Recenter, or use hotkey";
                toggle.Text=active?"Pause":"Resume";
                toggle.Width=active?133:88;recenter.Visible=!active;
                stop.Location=new Point(active?155:200,76);stop.Width=active?133:88;
                fill.Width=(int)(276*Math.Max(0,Math.Min(1,Convert.ToDouble(state["progress"]))));
                var display=state["display"] as Dictionary<string,object>;
                if(display==null)return;var rect=display["rect"] as Dictionary<string,object>;
                int x=Integer(rect,"x"),y=Integer(rect,"y"),width=Integer(rect,"width"),height=Integer(rect,"height");
                window.Location=new Point(x+width-320,y+height-150);
                var point=state["point"] as System.Collections.IList;
                if(!active && point!=null && point.Count==2) {
                    ghost.Location=new Point(x+(int)(Convert.ToDouble(point[0])*(width-1))-15,y+(int)(Convert.ToDouble(point[1])*(height-1))-15);
                    if(!ghost.Visible)ghost.Show();
                } else ghost.Hide();
            }catch{}
        };
        window.FormClosed+=(s,e)=>{timer.Stop();timer.Dispose();ghost.Close();ghost.Dispose();};
        timer.Start();Application.Run(window);window.Dispose();
    }
}
