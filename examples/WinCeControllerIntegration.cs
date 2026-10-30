// Integration sketch for the existing WinForms/.NET Compact Framework TestConsole.
// This is NOT a deployable motor controller. Insert the commented members inside
// the existing form, adding src/SerialProtocol.cs to the device project.
// using PwmPidColibri.Serial;
//
// private readonly SerialCommandReceiver _commands = new SerialCommandReceiver(512);
//
// private void pressCtrller_DataReceived(object sender, SerialDataReceivedEventArgs e)
// {
//     string chunk;
//     try { chunk = pressCtrller.ReadExisting(); }
//     catch (IOException ex) { Debug.WriteLine(ex.Message); SignalCommunicationFault(); return; }
//     catch (InvalidOperationException ex) { Debug.WriteLine(ex.Message); SignalCommunicationFault(); return; }
//
//     ReceiveResult batch = _commands.Feed(chunk);
//     for (int i = 0; i < batch.Rejections.Length; i++)
//         Debug.WriteLine("Invalid packet: " + batch.Rejections[i]);
//     if (batch.OverlongLines > 0) Debug.WriteLine("Overlong packet dropped");
//
//     for (int i = 0; i < batch.Updates.Length; i++)
//     {
//         ControlUpdate message = batch.Updates[i];
//         if (!IsDisposed && IsHandleCreated)
//             BeginInvoke(new MethodInvoker(delegate { ApplyValidatedUpdate(message); }));
//     }
// }
//
// private void ApplyValidatedUpdate(ControlUpdate update)
// {
//     if (update.Has(ControlField.ControlMode))
//         CNFcontrolMode = update.GetText(ControlField.ControlMode);
//     if (update.Has(ControlField.GivenPressure))
//         CNFgivenPress = update.GetText(ControlField.GivenPressure);
//     if (update.Has(ControlField.FeedbackPressure))
//         CNFfeedbackpress = update.GetText(ControlField.FeedbackPressure);
//     if (update.Has(ControlField.GivenVolume))
//         CNFgivenVolume = update.GetText(ControlField.GivenVolume);
//     if (update.Has(ControlField.FeedbackVolume))
//         CNFfeedbackVolume = update.GetText(ControlField.FeedbackVolume);
//     if (update.Has(ControlField.TarePressure))
//         CNFtarePress = update.GetText(ControlField.TarePressure);
//     if (update.Has(ControlField.TareVolume))
//         CNFtareVol = update.GetText(ControlField.TareVolume);
//     if (update.Has(ControlField.RateOfLoading))
//         CNFrateofLoading = update.GetText(ControlField.RateOfLoading);
//     if (update.Has(ControlField.DataFileName))
//         CNFdataFileName = update.GetText(ControlField.DataFileName);
//     if (update.Has(ControlField.SaveData))
//         CNFsaveDataYesNo = update.GetText(ControlField.SaveData);
//     if (update.Has(ControlField.Start))
//     {
//         CNFstartYesNo = update.GetText(ControlField.Start);
//         // Forward TRUE only after independent sensor/interlock/readiness checks.
//         // Forward FALSE to the machine's verified safe-stop sequence.
//     }
// }
//
// On reconnection, call _commands.Reset() to clear partial old data.
// Example sender:
// serialport.WriteLine(ControlProtocol.BuildSingleFieldCommand(ControlField.Start, "False"));
//
// SignalCommunicationFault is an application-specific placeholder, NOT implemented.
// The hardware stop must not depend on successful UI dispatch.
// Confirm the transmitter's framing and .NET CF toolchain on real hardware.
