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
        public float Progress=0;public bool Dragging=false;
        protected override bool ShowWithoutActivation { get { return true; } }
        protected override CreateParams CreateParams { get { var value=base.CreateParams;value.ExStyle|=0x08000000|0x80|0x20;return value; } }
        public Ghost() {
            FormBorderStyle=FormBorderStyle.None;ShowInTaskbar=false;TopMost=true;
            StartPosition=FormStartPosition.Manual;Size=new Size(38,38);
            BackColor=Color.FromArgb(1,2,3);TransparencyKey=BackColor;DoubleBuffered=true;
        }
        protected override void OnPaint(PaintEventArgs e) {
            e.Graphics.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            using(var pen=new Pen(Color.FromArgb(65,92,106),2))e.Graphics.DrawEllipse(pen,3,3,31,31);
            using(var pen=new Pen(Dragging?Color.FromArgb(255,199,105):Color.FromArgb(132,219,227),3)) {
                if(Dragging)e.Graphics.DrawEllipse(pen,3,3,31,31);
                else if(Progress>0)e.Graphics.DrawArc(pen,3,3,31,31,-90,Math.Min(1,Progress)*359);
            }
            using(var brush=new SolidBrush(Color.White))e.Graphics.FillEllipse(brush,17,17,4,4);
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
        window.Controls.AddRange(new Control[]{title,detail,bar});
        var buttons=new Dictionary<string,Button>();
        bool active=false;
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
                bool dragging=state.ContainsKey("dragging") && Convert.ToBoolean(state["dragging"]);
                string selection=state.ContainsKey("dwell_action")?Convert.ToString(state["dwell_action"]):"left_click";
                bool head=state.ContainsKey("mode") && Convert.ToString(state["mode"])=="head";
                bool scrolling=state.ContainsKey("head_scroll") && Convert.ToBoolean(state["head_scroll"]);
                detail.Text=active?(scrolling?"Dwell on Up / Down. Done returns to pointing.":dragging?"Drag held · move, then settle to drop":head?"Settle to "+selection.Replace("_"," "):(string)state["gesture_label"]):"Aim at Resume / Recenter, or use hotkey";
                var spec=state["layout"] as Dictionary<string,object>;
                if(spec==null)return;
                window.ClientSize=new Size(Integer(spec,"width"),Integer(spec,"height"));
                window.Location=new Point(Integer(spec,"x"),Integer(spec,"y"));
                foreach(var button in buttons.Values)button.Visible=false;
                foreach(Dictionary<string,object> target in (System.Collections.IEnumerable)spec["targets"]) {
                    string action=(string)target["action"];Button button;
                    if(!buttons.TryGetValue(action,out button)) {
                        button=new Button{FlatStyle=FlatStyle.Flat,TabStop=false};
                        string captured=action;button.Click+=(sender,args)=>Emit(captured);
                        buttons[action]=button;window.Controls.Add(button);
                    }
                    button.Text=(string)target["label"];button.SetBounds(Integer(target,"x"),Integer(target,"y"),Integer(target,"w"),Integer(target,"h"));
                    bool chosen=(action=="dwell_left" && selection=="left_click") || (action=="dwell_double" && selection=="double_click") || (action=="dwell_right" && selection=="right_click") || (action=="dwell_drag" && selection=="drag");
                    button.BackColor=chosen?Color.FromArgb(132,219,227):Color.FromArgb(41,67,76);
                    button.ForeColor=chosen?window.BackColor:Color.White;button.Visible=true;
                }
                fill.Width=(int)(276*Math.Max(0,Math.Min(1,Convert.ToDouble(state["progress"]))));
                var display=state["display"] as Dictionary<string,object>;
                if(display==null)return;var rect=display["rect"] as Dictionary<string,object>;
                int x=Integer(rect,"x"),y=Integer(rect,"y"),width=Integer(rect,"width"),height=Integer(rect,"height");
                var point=state["point"] as System.Collections.IList;
                if((!active || head) && point!=null && point.Count==2) {
                    ghost.Progress=(float)Convert.ToDouble(state["progress"]);ghost.Dragging=dragging;ghost.Invalidate();
                    ghost.Location=new Point(x+(int)(Convert.ToDouble(point[0])*(width-1))-19,y+(int)(Convert.ToDouble(point[1])*(height-1))-19);
                    if(!ghost.Visible)ghost.Show();
                } else ghost.Hide();
            }catch{}
        };
        window.FormClosed+=(s,e)=>{timer.Stop();timer.Dispose();ghost.Close();ghost.Dispose();};
        timer.Start();Application.Run(window);window.Dispose();
    }
}
