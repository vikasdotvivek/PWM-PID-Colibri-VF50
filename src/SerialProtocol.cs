using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PwmPidColibri.Serial
{
    // Field positions in the existing 11-field # protocol; zero-based here.
    public enum ControlField
    {
        ControlMode = 0,
        GivenPressure = 1,
        FeedbackPressure = 2,
        GivenVolume = 3,
        FeedbackVolume = 4,
        TarePressure = 5,
        TareVolume = 6,
        RateOfLoading = 7,
        DataFileName = 8,
        SaveData = 9,
        Start = 10
    }

    // Incremental, bounded line framer. Feed chunks, not assumed packets.
    // A frame ends at LF; CRLF is also accepted. An oversized line is
    // discarded entirely through its terminating LF, then decoding resumes.
    public sealed class LineFrameDecoder
    {
        private readonly int _maxLineChars;
        private readonly StringBuilder _pending = new StringBuilder();
        private bool _discarding;
        private int _overlongLines;

        public LineFrameDecoder(int maxLineChars)
        {
            if (maxLineChars < 16)
                throw new ArgumentOutOfRangeException("maxLineChars");
            _maxLineChars = maxLineChars;
        }

        public int OverlongLines { get { return _overlongLines; } }

        public IList<string> Append(string chunk)
        {
            if (chunk == null)
                throw new ArgumentNullException("chunk");

            List<string> completed = new List<string>();
            for (int i = 0; i < chunk.Length; i++)
            {
                char c = chunk[i];
                if (c == '\n')
                {
                    if (!_discarding)
                    {
                        string line = _pending.ToString();
                        if (line.EndsWith("\r", StringComparison.Ordinal))
                            line = line.Substring(0, line.Length - 1);
                        if (line.Length != 0)
                            completed.Add(line);
                    }
                    _pending.Length = 0;
                    _discarding = false;
                }
                else if (!_discarding)
                {
                    if (_pending.Length >= _maxLineChars)
                    {
                        _pending.Length = 0;
                        _discarding = true;
                        _overlongLines++;
                    }
                    else
                    {
                        _pending.Append(c);
                    }
                }
            }
            return completed;
        }

        // Call on reconnect so a partial frame from a previous connection
        // cannot be joined to the first frame of a new connection.
        public void Reset()
        {
            _pending.Length = 0;
            _discarding = false;
        }
    }

    // Immutable, validated patch. An unset field means "leave it unchanged".
    // In particular, receiving Start=False is an explicit stop request;
    // receiving a blank Start field is not a start or stop command.
    public sealed class ControlUpdate
    {
        private readonly string[] _fields;

        internal ControlUpdate(string[] fields)
        {
            _fields = (string[])fields.Clone();
        }

        public bool Has(ControlField field)
        {
            return _fields[(int)field].Length != 0;
        }

        public string GetText(ControlField field)
        {
            return Has(field) ? _fields[(int)field] : null;
        }

        public bool GetBoolean(ControlField field)
        {
            if (!Has(field))
                throw new InvalidOperationException("Field is not present");
            return bool.Parse(_fields[(int)field]);
        }

        public float GetNumber(ControlField field)
        {
            if (!Has(field))
                throw new InvalidOperationException("Field is not present");
            return float.Parse(_fields[(int)field], NumberStyles.Float, CultureInfo.InvariantCulture);
        }
    }

    public static class ControlProtocol
    {
        public const int FieldCount = 11;

        // Accepts both #a#b...#last and #a#b...#last# (legacy sender).
        // No state is mutated until all fields have passed validation.
        public static bool TryParseFrame(string frame, out ControlUpdate update, out string error)
        {
            update = null;
            error = null;
            if (String.IsNullOrEmpty(frame) || frame[0] != '#')
            {
                error = "Missing initial #";
                return false;
            }

            string[] tokens = frame.Split(new char[] { '#' });
            bool trailingDelimiter = tokens.Length == FieldCount + 2 && tokens[FieldCount + 1].Length == 0;
            if (tokens.Length != FieldCount + 1 && !trailingDelimiter)
            {
                error = "Expected exactly 11 fields (plus optional final #)";
                return false;
            }

            string[] values = new string[FieldCount];
            for (int i = 0; i < FieldCount; i++)
            {
                values[i] = tokens[i + 1];
                for (int j = 0; j < values[i].Length; j++)
                {
                    if (Char.IsControl(values[i][j]))
                    {
                        error = "Control character in field " + (i + 1);
                        return false;
                    }
                }
            }

            string mode = values[(int)ControlField.ControlMode];
            if (mode.Length != 0 && mode != "Pressure" && mode != "Volume" &&
                mode != "Filling" && mode != "None")
            {
                error = "Unknown control mode";
                return false;
            }

            ControlField[] numbers = new ControlField[] {
                ControlField.GivenPressure, ControlField.FeedbackPressure,
                ControlField.GivenVolume, ControlField.FeedbackVolume,
                ControlField.RateOfLoading
            };
            for (int i = 0; i < numbers.Length; i++)
            {
                string text = values[(int)numbers[i]];
                if (text.Length == 0) continue;
                float parsed;
                if (!float.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed)
                    || float.IsNaN(parsed) || float.IsInfinity(parsed))
                {
                    error = "Invalid finite numeric value in " + numbers[i];
                    return false;
                }
            }

            ControlField[] booleans = new ControlField[] {
                ControlField.TarePressure, ControlField.TareVolume,
                ControlField.SaveData, ControlField.Start
            };
            for (int i = 0; i < booleans.Length; i++)
            {
                string text = values[(int)booleans[i]];
                if (text.Length == 0) continue;
                bool parsed;
                if (!bool.TryParse(text, out parsed))
                {
                    error = "Invalid boolean value in " + booleans[i];
                    return false;
                }
            }

            update = new ControlUpdate(values);
            return true;
        }

        // Builds a legacy-compatible sparse command. Pass the returned text
        // to SerialPort.WriteLine(); do NOT add a newline to it here.
        public static string BuildSingleFieldCommand(ControlField field, string value)
        {
            if ((int)field < 0 || (int)field >= FieldCount || String.IsNullOrEmpty(value))
                throw new ArgumentException("Provide a valid field and nonempty value");

            string[] values = new string[FieldCount];
            for (int i = 0; i < values.Length; i++) values[i] = "";
            values[(int)field] = value;
            string frame = "#" + String.Join("#", values) + "#";
            ControlUpdate unused;
            string error;
            if (!TryParseFrame(frame, out unused, out error))
                throw new ArgumentException(error, "value");
            return frame;
        }
    }

    // Stateless per-chunk result. Each frame is either fully accepted or fully
    // rejected. The decoder itself is protected for concurrent event callbacks.
    public sealed class ReceiveResult
    {
        public readonly ControlUpdate[] Updates;
        public readonly string[] Rejections;
        public readonly int OverlongLines;

        internal ReceiveResult(List<ControlUpdate> updates, List<string> rejections, int overlongLines)
        {
            Updates = updates.ToArray();
            Rejections = rejections.ToArray();
            OverlongLines = overlongLines;
        }
    }

    public sealed class SerialCommandReceiver
    {
        private readonly object _sync = new object();
        private readonly LineFrameDecoder _decoder;

        public SerialCommandReceiver(int maxLineChars)
        {
            _decoder = new LineFrameDecoder(maxLineChars);
        }

        public ReceiveResult Feed(string chunk)
        {
            lock (_sync)
            {
                int before = _decoder.OverlongLines;
                IList<string> frames = _decoder.Append(chunk);
                List<ControlUpdate> updates = new List<ControlUpdate>();
                List<string> rejections = new List<string>();
                for (int i = 0; i < frames.Count; i++)
                {
                    ControlUpdate update;
                    string error;
                    if (ControlProtocol.TryParseFrame(frames[i], out update, out error))
                        updates.Add(update);
                    else
                        rejections.Add(error);
                }
                return new ReceiveResult(updates, rejections, _decoder.OverlongLines - before);
            }
        }

        public void Reset()
        {
            lock (_sync) _decoder.Reset();
        }
    }
}
