# PWM-PID-Colibri-VF50

*HEICO. Some information redacted*

**|USART|PID|PWM|WinCE|VC++|C#|**

Toradex Colibri VF50 doesn't have digital to analog converter. Delta motors used in this application requires analog voltage for speed control. So, PWM is used to simulate voltage and it's frequency can be varied to control motor speed.

PID control is implemented such that error between target and feedback value is multiplied with an user adjustable gain, to accomodate differences amoong plethora of products.
Integral and Derivative part of the control are not implemented as they're not required at the moment.

Control is provided on touch screen as well as via serial link to a GUI software running on PC. 

**Serial communication protocol:**
Data is sent out every 250ms, updating feedback values from sensors to the PC. Any faster update results is data corruption. 
On any command sent from PC to Colibri, such as starting the motor for desired application, an update string is sent containing '#' to mark different segments/packets of data.
This string is read under a try-catch statement to prevent bugging out if data is corrupted.




![image](https://github.com/vikasdotvivek/PWM-PID-Colibri-VF50/assets/43683145/5f49f986-a8b3-4e3b-bf81-2f98eaddbdd4)


Every checkbox or button will send out a serial command containing one or two changed variables, and rest will be blank variables as demonstrated in the example code.
2 machines were used in tandem with controls displayed on single PC via serial communication.





## Robust serial framing reference (proposed change)

The original snippets remain unchanged. See [src/SerialProtocol.cs](src/SerialProtocol.cs), [examples/WinCeControllerIntegration.cs](examples/WinCeControllerIntegration.cs), and [tests/Program.cs](tests/Program.cs).

**Problem:** `SerialPort.DataReceived` does not guarantee exactly one complete message. `ReadExisting().Split('#')` can read half a packet or two concatenated packets, and empty catch blocks conceal invalid data. The original sparse 11-field protocol is retained, but each command or status message must now be terminated with LF or CRLF (the original `WriteLine` sender supplies this if `NewLine` is configured accordingly).

**Updated receive path:** append serial chunks to a bounded per-port buffer; extract complete newline-delimited records; validate all 11 fields and optional final `#`; reject the entire malformed record; then dispatch each validated update to the existing UI/controller thread. Empty fields remain unchanged. No partial command is applied. Reset framing when reconnecting.

The 11 fields are, in order: control mode, given pressure, feedback pressure, given volume, feedback volume, tare pressure, tare volume, rate of loading, filename, save-data flag, start flag. Numeric fields require finite invariant-culture numbers; Boolean fields require True/False. Control mode accepts Pressure, Volume, Filling, or None. Check these against your deployed field definitions before integration.

**Example stop command, preserving all other fields:**

```csharp
serialport.WriteLine(ControlProtocol.BuildSingleFieldCommand(ControlField.Start, "False"));
```

**Example receive path:**

```csharp
// One instance per serial connection.
SerialCommandReceiver receiver = new SerialCommandReceiver(512);

// Inside DataReceived:
ReceiveResult result = receiver.Feed(serialport.ReadExisting());
foreach (ControlUpdate update in result.Updates)
{
    // Marshal to the UI/controller thread and apply validated fields.
}
// Log result.Rejections and result.OverlongLines.
```

**Run automated protocol tests** (requires .NET 8 SDK):

```sh
dotnet run --project tests/SerialProtocol.SelfTest.csproj --configuration Release
```

The parser uses older C# syntax to facilitate porting to a WinCE/.NET Compact Framework application. Compatibility with the actual device toolchain, installed serial library, and Toradex hardware has **not** been verified.

**Safety limitations:** framing and validation do not provide a CRC, authentication, sequence number, or communication watchdog; valid-looking corrupted or replayed frames may still be accepted. A PC sending sporadic commands should not be interpreted as a periodic heartbeat. The new code is a reference implementation, not a deployed motor controller. Validate machine interlocks, safe stop on faults, parameter limits, and sensor freshness independently before using any received Start=True command to drive PWM. Do not use the UI thread as the sole safety-stop path.
