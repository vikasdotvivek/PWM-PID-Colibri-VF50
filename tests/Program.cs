using System;
using System.Globalization;
using PwmPidColibri.Serial;
class Program
{
    static int checks;
    static void Check(bool ok, string name)
    {
        if (!ok) throw new Exception("FAILED: " + name);
        checks++;
    }
    static void Rejected(string frame)
    {
        ControlUpdate update;
        string error;
        Check(!ControlProtocol.TryParseFrame(frame, out update, out error) &&
              update == null && error != null, "invalid frame rejected");
    }
    static void Main()
    {
        string start = ControlProtocol.BuildSingleFieldCommand(ControlField.Start, "True");
        string stop = ControlProtocol.BuildSingleFieldCommand(ControlField.Start, "False");
        var rx = new SerialCommandReceiver(512);
        Check(rx.Feed(start.Substring(0, 8)).Updates.Length == 0, "partial chunk held");
        Check(rx.Feed(start.Substring(8) + "\r").Updates.Length == 0, "CR not complete");
        var part = rx.Feed("\n");
        Check(part.Updates.Length == 1 && part.Updates[0].GetBoolean(ControlField.Start), "fragmented CRLF");
        Check(!part.Updates[0].Has(ControlField.GivenPressure), "blank means unchanged");
        var both = rx.Feed(stop + "\n" + start + "\n");
        Check(both.Updates.Length == 2 && !both.Updates[0].GetBoolean(ControlField.Start)
            && both.Updates[1].GetBoolean(ControlField.Start), "two messages in one event");
        Check(rx.Feed(stop.Substring(0,stop.Length - 1) + "\n").Updates.Length == 1, "optional final hash");
        var mixed = rx.Feed("garbage\n" + stop + "\n");
        Check(mixed.Rejections.Length == 1 && mixed.Updates.Length == 1, "bad then valid");
        Rejected("garbage");
        Rejected("#one#two");
        Rejected(stop + "#");
        Rejected(ControlProtocol.BuildSingleFieldCommand(ControlField.ControlMode,"Pressure").Replace("Pressure", "Unknown"));
        string pressure = ControlProtocol.BuildSingleFieldCommand(ControlField.GivenPressure,"12.5");
        ControlUpdate p; string err;
        Check(ControlProtocol.TryParseFrame(pressure,out p,out err) && p.GetNumber(ControlField.GivenPressure)==12.5f, "valid number");
        Rejected(pressure.Replace("12.5","NaN"));
        Rejected(pressure.Replace("12.5","Infinity"));
        Rejected(pressure.Replace("12.5","invalid"));
        Rejected(stop.Replace("False","invalid"));
        Rejected(pressure.Replace("12.5", "12\r.5"));
        rx.Feed(start.Substring(0,10));
        rx.Reset();
        Check(rx.Feed(stop+"\n").Updates.Length==1, "reset on reconnect");
        var limited = new SerialCommandReceiver(32);
        var overflow = limited.Feed(new string('z',40)+"\n"+stop+"\n");
        Check(overflow.OverlongLines==1 && overflow.Updates.Length==1, "overflow recovered");
        CultureInfo previous=CultureInfo.CurrentCulture;
        try {
            CultureInfo.CurrentCulture=new CultureInfo("fr-FR");
            Check(ControlProtocol.TryParseFrame(pressure,out p,out err) &&
                p.GetNumber(ControlField.GivenPressure)==12.5f, "invariant culture");
        } finally { CultureInfo.CurrentCulture=previous; }
        Console.WriteLine("PASS " + checks + " serial protocol checks");
    }
}
