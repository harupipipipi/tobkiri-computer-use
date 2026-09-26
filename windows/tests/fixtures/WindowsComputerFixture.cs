using System;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;
using System.Runtime.InteropServices;

namespace TobkiriWindowsFixture {
    [ComImport]
    [Guid("A5CD92FF-29BE-454C-8D04-D82879FB3F1B")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IVirtualDesktopManager {
        [PreserveSig]
        int IsWindowOnCurrentVirtualDesktop(IntPtr topLevelWindow,
            [MarshalAs(UnmanagedType.Bool)] out bool onCurrentDesktop);
        [PreserveSig]
        int GetWindowDesktopId(IntPtr topLevelWindow, out Guid desktopId);
        [PreserveSig]
        int MoveWindowToDesktop(IntPtr topLevelWindow, ref Guid desktopId);
    }

    [ComImport]
    [Guid("AA509086-5CA9-4C25-8F95-589D3C07B48A")]
    class VirtualDesktopManager { }

    static class Log {
        public static string PathValue;
        static readonly object Gate = new object();

        static string Escape(string value) {
            return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"")
                .Replace("\r", "\\r").Replace("\n", "\\n");
        }

        public static void Write(string name, string fields) {
            lock (Gate) {
                File.AppendAllText(PathValue, "{\"event\":\"" + Escape(name) + "\"" +
                    (String.IsNullOrEmpty(fields) ? "" : "," + fields) + "}\n", Encoding.UTF8);
            }
        }

        public static string StringField(string name, string value) {
            return "\"" + Escape(name) + "\":\"" + Escape(value) + "\"";
        }
    }

    sealed class LoggingListBox : ListBox {
        protected override void OnMouseWheel(MouseEventArgs e) {
            base.OnMouseWheel(e);
            Log.Write("scroll", "\"delta\":" + e.Delta);
        }
    }

    sealed class TargetForm : Form {
        readonly TextBox nameBox;
        readonly Label applied;
        readonly Label countLabel;
        readonly Button dragPanel;
        int count;
        Point? dragStart;

        public TargetForm() {
            Text = "Tobkiri Windows Target [" + System.Diagnostics.Process.GetCurrentProcess().Id + "]";
            StartPosition = FormStartPosition.Manual;
            Location = new Point(120, 120);
            ClientSize = new Size(760, 620);
            Font = new Font("Segoe UI", 10F);

            var title = new Label { Text = "Tobkiri Windows Acceptance Fixture", AutoSize = true,
                Font = new Font("Segoe UI", 18F, FontStyle.Bold), Location = new Point(24, 20) };
            Controls.Add(title);
            Controls.Add(new Label { Text = "Name", AutoSize = true, Location = new Point(24, 83),
                AccessibleName = "Name label" });
            nameBox = new TextBox { Location = new Point(90, 78), Width = 430, AccessibleName = "Name" };
            Controls.Add(nameBox);
            var apply = new Button { Text = "Apply", Location = new Point(540, 76), Size = new Size(110, 34),
                AccessibleName = "Apply" };
            apply.Click += delegate {
                applied.Text = "Applied: " + nameBox.Text;
                Log.Write("apply", Log.StringField("value", nameBox.Text));
            };
            Controls.Add(apply);
            applied = new Label { Text = "Applied: (none)", AutoSize = true, Location = new Point(24, 125),
                AccessibleName = "Applied value" };
            Controls.Add(applied);
            countLabel = new Label { Text = "Count: 0", AutoSize = true, Location = new Point(24, 175),
                Font = new Font("Segoe UI", 16F), AccessibleName = "Count" };
            Controls.Add(countLabel);
            var increment = new Button { Text = "Increment", Location = new Point(180, 168), Size = new Size(130, 42),
                AccessibleName = "Increment" };
            increment.Click += delegate {
                count++;
                countLabel.Text = "Count: " + count;
                Log.Write("increment", "\"count\":" + count);
            };
            Controls.Add(increment);
            Controls.Add(new Label { Text = "Scrollable list", AutoSize = true, Location = new Point(24, 235) });
            var list = new LoggingListBox { Location = new Point(24, 265), Size = new Size(690, 150),
                AccessibleName = "Scrollable list" };
            for (int i = 0; i < 60; i++) list.Items.Add("Row " + i.ToString("00"));
            Controls.Add(list);
            dragPanel = new Button { Location = new Point(24, 450), Size = new Size(690, 130),
                BackColor = Color.FromArgb(244, 247, 251), FlatStyle = FlatStyle.Flat,
                Text = "Drag canvas", AccessibleName = "Drag canvas", TabStop = true };
            dragPanel.MouseDown += delegate(object sender, MouseEventArgs e) {
                dragStart = e.Location;
                Log.Write("drag_start", "\"x\":" + e.X + ",\"y\":" + e.Y);
            };
            dragPanel.MouseUp += delegate(object sender, MouseEventArgs e) {
                if (dragStart.HasValue) {
                    using (Graphics graphics = dragPanel.CreateGraphics()) {
                        using (var pen = new Pen(Color.FromArgb(225, 70, 88), 4F))
                            graphics.DrawLine(pen, dragStart.Value, e.Location);
                    }
                }
                Log.Write("drag_end", "\"x\":" + e.X + ",\"y\":" + e.Y);
            };
            Controls.Add(dragPanel);
        }
    }

    sealed class WitnessForm : Form {
        public WitnessForm() {
            Text = "Tobkiri Windows Witness [" + System.Diagnostics.Process.GetCurrentProcess().Id + "]";
            StartPosition = FormStartPosition.Manual;
            Location = new Point(980, 180);
            ClientSize = new Size(720, 520);
            Font = new Font("Segoe UI", 10F);
            Controls.Add(new Label { Text = "Foreground witness", AutoSize = true,
                Font = new Font("Segoe UI", 24F, FontStyle.Bold), Location = new Point(170, 100) });
            Controls.Add(new Label { Text = "Tobkiri must operate the other window without activating it.",
                AutoSize = true, Location = new Point(120, 175) });
            Shown += delegate { Activate(); BringToFront(); };
        }
    }

    static class Program {
        [STAThread]
        static void Main(string[] args) {
            string mode = null, ready = null, events = null, desktopId = null;
            for (int i = 0; i + 1 < args.Length; i += 2) {
                if (args[i] == "--mode") mode = args[i + 1];
                else if (args[i] == "--ready-file") ready = args[i + 1];
                else if (args[i] == "--event-log") events = args[i + 1];
                else if (args[i] == "--desktop-id") desktopId = args[i + 1];
            }
            if ((mode != "target" && mode != "witness") || ready == null || events == null)
                throw new ArgumentException("Use --mode target|witness --ready-file PATH --event-log PATH");
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(ready));
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(events));
            Log.PathValue = events;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Form form = mode == "target" ? (Form)new TargetForm() : new WitnessForm();
            form.Shown += delegate {
                int moveHr = 0;
                bool onCurrentDesktop = true;
                Guid assignedDesktop = Guid.Empty;
                if (!String.IsNullOrEmpty(desktopId)) {
                    Guid requestedDesktop = Guid.Parse(desktopId);
                    var manager = (IVirtualDesktopManager)new VirtualDesktopManager();
                    moveHr = manager.MoveWindowToDesktop(form.Handle, ref requestedDesktop);
                    manager.IsWindowOnCurrentVirtualDesktop(form.Handle, out onCurrentDesktop);
                    manager.GetWindowDesktopId(form.Handle, out assignedDesktop);
                    Log.Write("desktop_move", "\"hresult\":" + moveHr + ",\"on_current\":" +
                        (onCurrentDesktop ? "true" : "false") + "," +
                        Log.StringField("desktop_id", assignedDesktop.ToString("D")));
                }
                File.WriteAllText(ready, "{\"pid\":" + System.Diagnostics.Process.GetCurrentProcess().Id +
                    ",\"hwnd\":" + form.Handle.ToInt64() +
                    ",\"title\":\"" + form.Text.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"" +
                    ",\"desktop_hresult\":" + moveHr +
                    ",\"on_current_desktop\":" + (onCurrentDesktop ? "true" : "false") +
                    ",\"desktop_id\":\"" + assignedDesktop.ToString("D") + "\"}", Encoding.UTF8);
                Log.Write("ready", "\"pid\":" + System.Diagnostics.Process.GetCurrentProcess().Id + "," +
                    Log.StringField("title", form.Text));
            };
            Application.Run(form);
        }
    }
}
