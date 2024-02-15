# PWM-PID-Colibri-VF50

Toradex Colibri VF50 doesn't have digital to analog converter. Delta motors used in this application requires analog voltage for speed control. So, PWM is used to simulate voltage and it's frequency can be varied to control motor speed.

PID control is implemented such that error between target and feedback value is multiplied with an user adjustable gain, to accomodate differences amoong plethora of products.
Integral and Derivative part of the control are not implemented as they're not required at the moment.

Control is provided on touch screen as well as via serial link to an accomodating softwaare running on PC. 

Serial communication protocol:
Data is sent out every 250ms, updating feedback values from sensors to the PC. Any faster update results is data corruption. 
On any command sent from PC to Colibri, such as starting the motor for desired application, an update string is sent containing '#' to mark different segments or packets of data.
This string is read under a try-catch statement to prevent bugging out if data is corrupted.



![image](https://github.com/vikasdotvivek/PWM-PID-Colibri-VF50/assets/43683145/7d2e1dc1-e469-409a-82ee-aa2a42245e7b)
![image](https://github.com/vikasdotvivek/PWM-PID-Colibri-VF50/assets/43683145/5f49f986-a8b3-4e3b-bf81-2f98eaddbdd4)


Every checkbox or button will send out a serial command containing one or two changed variables, and rest will be blank variables as demonstrated in the example code.
2 machines were used in tandem with controls displayed on single PC via serial communication.



